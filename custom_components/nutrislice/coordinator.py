"""DataUpdateCoordinator for Nutrislice."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import NutrisliceApiClient, NutrisliceError
from .const import (
    CONF_DISTRICT,
    CONF_MENU_TYPES,
    CONF_NEXT_SCHOOL_DAY_ON_WEEKEND,
    CONF_SCAN_INTERVAL_HOURS,
    CONF_SCHOOL_NAME,
    CONF_SCHOOL_SLUG,
    DEFAULT_NEXT_SCHOOL_DAY_ON_WEEKEND,
    DEFAULT_SCAN_INTERVAL_HOURS,
    DEFAULT_UPCOMING_WEEKS,
    DOMAIN,
    ENTREE_FOOD_CATEGORIES,
    ENTREE_SECTION_KEYWORDS,
    IGNORE_SECTION_KEYWORDS,
    LOGGER,
    SIDE_SECTION_KEYWORDS,
)


@dataclass
class ParsedFoodItem:
    """Represents an individual food item."""

    name: str
    category: str
    section: str
    is_entree: bool
    is_side: bool
    calories: float | None = None
    allergens: list[str] = field(default_factory=list)
    raw_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedDayMenu:
    """Represents a day's menu."""

    date_str: str
    target_date: date
    is_holiday: bool
    has_menu: bool
    entrees: list[str] = field(default_factory=list)
    sides: list[str] = field(default_factory=list)
    beverages: list[str] = field(default_factory=list)
    condiments: list[str] = field(default_factory=list)
    items: list[ParsedFoodItem] = field(default_factory=list)
    categories: dict[str, list[str]] = field(default_factory=dict)
    raw_day: dict[str, Any] = field(default_factory=dict)

    @property
    def summary(self) -> str:
        """Return clean summary of entrees for state display (capped at 255 chars)."""
        if not self.has_menu or not self.entrees:
            return "No Menu Scheduled"
        text = ", ".join(self.entrees)
        if len(text) > 250:
            return text[:247] + "..."
        return text

    @property
    def formatted_description(self) -> str:
        """Formatted description suitable for calendar events or notifications."""
        lines: list[str] = []
        if self.entrees:
            lines.append(f"🍽️ Entrees:\n• " + "\n• ".join(self.entrees))
        if self.sides:
            lines.append(f"🥗 Sides & Fruits:\n• " + "\n• ".join(self.sides))
        if self.beverages:
            lines.append(f"🥛 Beverages:\n• " + "\n• ".join(self.beverages))
        return "\n\n".join(lines) if lines else "No menu items published."


@dataclass
class NutrisliceMenuData:
    """Menu data for a single menu type."""

    district: str
    school_slug: str
    school_name: str
    menu_type_slug: str
    menu_type_name: str
    days: list[dict[str, Any]]
    days_by_date: dict[str, ParsedDayMenu]
    today: ParsedDayMenu | None
    tomorrow: ParsedDayMenu | None
    next_school_day: ParsedDayMenu | None
    last_updated: datetime


def parse_day(raw_day: dict[str, Any]) -> ParsedDayMenu:
    """Parse a day dictionary from Nutrislice into ParsedDayMenu."""
    date_str = raw_day.get("date", "")
    try:
        t_date = date.fromisoformat(date_str)
    except (ValueError, TypeError):
        t_date = date.today()

    is_holiday = bool(raw_day.get("is_holiday", False))
    raw_menu_items = raw_day.get("menu_items", []) or []

    entrees: list[str] = []
    sides: list[str] = []
    beverages: list[str] = []
    condiments: list[str] = []
    categories: dict[str, list[str]] = {}
    parsed_items: list[ParsedFoodItem] = []

    current_section = "General"

    for item in raw_menu_items:
        if not isinstance(item, dict):
            continue

        if item.get("is_section_title"):
            current_section = item.get("text") or "General"
            continue

        food = item.get("food")
        if not food or not isinstance(food, dict):
            continue

        name = food.get("name")
        if not name:
            continue
        name = name.strip()

        food_category = (food.get("food_category") or "").lower()
        section_lower = current_section.lower()

        # Nutrition & allergens
        calories = None
        rounded_nutr = food.get("rounded_nutrition_info")
        if isinstance(rounded_nutr, dict):
            calories = rounded_nutr.get("calories")

        allergens: list[str] = []
        icons = food.get("icons")
        if isinstance(icons, dict):
            food_icons = icons.get("food_icons")
            if isinstance(food_icons, list):
                for icon in food_icons:
                    if isinstance(icon, dict) and icon.get("name"):
                        allergens.append(icon["name"])

        # Categorize
        is_entree = False
        is_side = False

        if any(kw in section_lower for kw in IGNORE_SECTION_KEYWORDS) or food_category in (
            "condiment",
            "beverage",
            "milk",
        ):
            if "milk" in section_lower or "beverage" in section_lower or food_category in ("milk", "beverage"):
                if name not in beverages:
                    beverages.append(name)
            else:
                if name not in condiments:
                    condiments.append(name)
        elif (
            food_category in ENTREE_FOOD_CATEGORIES
            or any(kw in section_lower for kw in ENTREE_SECTION_KEYWORDS)
        ):
            is_entree = True
            if name not in entrees:
                entrees.append(name)
        elif (
            food_category in ("side", "salad", "fruit", "vegetable")
            or any(kw in section_lower for kw in SIDE_SECTION_KEYWORDS)
        ):
            is_side = True
            if name not in sides:
                sides.append(name)
        else:
            # If uncertain, treat as side/other
            is_side = True
            if name not in sides:
                sides.append(name)

        categories.setdefault(current_section, []).append(name)
        parsed_items.append(
            ParsedFoodItem(
                name=name,
                category=food_category,
                section=current_section,
                is_entree=is_entree,
                is_side=is_side,
                calories=calories,
                allergens=allergens,
                raw_data=item,
            )
        )

    has_menu = len(parsed_items) > 0

    return ParsedDayMenu(
        date_str=date_str,
        target_date=t_date,
        is_holiday=is_holiday,
        has_menu=has_menu,
        entrees=entrees,
        sides=sides,
        beverages=beverages,
        condiments=condiments,
        items=parsed_items,
        categories=categories,
        raw_day=raw_day,
    )


class NutrisliceCoordinator(DataUpdateCoordinator[dict[str, NutrisliceMenuData]]):
    """Coordinator to fetch Nutrislice menu data for configured menu types."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        client: NutrisliceApiClient,
        entry: ConfigEntry,
    ) -> None:
        """Initialize coordinator."""
        self.client = client
        self.district: str = entry.data[CONF_DISTRICT]
        self.school_slug: str = entry.data[CONF_SCHOOL_SLUG]
        self.school_name: str = entry.data.get(CONF_SCHOOL_NAME, self.school_slug)
        self.menu_types: list[dict[str, Any]] = entry.data.get(CONF_MENU_TYPES, [])

        scan_interval_hours = entry.options.get(
            CONF_SCAN_INTERVAL_HOURS,
            entry.data.get(CONF_SCAN_INTERVAL_HOURS, DEFAULT_SCAN_INTERVAL_HOURS),
        )

        super().__init__(
            hass,
            LOGGER,
            name=f"Nutrislice ({self.school_name})",
            update_interval=timedelta(hours=scan_interval_hours),
        )

    async def _async_update_data(self) -> dict[str, NutrisliceMenuData]:
        """Fetch all menu types data from Nutrislice."""
        result: dict[str, NutrisliceMenuData] = {}
        now = datetime.now()
        today_date = date.today()
        tomorrow_date = today_date + timedelta(days=1)
        today_str = today_date.isoformat()
        tomorrow_str = tomorrow_date.isoformat()

        for menu_info in self.menu_types:
            menu_type_slug = menu_info.get("slug")
            menu_type_name = menu_info.get("name", menu_type_slug)
            if not menu_type_slug:
                continue

            try:
                raw_days = await self.client.async_get_upcoming_menu(
                    district=self.district,
                    school_slug=self.school_slug,
                    menu_type_slug=menu_type_slug,
                    start_date=today_date,
                    weeks=DEFAULT_UPCOMING_WEEKS,
                )
            except NutrisliceError as err:
                raise UpdateFailed(
                    f"Error updating Nutrislice menu for {self.school_slug}/{menu_type_slug}: {err}"
                ) from err

            days_by_date: dict[str, ParsedDayMenu] = {}
            for d in raw_days:
                parsed = parse_day(d)
                days_by_date[parsed.date_str] = parsed

            today_menu = days_by_date.get(today_str)
            tomorrow_menu = days_by_date.get(tomorrow_str)

            # Determine next school day if tomorrow has no menu or is weekend
            next_school_day: ParsedDayMenu | None = None
            sorted_dates = sorted(days_by_date.keys())
            for d_str in sorted_dates:
                if d_str >= today_str:
                    day_obj = days_by_date[d_str]
                    if day_obj.has_menu and day_obj.entrees:
                        if d_str > today_str and next_school_day is None:
                            next_school_day = day_obj

            result[menu_type_slug] = NutrisliceMenuData(
                district=self.district,
                school_slug=self.school_slug,
                school_name=self.school_name,
                menu_type_slug=menu_type_slug,
                menu_type_name=menu_type_name,
                days=raw_days,
                days_by_date=days_by_date,
                today=today_menu,
                tomorrow=tomorrow_menu,
                next_school_day=next_school_day,
                last_updated=now,
            )

        return result

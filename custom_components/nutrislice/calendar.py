"""Calendar platform for Nutrislice."""
from __future__ import annotations

from datetime import date, datetime, timedelta
import logging

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import NutrisliceCoordinator, NutrisliceMenuData, ParsedDayMenu

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Nutrislice calendar entities from a config entry."""
    coordinator: NutrisliceCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[NutrisliceCalendarEntity] = []

    for menu_type_slug, menu_data in coordinator.data.items():
        entities.append(
            NutrisliceCalendarEntity(coordinator, entry, menu_type_slug)
        )

    async_add_entities(entities)


class NutrisliceCalendarEntity(CoordinatorEntity[NutrisliceCoordinator], CalendarEntity):
    """Representation of a Nutrislice School Menu Calendar."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: NutrisliceCoordinator,
        entry: ConfigEntry,
        menu_type_slug: str,
    ) -> None:
        """Initialize calendar entity."""
        super().__init__(coordinator)
        self.entry = entry
        self.menu_type_slug = menu_type_slug
        menu_name = (
            self.menu_data.menu_type_name
            if self.menu_data
            else menu_type_slug.replace("-", " ").title()
        )
        self._attr_name = f"{menu_name} Calendar"
        self._attr_unique_id = (
            f"{coordinator.district}_{coordinator.school_slug}_{menu_type_slug}_calendar"
        )
        self._attr_icon = "mdi:calendar-month"

    @property
    def menu_data(self) -> NutrisliceMenuData | None:
        """Return menu data for this menu type."""
        return self.coordinator.data.get(self.menu_type_slug)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group school entities."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self.coordinator.district}_{self.coordinator.school_slug}")},
            name=self.coordinator.school_name,
            manufacturer="Nutrislice",
            model="School Menu System",
            configuration_url=f"https://{self.coordinator.district}.nutrislice.com/menu/{self.coordinator.school_slug}",
        )

    def _day_to_event(self, day: ParsedDayMenu) -> CalendarEvent:
        """Convert a ParsedDayMenu to a CalendarEvent."""
        menu_name = self.menu_data.menu_type_name if self.menu_data else "Meal"
        return CalendarEvent(
            start=day.target_date,
            end=day.target_date + timedelta(days=1),
            summary=f"{menu_name}: {day.summary}",
            description=day.formatted_description,
            location=self.coordinator.school_name,
        )

    @property
    def event(self) -> CalendarEvent | None:
        """Return the current or next upcoming calendar event."""
        if not self.menu_data:
            return None

        today_date = date.today()
        today_str = today_date.isoformat()

        # Check today first
        if today_str in self.menu_data.days_by_date:
            today_day = self.menu_data.days_by_date[today_str]
            if today_day.has_menu and today_day.entrees:
                return self._day_to_event(today_day)

        # Look for the next upcoming day with a menu
        for d_str in sorted(self.menu_data.days_by_date.keys()):
            if d_str >= today_str:
                day = self.menu_data.days_by_date[d_str]
                if day.has_menu and day.entrees:
                    return self._day_to_event(day)

        return None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return calendar events within a datetime range."""
        if not self.menu_data:
            return []

        start_d = start_date.date() if isinstance(start_date, datetime) else start_date
        end_d = end_date.date() if isinstance(end_date, datetime) else end_date

        events: list[CalendarEvent] = []

        for day in self.menu_data.days_by_date.values():
            if start_d <= day.target_date <= end_d:
                if day.has_menu and day.entrees:
                    events.append(self._day_to_event(day))

        return events

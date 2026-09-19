"""Calendar platform for Nutrislice."""
from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import CONF_TITLE_SECTIONS, DEFAULT_TITLE_SECTIONS, DOMAIN
from .coordinator import (
    NutrisliceCoordinator,
    NutrisliceMenuData,
    ParsedDayMenu,
    menu_entity_name,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Nutrislice calendar entities from a config entry."""
    coordinator: NutrisliceCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        NutrisliceCalendarEntity(coordinator, entry, menu_type_slug)
        for menu_type_slug in coordinator.data
    )


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
        self._attr_name = menu_entity_name(coordinator.school_name, menu_name)
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
            summary=day.calendar_summary(
                menu_name,
                self.entry.options.get(CONF_TITLE_SECTIONS, DEFAULT_TITLE_SECTIONS),
            ),
            description=day.formatted_description,
            location=self.coordinator.school_name,
        )

    @property
    def event(self) -> CalendarEvent | None:
        """Return the current or next upcoming calendar event."""
        if not self.menu_data:
            return None

        today_str = dt_util.now().date().isoformat()

        # ISO date strings sort chronologically, so the first match is the
        # current day's meal or, failing that, the next upcoming one.
        for d_str in sorted(self.menu_data.days_by_date):
            day = self.menu_data.days_by_date[d_str]
            if d_str >= today_str and day.has_entrees:
                return self._day_to_event(day)

        return None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return calendar events overlapping the requested range.

        ``end_date`` is exclusive, so a day starting exactly at ``end_date``
        is outside the range.
        """
        if not self.menu_data:
            return []

        return [
            self._day_to_event(day)
            for day in self.menu_data.days_by_date.values()
            if day.has_entrees
            and dt_util.start_of_local_day(day.target_date) < end_date
            and dt_util.start_of_local_day(day.target_date + timedelta(days=1)) > start_date
        ]

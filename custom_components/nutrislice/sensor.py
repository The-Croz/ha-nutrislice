"""Sensor platform for Nutrislice."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_CATEGORIES,
    ATTR_DATE,
    ATTR_DAYS,
    ATTR_DISTRICT,
    ATTR_ENTREES,
    ATTR_LAST_UPDATED,
    ATTR_MENU_ITEMS,
    ATTR_MENU_TYPE,
    ATTR_SCHOOL_NAME,
    ATTR_SIDES,
    CONF_NEXT_SCHOOL_DAY_ON_WEEKEND,
    DEFAULT_NEXT_SCHOOL_DAY_ON_WEEKEND,
    DOMAIN,
)
from .coordinator import NutrisliceCoordinator, NutrisliceMenuData


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Nutrislice sensors from a config entry."""
    coordinator: NutrisliceCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        sensor_class(coordinator, entry, menu_type_slug)
        for menu_type_slug in coordinator.data
        for sensor_class in (
            NutrisliceTodayMenuSensor,
            NutrisliceTomorrowMenuSensor,
            NutrisliceFullMenuSensor,
        )
    )


class NutrisliceBaseSensor(CoordinatorEntity[NutrisliceCoordinator], SensorEntity):
    """Base sensor for Nutrislice entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: NutrisliceCoordinator,
        entry: ConfigEntry,
        menu_type_slug: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entry = entry
        self.menu_type_slug = menu_type_slug

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


class NutrisliceTodayMenuSensor(NutrisliceBaseSensor):
    """Sensor displaying today's menu."""

    def __init__(
        self,
        coordinator: NutrisliceCoordinator,
        entry: ConfigEntry,
        menu_type_slug: str,
    ) -> None:
        """Initialize today sensor."""
        super().__init__(coordinator, entry, menu_type_slug)
        menu_name = (
            self.menu_data.menu_type_name if self.menu_data else menu_type_slug.replace("-", " ").title()
        )
        self._attr_name = f"{menu_name} Today"
        self._attr_unique_id = (
            f"{coordinator.district}_{coordinator.school_slug}_{menu_type_slug}_today"
        )
        if "breakfast" in menu_type_slug.lower():
            self._attr_icon = "mdi:food-croissant"
        elif "snack" in menu_type_slug.lower():
            self._attr_icon = "mdi:cookie"
        else:
            self._attr_icon = "mdi:food-drumstick"

    @property
    def native_value(self) -> str:
        """Return today's menu summary."""
        if not self.menu_data or not self.menu_data.today:
            return "No Menu Scheduled"
        return self.menu_data.today.summary

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return attributes for today's menu."""
        if not self.menu_data or not self.menu_data.today:
            return {
                ATTR_DATE: dt_util.now().date().isoformat(),
                ATTR_ENTREES: [],
                ATTR_SIDES: [],
                ATTR_MENU_ITEMS: [],
                ATTR_SCHOOL_NAME: self.coordinator.school_name,
                ATTR_MENU_TYPE: self.menu_type_slug,
            }

        today = self.menu_data.today
        return {
            ATTR_DATE: today.date_str,
            ATTR_ENTREES: today.entrees,
            ATTR_SIDES: today.sides,
            "beverages": today.beverages,
            ATTR_CATEGORIES: today.categories,
            ATTR_MENU_ITEMS: [
                {
                    "name": item.name,
                    "category": item.category,
                    "section": item.section,
                    "calories": item.calories,
                    "allergens": item.allergens,
                }
                for item in today.items
            ],
            ATTR_SCHOOL_NAME: self.menu_data.school_name,
            ATTR_MENU_TYPE: self.menu_data.menu_type_name,
            ATTR_LAST_UPDATED: self.menu_data.last_updated.isoformat(),
        }


class NutrisliceTomorrowMenuSensor(NutrisliceBaseSensor):
    """Sensor displaying tomorrow's menu (or next school day on weekends)."""

    def __init__(
        self,
        coordinator: NutrisliceCoordinator,
        entry: ConfigEntry,
        menu_type_slug: str,
    ) -> None:
        """Initialize tomorrow sensor."""
        super().__init__(coordinator, entry, menu_type_slug)
        menu_name = (
            self.menu_data.menu_type_name if self.menu_data else menu_type_slug.replace("-", " ").title()
        )
        self._attr_name = f"{menu_name} Tomorrow"
        self._attr_unique_id = (
            f"{coordinator.district}_{coordinator.school_slug}_{menu_type_slug}_tomorrow"
        )
        self._attr_icon = "mdi:food-variant"

    @property
    def _target_menu(self):
        """Return either tomorrow's menu or next school day menu."""
        if not self.menu_data:
            return None, False

        allow_next_school_day = self.entry.options.get(
            CONF_NEXT_SCHOOL_DAY_ON_WEEKEND,
            self.entry.data.get(CONF_NEXT_SCHOOL_DAY_ON_WEEKEND, DEFAULT_NEXT_SCHOOL_DAY_ON_WEEKEND),
        )

        tomorrow = self.menu_data.tomorrow
        if tomorrow and tomorrow.has_entrees:
            return tomorrow, False

        # If tomorrow is empty or weekend, fall back to next school day if configured
        if allow_next_school_day and self.menu_data.next_school_day:
            return self.menu_data.next_school_day, True

        return tomorrow, False

    @property
    def native_value(self) -> str:
        """Return tomorrow's menu summary."""
        target, _ = self._target_menu
        if not target:
            return "No Menu Scheduled"
        return target.summary

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return attributes for tomorrow's menu."""
        target, is_next_school_day = self._target_menu
        if not target:
            return {
                ATTR_DATE: None,
                ATTR_ENTREES: [],
                ATTR_SIDES: [],
                ATTR_MENU_ITEMS: [],
                "is_next_school_day": False,
                ATTR_SCHOOL_NAME: self.coordinator.school_name,
                ATTR_MENU_TYPE: self.menu_type_slug,
            }

        return {
            ATTR_DATE: target.date_str,
            "is_next_school_day": is_next_school_day,
            ATTR_ENTREES: target.entrees,
            ATTR_SIDES: target.sides,
            "beverages": target.beverages,
            ATTR_CATEGORIES: target.categories,
            ATTR_MENU_ITEMS: [
                {
                    "name": item.name,
                    "category": item.category,
                    "section": item.section,
                    "calories": item.calories,
                    "allergens": item.allergens,
                }
                for item in target.items
            ],
            ATTR_SCHOOL_NAME: self.menu_data.school_name,
            ATTR_MENU_TYPE: self.menu_data.menu_type_name,
            ATTR_LAST_UPDATED: self.menu_data.last_updated.isoformat(),
        }


class NutrisliceFullMenuSensor(NutrisliceBaseSensor):
    """Full menu sensor matching user's legacy REST sensor structure."""

    def __init__(
        self,
        coordinator: NutrisliceCoordinator,
        entry: ConfigEntry,
        menu_type_slug: str,
    ) -> None:
        """Initialize legacy full menu sensor."""
        super().__init__(coordinator, entry, menu_type_slug)
        menu_name = (
            self.menu_data.menu_type_name if self.menu_data else menu_type_slug.replace("-", " ").title()
        )
        self._attr_name = f"{menu_name} Menu"
        self._attr_unique_id = (
            f"{coordinator.district}_{coordinator.school_slug}_{menu_type_slug}_menu"
        )
        self._attr_icon = "mdi:silverware-fork-knife"

    @property
    def native_value(self) -> str:
        """Return current date to match legacy sensor value_template (value_json.date)."""
        return dt_util.now().date().isoformat()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return raw 'days' list for full backward compatibility."""
        if not self.menu_data:
            return {
                ATTR_DAYS: [],
                ATTR_DISTRICT: self.coordinator.district,
                ATTR_SCHOOL_NAME: self.coordinator.school_name,
                ATTR_MENU_TYPE: self.menu_type_slug,
            }

        return {
            ATTR_DAYS: self.menu_data.days,
            ATTR_DISTRICT: self.menu_data.district,
            ATTR_SCHOOL_NAME: self.menu_data.school_name,
            ATTR_MENU_TYPE: self.menu_data.menu_type_name,
            ATTR_LAST_UPDATED: self.menu_data.last_updated.isoformat(),
        }

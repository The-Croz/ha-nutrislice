"""Config flow for Nutrislice integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import selector

from .api import (
    CannotConnect,
    InvalidDistrict,
    NutrisliceApiClient,
    NutrisliceError,
    parse_nutrislice_url_or_slug,
)
from .const import (
    CONF_DISTRICT,
    CONF_MENU_TYPES,
    CONF_NEXT_SCHOOL_DAY_ON_WEEKEND,
    CONF_SCAN_INTERVAL_HOURS,
    CONF_SCHOOL_NAME,
    CONF_SCHOOL_SLUG,
    DEFAULT_NEXT_SCHOOL_DAY_ON_WEEKEND,
    DEFAULT_SCAN_INTERVAL_HOURS,
    DOMAIN,
    LOGGER,
)


class NutrisliceConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Nutrislice."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize flow."""
        self._district: str = ""
        self._schools: list[dict[str, Any]] = []
        self._selected_school: dict[str, Any] = {}
        self._preselected_menu_type: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: Input district name or Nutrislice menu URL."""
        errors: dict[str, str] = {}

        if user_input is not None:
            raw_input = user_input.get(CONF_DISTRICT, "").strip()
            district, school_slug, menu_type_slug = parse_nutrislice_url_or_slug(raw_input)

            if not district:
                errors["base"] = "invalid_district"
            else:
                session = async_get_clientsession(self.hass)
                client = NutrisliceApiClient(session)
                try:
                    schools = await client.async_get_schools(district)
                    if not schools:
                        errors["base"] = "no_schools_found"
                    else:
                        self._district = district
                        self._schools = schools
                        self._preselected_menu_type = menu_type_slug

                        # If user pasted a full URL with a school, check if it matches
                        if school_slug:
                            for s in schools:
                                if s.get("slug") == school_slug:
                                    self._selected_school = s
                                    return await self.async_step_menu_types()

                        return await self.async_step_school()

                except InvalidDistrict:
                    errors["base"] = "invalid_district"
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                except Exception as err:
                    LOGGER.exception("Unexpected error in Nutrislice setup: %s", err)
                    errors["base"] = "unknown"

        schema = vol.Schema(
            {
                vol.Required(CONF_DISTRICT): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.TEXT,
                        multiline=False,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_school(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2: Select school from district list."""
        errors: dict[str, str] = {}

        if user_input is not None:
            selected_slug = user_input.get(CONF_SCHOOL_SLUG)
            for s in self._schools:
                if s.get("slug") == selected_slug:
                    self._selected_school = s
                    return await self.async_step_menu_types()
            errors["base"] = "school_not_found"

        # Build dropdown options
        school_options = [
            selector.SelectOptionDict(
                value=s.get("slug", ""),
                label=s.get("name", s.get("slug", "")),
            )
            for s in self._schools
            if s.get("slug")
        ]

        # Sort alphabetically by label
        school_options.sort(key=lambda x: x["label"].lower())

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCHOOL_SLUG,
                    default=school_options[0]["value"] if school_options else None,
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=school_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="school",
            data_schema=schema,
            errors=errors,
            description_placeholders={"district": self._district},
        )

    async def async_step_menu_types(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 3: Choose menu types to track (Lunch, Breakfast, etc.)."""
        errors: dict[str, str] = {}
        active_menus: list[dict[str, Any]] = self._selected_school.get("active_menu_types", [])

        # Fallback if no active menus listed in school response
        if not active_menus:
            active_menus = [
                {"slug": "lunch", "name": "Lunch"},
                {"slug": "breakfast", "name": "Breakfast"},
            ]

        menu_options = [
            selector.SelectOptionDict(
                value=m.get("slug", ""),
                label=m.get("name", m.get("slug", "")),
            )
            for m in active_menus
            if m.get("slug")
        ]

        if user_input is not None:
            selected_slugs: list[str] = user_input.get(CONF_MENU_TYPES, [])
            if not selected_slugs:
                errors["base"] = "no_menu_types_selected"
            else:
                school_slug = self._selected_school.get("slug", "")
                school_name = self._selected_school.get("name", school_slug)

                # Set unique ID to prevent duplicates
                unique_id = f"{self._district}_{school_slug}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                # Build configured menu types list with names
                configured_menus = []
                for slug in selected_slugs:
                    name = next(
                        (m.get("name") for m in active_menus if m.get("slug") == slug),
                        slug.replace("-", " ").title(),
                    )
                    configured_menus.append({"slug": slug, "name": name})

                return self.async_create_entry(
                    title=f"{school_name} ({self._district})",
                    data={
                        CONF_DISTRICT: self._district,
                        CONF_SCHOOL_SLUG: school_slug,
                        CONF_SCHOOL_NAME: school_name,
                        CONF_MENU_TYPES: configured_menus,
                    },
                )

        # Determine default selections
        default_selections: list[str] = []
        available_slugs = [opt["value"] for opt in menu_options]
        if self._preselected_menu_type and self._preselected_menu_type in available_slugs:
            default_selections = [self._preselected_menu_type]
        elif "lunch" in available_slugs:
            default_selections = ["lunch"]
        elif menu_options:
            default_selections = [menu_options[0]["value"]]

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_MENU_TYPES,
                    default=default_selections,
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=menu_options,
                        multiple=True,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="menu_types",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "school_name": self._selected_school.get("name", "School")
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> NutrisliceOptionsFlowHandler:
        """Get options flow for this entry."""
        return NutrisliceOptionsFlowHandler(config_entry)


class NutrisliceOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Nutrislice options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL_HOURS,
                    default=self.config_entry.options.get(
                        CONF_SCAN_INTERVAL_HOURS,
                        self.config_entry.data.get(
                            CONF_SCAN_INTERVAL_HOURS, DEFAULT_SCAN_INTERVAL_HOURS
                        ),
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=24,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="hours",
                    )
                ),
                vol.Optional(
                    CONF_NEXT_SCHOOL_DAY_ON_WEEKEND,
                    default=self.config_entry.options.get(
                        CONF_NEXT_SCHOOL_DAY_ON_WEEKEND,
                        DEFAULT_NEXT_SCHOOL_DAY_ON_WEEKEND,
                    ),
                ): selector.BooleanSelector(),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)

"""Config flow for Nutrislice integration."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import selector

from .api import (
    CannotConnect,
    NutrisliceApiClient,
    candidate_districts,
    parse_nutrislice_url_or_slug,
)
from .const import (
    CONF_DISTRICT,
    CONF_LINK,
    CONF_MENU_TYPES,
    CONF_NEXT_SCHOOL_DAY_ON_WEEKEND,
    CONF_SCAN_INTERVAL_HOURS,
    CONF_SCHOOL_NAME,
    CONF_SCHOOL_SLUG,
    CONF_SYNC_CALENDAR,
    CONF_TITLE_SECTIONS,
    COURSE_EMOJI,
    DEFAULT_NEXT_SCHOOL_DAY_ON_WEEKEND,
    DEFAULT_SCAN_INTERVAL_HOURS,
    DEFAULT_TITLE_SECTIONS,
    DOMAIN,
    EXAMPLE_MENU_URL,
    LOGGER,
    LOOKUP_URL,
)


def title_sections_selector() -> selector.SelectSelector:
    """Checkboxes choosing which courses appear in calendar event titles."""
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=list(COURSE_EMOJI),
            multiple=True,
            mode=selector.SelectSelectorMode.LIST,
            translation_key=CONF_TITLE_SECTIONS,
        )
    )


class NutrisliceConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Nutrislice."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize flow."""
        self._district: str = ""
        # Every district the search matched, with its schools
        self._schools_by_district: dict[str, list[dict[str, Any]]] = {}
        self._selected_school: dict[str, Any] = {}
        self._preselected_menu_type: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: Paste a menu link, or search for a district by name."""
        errors: dict[str, str] = {}

        if user_input is not None:
            link = (user_input.get(CONF_LINK) or "").strip()
            name = (user_input.get(CONF_DISTRICT) or "").strip()

            # A link identifies the district exactly; a name has to be guessed at
            district, school_slug, menu_type_slug = parse_nutrislice_url_or_slug(link)
            candidates = [district] if district else []
            if not link:
                school_slug = menu_type_slug = None
                candidates = candidate_districts(name)

            # Reject an unrelated address before spending a request on it
            looks_like_address = any(char in link for char in ("/", ".", ":"))
            if link and looks_like_address and "nutrislice.com" not in link.lower():
                candidates = []

            if not link and not name:
                errors["base"] = "nothing_entered"
            elif not candidates:
                errors["base"] = "invalid_link" if link else "invalid_district"
            else:
                client = NutrisliceApiClient(async_get_clientsession(self.hass))
                try:
                    found = await client.async_find_districts(candidates)
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                except Exception as err:
                    LOGGER.exception("Unexpected error in Nutrislice setup: %s", err)
                    errors["base"] = "unknown"
                else:
                    if not found:
                        errors["base"] = "invalid_link" if link else "no_districts_found"
                    else:
                        self._schools_by_district = found
                        self._preselected_menu_type = menu_type_slug

                        # A link naming a school goes straight to menu selection
                        if school_slug and len(found) == 1:
                            only_district, schools = next(iter(found.items()))
                            for school in schools:
                                if school.get("slug") == school_slug:
                                    self._district = only_district
                                    self._selected_school = school
                                    return await self.async_step_menu_types()

                        return await self.async_step_school()

        schema = vol.Schema(
            {
                vol.Optional(CONF_LINK): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.URL,
                        multiline=False,
                    )
                ),
                vol.Optional(CONF_DISTRICT): selector.TextSelector(
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
            description_placeholders={
                "lookup_url": LOOKUP_URL,
                "example_url": EXAMPLE_MENU_URL,
            },
        )

    async def async_step_school(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2: Select the school from every district the search matched."""
        errors: dict[str, str] = {}

        if user_input is not None:
            district, _, school_slug = user_input.get(CONF_SCHOOL_SLUG, "").partition("/")
            for school in self._schools_by_district.get(district, []):
                if school.get("slug") == school_slug:
                    self._district = district
                    self._selected_school = school
                    return await self.async_step_menu_types()
            errors["base"] = "school_not_found"

        # Name the district next to each school only when several matched
        districts = ", ".join(self._schools_by_district)
        multiple_districts = len(self._schools_by_district) > 1
        school_options = [
            selector.SelectOptionDict(
                value=f"{district}/{school['slug']}",
                label=(
                    f"{school.get('name', school['slug'])} ({district})"
                    if multiple_districts
                    else school.get("name", school["slug"])
                ),
            )
            for district, schools in self._schools_by_district.items()
            for school in schools
            if school.get("slug")
        ]
        school_options.sort(key=lambda option: option["label"].lower())

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
            description_placeholders={
                "count": str(len(school_options)),
                "districts": districts,
                # Older releases' cached translations still reference {district}
                "district": districts,
            },
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
                    # Kept in options so it can be changed later under Configure
                    options={
                        CONF_TITLE_SECTIONS: user_input.get(
                            CONF_TITLE_SECTIONS, DEFAULT_TITLE_SECTIONS
                        )
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
                vol.Optional(
                    CONF_TITLE_SECTIONS, default=DEFAULT_TITLE_SECTIONS
                ): title_sections_selector(),
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
        return NutrisliceOptionsFlowHandler()


class NutrisliceOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Nutrislice options."""

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
                vol.Optional(
                    CONF_TITLE_SECTIONS,
                    default=self.config_entry.options.get(
                        CONF_TITLE_SECTIONS, DEFAULT_TITLE_SECTIONS
                    ),
                ): title_sections_selector(),
                # suggested_value (not default) so the field can be cleared
                vol.Optional(
                    CONF_SYNC_CALENDAR,
                    description={
                        "suggested_value": self.config_entry.options.get(
                            CONF_SYNC_CALENDAR
                        )
                    },
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        filter=selector.EntityFilterSelectorConfig(
                            domain="calendar",
                            supported_features=[
                                "calendar.CalendarEntityFeature.CREATE_EVENT"
                            ],
                        )
                    )
                ),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)

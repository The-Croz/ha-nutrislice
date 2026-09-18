"""Push Nutrislice menus into another Home Assistant calendar.

The Nutrislice calendar entities are read-only. This module copies upcoming
meals into a writable calendar (Local Calendar, Google Calendar, CalDAV, ...)
using the standard ``calendar.create_event`` service, so menus show up next to
the rest of a family's events and on any device that calendar syncs to.

Home Assistant offers no update or delete service for calendar events, so the
sync is additive: a meal is created once and never rewritten. A meal already on
the target calendar (same day, menu, and school) is skipped, which keeps the
sync safe to run after every refresh.
"""
from __future__ import annotations

from datetime import date, timedelta

from homeassistant.components.calendar import DOMAIN as CALENDAR_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .const import CONF_SYNC_CALENDAR, LOGGER
from .coordinator import NutrisliceCoordinator, NutrisliceMenuData, ParsedDayMenu


async def async_sync_entry(
    hass: HomeAssistant, entry: ConfigEntry, coordinator: NutrisliceCoordinator
) -> int:
    """Sync upcoming meals to the entry's target calendar, if one is configured.

    Returns the number of events created.
    """
    target = entry.options.get(CONF_SYNC_CALENDAR)
    if not target or not coordinator.data:
        return 0

    async with coordinator.sync_lock:
        return await _async_sync(hass, coordinator, target)


async def _async_sync(
    hass: HomeAssistant, coordinator: NutrisliceCoordinator, target: str
) -> int:
    """Create any upcoming meals missing from the target calendar."""
    today = dt_util.now().date()
    wanted: list[tuple[NutrisliceMenuData, ParsedDayMenu]] = sorted(
        (
            (menu, day)
            for menu in coordinator.data.values()
            for day in menu.days_by_date.values()
            if day.has_entrees and day.target_date >= today
        ),
        key=lambda pair: (pair[1].target_date, pair[0].menu_type_name),
    )
    if not wanted:
        return 0

    try:
        existing = await _async_get_existing_events(
            hass,
            target,
            wanted[0][1].target_date,
            wanted[-1][1].target_date + timedelta(days=1),
        )

        created = 0
        for menu, day in wanted:
            if _is_synced(existing, menu, day):
                continue
            await hass.services.async_call(
                CALENDAR_DOMAIN,
                "create_event",
                {
                    "entity_id": target,
                    "summary": day.calendar_summary(menu.menu_type_name),
                    "description": day.formatted_description,
                    "location": menu.school_name,
                    "start_date": day.target_date.isoformat(),
                    # All-day events end on the day after (exclusive)
                    "end_date": (day.target_date + timedelta(days=1)).isoformat(),
                },
                blocking=True,
            )
            created += 1
    except HomeAssistantError as err:
        # Typically a missing/renamed target or one that cannot create events;
        # the next refresh retries, so don't fail the coordinator over it.
        LOGGER.warning("Could not sync Nutrislice menus to %s: %s", target, err)
        return 0

    if created:
        LOGGER.debug("Synced %d Nutrislice meal(s) to %s", created, target)
    return created


async def _async_get_existing_events(
    hass: HomeAssistant, target: str, first: date, end: date
) -> list[dict[str, str]]:
    """Return the events already on the target calendar within [first, end)."""
    response = await hass.services.async_call(
        CALENDAR_DOMAIN,
        "get_events",
        {
            "entity_id": target,
            "start_date_time": dt_util.start_of_local_day(first),
            "end_date_time": dt_util.start_of_local_day(end),
        },
        blocking=True,
        return_response=True,
    )
    return (response or {}).get(target, {}).get("events", [])


def _is_synced(
    existing: list[dict[str, str]], menu: NutrisliceMenuData, day: ParsedDayMenu
) -> bool:
    """Return True if this meal is already on the calendar.

    Matches on day, school, and menu name rather than the full title, so a meal
    whose entrees changed after syncing isn't duplicated.
    """
    title_prefix = f"{menu.menu_type_name}: "
    return any(
        str(event.get("start", ""))[:10] == day.date_str
        and event.get("location") == menu.school_name
        and str(event.get("summary", "")).startswith(title_prefix)
        for event in existing
    )

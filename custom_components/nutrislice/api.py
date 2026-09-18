"""Nutrislice API client."""
from __future__ import annotations

import asyncio
from datetime import date, timedelta
import logging
import re
from typing import Any
from urllib.parse import urlparse

import aiohttp

from .const import LOGGER

TIMEOUT = aiohttp.ClientTimeout(total=15)
DEFAULT_HEADERS = {
    "User-Agent": "HomeAssistant-Nutrislice/1.0",
    "Accept": "application/json",
}


class NutrisliceError(Exception):
    """Base exception for Nutrislice."""


class CannotConnect(NutrisliceError):
    """Exception to indicate connection failure."""


class InvalidDistrict(NutrisliceError):
    """Exception to indicate district is invalid."""


class SchoolNotFound(NutrisliceError):
    """Exception to indicate school was not found."""


class MenuNotFound(NutrisliceError):
    """Exception to indicate menu was not found."""


def parse_nutrislice_url_or_slug(input_str: str) -> tuple[str, str | None, str | None]:
    """Parse district, school, and menu type from a URL or slug.

    Returns:
        tuple[district, school_slug, menu_type_slug]
    """
    cleaned = input_str.strip()
    if not cleaned:
        return "", None, None

    # Check if this is a URL or domain
    if "nutrislice.com" in cleaned or "://" in cleaned:
        if not cleaned.startswith(("http://", "https://")):
            cleaned = f"https://{cleaned}"
        parsed = urlparse(cleaned)
        netloc = parsed.netloc.lower()
        parts = netloc.split(".")

        # Extract district subdomain (e.g., 'soudertonsd' from 'soudertonsd.nutrislice.com' or 'soudertonsd.api.nutrislice.com')
        district = parts[0] if parts else ""
        if district == "api" or district == "lookup":
            district = ""

        path_segments = [p for p in parsed.path.strip("/").split("/") if p]
        school_slug: str | None = None
        menu_type_slug: str | None = None

        # Check API URL format: /menu/api/weeks/school/<school>/menu-type/<menu-type>/...
        if "school" in path_segments:
            try:
                school_idx = path_segments.index("school")
                if school_idx + 1 < len(path_segments):
                    school_slug = path_segments[school_idx + 1]
            except ValueError:
                pass

        if "menu-type" in path_segments:
            try:
                menu_idx = path_segments.index("menu-type")
                if menu_idx + 1 < len(path_segments):
                    menu_type_slug = path_segments[menu_idx + 1]
            except ValueError:
                pass

        # Check Web URL format: /menu/<school>/<menu-type>/...
        if not school_slug and path_segments:
            if path_segments[0] == "menu" and len(path_segments) > 1:
                school_slug = path_segments[1]
                if len(path_segments) > 2 and not path_segments[2].isdigit():
                    menu_type_slug = path_segments[2]

        return district, school_slug, menu_type_slug

    # Plain district slug entered
    # Clean non-alphanumeric chars except dashes
    district = re.sub(r"[^a-zA-Z0-9-]", "", cleaned.lower())
    return district, None, None


class NutrisliceApiClient:
    """Nutrislice API client."""

    def __init__(self, session: aiohttp.ClientSession | None = None) -> None:
        """Initialize API client."""
        self._session = session
        self._own_session = False

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create client session."""
        if self._session is None or getattr(self._session, "closed", False) is True:
            self._session = aiohttp.ClientSession(timeout=TIMEOUT, headers=DEFAULT_HEADERS)
            self._own_session = True
        return self._session

    async def close(self) -> None:
        """Close session if owned."""
        if self._own_session and self._session and not self._session.closed:
            await self._session.close()

    async def async_get_schools(self, district: str) -> list[dict[str, Any]]:
        """Fetch all schools in a district."""
        district = district.strip().lower()
        if not district:
            raise InvalidDistrict("District cannot be empty")

        url = f"https://{district}.api.nutrislice.com/menu/api/schools/"
        session = await self._get_session()

        try:
            async with session.get(url) as response:
                if response.status == 404:
                    raise InvalidDistrict(f"District '{district}' not found (HTTP 404)")
                if response.status >= 500:
                    raise CannotConnect(f"Nutrislice server error: HTTP {response.status}")
                if response.status != 200:
                    raise CannotConnect(f"Unexpected response: HTTP {response.status}")

                data = await response.json(content_type=None)
                if not isinstance(data, list):
                    raise CannotConnect("Unexpected API response format: expected school list")
                return data

        except (aiohttp.ClientConnectorError, aiohttp.ClientError, asyncio.TimeoutError) as err:
            LOGGER.error("Connection error reaching Nutrislice for district %s: %s", district, err)
            raise CannotConnect(f"Failed to connect to Nutrislice: {err}") from err

    async def async_get_school(self, district: str, school_slug: str) -> dict[str, Any]:
        """Fetch a specific school by slug."""
        schools = await self.async_get_schools(district)
        for school in schools:
            if school.get("slug") == school_slug:
                return school
        raise SchoolNotFound(f"School '{school_slug}' not found in district '{district}'")

    async def async_get_week_menu(
        self,
        district: str,
        school_slug: str,
        menu_type_slug: str,
        target_date: date | None = None,
    ) -> dict[str, Any]:
        """Fetch weekly menu for a school and meal type."""
        if target_date is None:
            target_date = date.today()

        url = (
            f"https://{district}.api.nutrislice.com/menu/api/weeks/school/"
            f"{school_slug}/menu-type/{menu_type_slug}/"
            f"{target_date.year:04d}/{target_date.month:02d}/{target_date.day:02d}/?format=json"
        )
        session = await self._get_session()

        try:
            async with session.get(url) as response:
                if response.status == 404:
                    raise MenuNotFound(
                        f"Menu not found for school '{school_slug}', type '{menu_type_slug}'"
                    )
                if response.status != 200:
                    raise CannotConnect(f"Failed to fetch menu: HTTP {response.status}")

                return await response.json(content_type=None)

        except (aiohttp.ClientConnectorError, aiohttp.ClientError, asyncio.TimeoutError) as err:
            LOGGER.error("Error fetching menu from %s: %s", url, err)
            raise CannotConnect(f"Failed to connect to Nutrislice: {err}") from err

    async def async_get_upcoming_menu(
        self,
        district: str,
        school_slug: str,
        menu_type_slug: str,
        start_date: date | None = None,
        weeks: int = 2,
    ) -> list[dict[str, Any]]:
        """Fetch upcoming weeks and return unified chronological list of days."""
        if start_date is None:
            start_date = date.today()

        all_days: dict[str, dict[str, Any]] = {}

        for week_idx in range(weeks):
            week_date = start_date + timedelta(days=week_idx * 7)
            try:
                week_data = await self.async_get_week_menu(
                    district, school_slug, menu_type_slug, week_date
                )
                for day in week_data.get("days", []):
                    day_date = day.get("date")
                    if day_date and day_date not in all_days:
                        all_days[day_date] = day
            except MenuNotFound:
                # Later weeks may not be published yet
                LOGGER.debug(
                    "Menu not published yet for %s week of %s",
                    menu_type_slug,
                    week_date.isoformat(),
                )
            except Exception as err:
                LOGGER.warning("Error fetching week %d for %s: %s", week_idx, school_slug, err)
                if week_idx == 0:
                    # If the first week fails, raise error
                    raise

        # Return sorted by date
        sorted_days = [all_days[k] for k in sorted(all_days.keys())]
        return sorted_days

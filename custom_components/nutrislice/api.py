"""Nutrislice API client."""
from __future__ import annotations

import asyncio
from datetime import date, timedelta
import re
from typing import Any
from urllib.parse import urlparse

import aiohttp

from .const import LOGGER

TIMEOUT = aiohttp.ClientTimeout(total=15)
# Any HTTP response from this host proves the network works (used to tell an
# unknown district apart from being offline).
REACHABILITY_URL = "https://api.nutrislice.com/"
MAX_DISTRICT_CANDIDATES = 16
MAX_CONCURRENT_LOOKUPS = 6

# Words that describe *what* a district is rather than *which* one it is.
GENERIC_NAME_WORDS = frozenset(
    {
        "the", "of", "and", "for", "school", "schools", "district", "public",
        "county", "city", "unified", "independent", "community", "consolidated",
        "area", "regional", "academy", "academies", "charter", "department",
        "education", "board", "system", "elementary", "middle", "high", "junior",
        "senior", "primary", "central",
    }
)
# Common ways districts turn their name into a Nutrislice subdomain
# (e.g. "soudertonsd", "austinisd", "mcsin-k12", "a2schools").
DISTRICT_SLUG_SUFFIXES = ("sd", "schools", "isd", "usd", "csd", "cusd", "psd", "ps")
DISTRICT_SLUG_HYPHENATED_SUFFIXES = ("k12", "sd", "schools")
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


class DistrictUnreachable(CannotConnect):
    """A district's hostname could not be reached.

    Either the district doesn't exist (its subdomain has no DNS record) or the
    network is down; callers tell the two apart with a reachability check.
    """


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


def candidate_districts(query: str) -> list[str]:
    """Return likely district subdomains for a free-text name, best guess first.

    Nutrislice has no public district search, so names are turned into the
    slugs districts commonly use and each one is checked against the API.
    "Fairfax County Public Schools" yields ``fairfax``, ``fcps``,
    ``fairfaxsd``, ``fairfax-k12``, ...
    """
    tokens = re.findall(r"[a-z0-9]+", query.lower())
    if not tokens:
        return []

    stem_tokens = [t for t in tokens if t not in GENERIC_NAME_WORDS] or tokens
    stem = "".join(stem_tokens)

    candidates = ["".join(tokens), "-".join(tokens), stem]

    # Initials, e.g. "Fairfax County Public Schools" -> "fcps"
    if 2 < len(tokens) <= 6:
        candidates.append("".join(t[0] for t in tokens))

    # "District 211" -> "d211" / "district211" / "sd211"
    numbers = [t for t in tokens if t.isdigit()]
    if numbers:
        candidates += [f"d{numbers[0]}", f"district{numbers[0]}", f"sd{numbers[0]}"]

    candidates += [f"{stem}{suffix}" for suffix in DISTRICT_SLUG_SUFFIXES]
    candidates += [f"{stem}-{suffix}" for suffix in DISTRICT_SLUG_HYPHENATED_SUFFIXES]

    unique = list(dict.fromkeys(c for c in candidates if c))
    return unique[:MAX_DISTRICT_CANDIDATES]


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

    async def _async_fetch_schools(self, district: str) -> list[dict[str, Any]]:
        """Fetch a district's schools without judging connection failures."""
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

        except aiohttp.ClientConnectorError as err:
            raise DistrictUnreachable(f"Could not reach {district}: {err}") from err
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise CannotConnect(f"Failed to connect to Nutrislice: {err}") from err

    async def _async_is_online(self) -> bool:
        """Return True if Nutrislice's API host answers at all."""
        session = await self._get_session()
        try:
            async with session.get(REACHABILITY_URL):
                return True
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return False

    async def async_get_schools(self, district: str) -> list[dict[str, Any]]:
        """Fetch all schools in a district."""
        district = district.strip().lower()
        if not district:
            raise InvalidDistrict("District cannot be empty")

        try:
            return await self._async_fetch_schools(district)
        except DistrictUnreachable as err:
            # An unknown district has no DNS record, which looks just like a
            # connection failure; only report one if we're really offline.
            if await self._async_is_online():
                raise InvalidDistrict(f"District '{district}' not found") from err
            raise

    async def async_find_districts(
        self, candidates: list[str]
    ) -> dict[str, list[dict[str, Any]]]:
        """Check candidate district slugs and return the ones that exist.

        Returns a mapping of district slug to its schools (empty if none exist).
        Raises CannotConnect only when nothing was found *and* Nutrislice could
        not be reached, so "no such district" is never reported as an outage.
        """
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_LOOKUPS)

        async def probe(district: str) -> tuple[list[dict[str, Any]] | None, NutrisliceError | None]:
            async with semaphore:
                try:
                    return await self._async_fetch_schools(district), None
                except InvalidDistrict:
                    return None, None
                except NutrisliceError as err:
                    return None, err

        results = await asyncio.gather(*(probe(c) for c in candidates))

        found = {
            district: schools
            for district, (schools, _) in zip(candidates, results)
            if schools
        }
        if found:
            return found

        errors = [err for _, err in results if err is not None]
        if any(not isinstance(err, DistrictUnreachable) for err in errors):
            raise next(err for err in errors if not isinstance(err, DistrictUnreachable))
        if errors and not await self._async_is_online():
            raise errors[0]
        return {}

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

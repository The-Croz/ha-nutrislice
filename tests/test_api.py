"""Unit tests for the Nutrislice API client."""
import unittest
from unittest.mock import AsyncMock, MagicMock

from tests.ha_mock import setup_ha_mocks

setup_ha_mocks()

import aiohttp

from custom_components.nutrislice.api import (
    MAX_DISTRICT_CANDIDATES,
    CannotConnect,
    InvalidDistrict,
    MenuNotFound,
    NutrisliceApiClient,
    candidate_districts,
    parse_nutrislice_url_or_slug,
)


class TestNutrisliceUrlParsing(unittest.TestCase):
    """Test URL and slug parsing."""

    def test_plain_district_slug(self):
        district, school, menu = parse_nutrislice_url_or_slug("sample-district")
        self.assertEqual(district, "sample-district")
        self.assertIsNone(school)
        self.assertIsNone(menu)

    def test_district_with_spaces_and_special_chars(self):
        district, school, menu = parse_nutrislice_url_or_slug("  Great-Schools!  ")
        self.assertEqual(district, "great-schools")
        self.assertIsNone(school)
        self.assertIsNone(menu)

    def test_district_domain(self):
        district, school, menu = parse_nutrislice_url_or_slug("sample-district.nutrislice.com")
        self.assertEqual(district, "sample-district")
        self.assertIsNone(school)
        self.assertIsNone(menu)

    def test_full_web_url_with_school_and_menu(self):
        url = "https://sample-district.nutrislice.com/menu/lincoln-elementary/lunch"
        district, school, menu = parse_nutrislice_url_or_slug(url)
        self.assertEqual(district, "sample-district")
        self.assertEqual(school, "lincoln-elementary")
        self.assertEqual(menu, "lunch")

    def test_web_url_with_date(self):
        url = "https://sample-district.nutrislice.com/menu/lincoln-elementary/lunch/2026/09/18"
        district, school, menu = parse_nutrislice_url_or_slug(url)
        self.assertEqual(district, "sample-district")
        self.assertEqual(school, "lincoln-elementary")
        self.assertEqual(menu, "lunch")

    def test_api_rest_url(self):
        url = "https://sample-district.api.nutrislice.com/menu/api/weeks/school/lincoln-elementary/menu-type/lunch/2026/09/18?format=json"
        district, school, menu = parse_nutrislice_url_or_slug(url)
        self.assertEqual(district, "sample-district")
        self.assertEqual(school, "lincoln-elementary")
        self.assertEqual(menu, "lunch")

    def test_empty_input(self):
        district, school, menu = parse_nutrislice_url_or_slug("")
        self.assertEqual(district, "")
        self.assertIsNone(school)
        self.assertIsNone(menu)


class TestCandidateDistricts(unittest.TestCase):
    """Test turning a free-text name into likely district subdomains."""

    def test_typed_name_is_tried_first(self):
        self.assertEqual(candidate_districts("Austin ISD")[0], "austinisd")

    def test_drops_generic_words_for_the_stem(self):
        candidates = candidate_districts("Souderton Area School District")
        self.assertIn("souderton", candidates)
        self.assertIn("soudertonsd", candidates)

    def test_common_suffixes_and_hyphenated_forms(self):
        candidates = candidate_districts("Maple Grove")
        for expected in ("maplegrove", "maple-grove", "maplegrovesd", "maplegroveisd", "maplegrove-k12"):
            self.assertIn(expected, candidates)

    def test_initials_for_long_names(self):
        self.assertIn("fcps", candidate_districts("Fairfax County Public Schools"))

    def test_district_number(self):
        self.assertIn("d211", candidate_districts("Township High School District 211"))

    def test_only_generic_words_still_searches(self):
        self.assertIn("publicschools", candidate_districts("Public Schools"))

    def test_junk_and_empty_input(self):
        self.assertEqual(candidate_districts(""), [])
        self.assertEqual(candidate_districts("  !!  "), [])

    def test_unique_and_capped(self):
        candidates = candidate_districts("A Very Long Made Up District Name Here")
        self.assertEqual(len(candidates), len(set(candidates)))
        self.assertLessEqual(len(candidates), MAX_DISTRICT_CANDIDATES)
        self.assertTrue(all(c == c.lower() and " " not in c for c in candidates))


def response(status=200, body=None):
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=body)
    ctx = MagicMock()
    ctx.__aenter__.return_value = resp
    return ctx


def connector_error():
    return aiohttp.ClientConnectorError(MagicMock(), OSError("Name or service not known"))


class FakeSession:
    """Session whose responses depend on the requested district subdomain."""

    def __init__(self, districts, online=True):
        self.districts = districts  # subdomain -> status | list of schools | Exception
        self.online = online
        self.requests = []
        self.closed = False

    def get(self, url):
        self.requests.append(url)
        if url == "https://api.nutrislice.com/":
            if not self.online:
                raise connector_error()
            return response(404)
        subdomain = url.split("//")[1].split(".")[0]
        result = self.districts.get(subdomain, connector_error())
        if isinstance(result, Exception):
            raise result
        if isinstance(result, int):
            return response(result)
        return response(200, result)


class TestDistrictDiscovery(unittest.IsolatedAsyncioTestCase):
    """Test finding districts and telling 'no such district' from 'offline'."""

    async def test_unknown_district_is_invalid_not_a_connection_error(self):
        client = NutrisliceApiClient(FakeSession({}, online=True))
        with self.assertRaises(InvalidDistrict):
            await client.async_get_schools("austinisd")

    async def test_offline_is_a_connection_error(self):
        client = NutrisliceApiClient(FakeSession({}, online=False))
        with self.assertRaises(CannotConnect) as ctx:
            await client.async_get_schools("sample-district")
        self.assertNotIsInstance(ctx.exception, InvalidDistrict)

    async def test_find_districts_returns_only_existing_ones(self):
        schools = [{"name": "Lincoln", "slug": "lincoln"}]
        session = FakeSession({"one": schools, "two": 404, "three": [], "four": [{"name": "X", "slug": "x"}]})
        client = NutrisliceApiClient(session)

        found = await client.async_find_districts(["one", "two", "three", "four", "five"])

        self.assertEqual(found, {"one": schools, "four": [{"name": "X", "slug": "x"}]})

    async def test_find_districts_none_exist(self):
        client = NutrisliceApiClient(FakeSession({}, online=True))
        self.assertEqual(await client.async_find_districts(["a", "b", "c"]), {})

    async def test_find_districts_none_exist_and_offline(self):
        client = NutrisliceApiClient(FakeSession({}, online=False))
        with self.assertRaises(CannotConnect):
            await client.async_find_districts(["a", "b"])

    async def test_find_districts_server_error_is_surfaced_when_nothing_found(self):
        client = NutrisliceApiClient(FakeSession({"a": 500}))
        with self.assertRaises(CannotConnect):
            await client.async_find_districts(["a", "b"])

    async def test_find_districts_ignores_failures_when_something_was_found(self):
        session = FakeSession({"a": 500, "b": [{"name": "Lincoln", "slug": "lincoln"}]})
        found = await NutrisliceApiClient(session).async_find_districts(["a", "b"])
        self.assertEqual(list(found), ["b"])

    async def test_offline_check_runs_once_not_per_candidate(self):
        session = FakeSession({}, online=True)
        await NutrisliceApiClient(session).async_find_districts(["a", "b", "c", "d"])
        self.assertEqual(session.requests.count("https://api.nutrislice.com/"), 1)


class TestNutrisliceApiClient(unittest.IsolatedAsyncioTestCase):
    """Test API client HTTP operations with mocks."""

    async def test_get_schools_success(self):
        mock_schools = [
            {"id": 1, "name": "Lincoln Elementary", "slug": "lincoln-elementary"},
            {"id": 2, "name": "Burgaw Middle School", "slug": "burgaw-middle-school"},
        ]

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=mock_schools)

        mock_session = MagicMock()
        mock_session.get.return_value.__aenter__.return_value = mock_resp

        client = NutrisliceApiClient(mock_session)
        schools = await client.async_get_schools("sample-district")
        self.assertEqual(len(schools), 2)
        self.assertEqual(schools[0]["name"], "Lincoln Elementary")

    async def test_get_schools_404(self):
        mock_resp = AsyncMock()
        mock_resp.status = 404

        mock_session = MagicMock()
        mock_session.get.return_value.__aenter__.return_value = mock_resp

        client = NutrisliceApiClient(mock_session)
        with self.assertRaises(InvalidDistrict):
            await client.async_get_schools("nonexistent-district")

    async def test_get_schools_server_error(self):
        mock_resp = AsyncMock()
        mock_resp.status = 500

        mock_session = MagicMock()
        mock_session.get.return_value.__aenter__.return_value = mock_resp

        client = NutrisliceApiClient(mock_session)
        with self.assertRaises(CannotConnect):
            await client.async_get_schools("sample-district")

    async def test_get_week_menu_success(self):
        mock_menu = {
            "start_date": "2026-09-13",
            "days": [
                {"date": "2026-09-18", "menu_items": [{"text": "Pizza"}]},
            ],
        }

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=mock_menu)

        mock_session = MagicMock()
        mock_session.get.return_value.__aenter__.return_value = mock_resp

        client = NutrisliceApiClient(mock_session)
        data = await client.async_get_week_menu("sample-district", "lincoln-elementary", "lunch")
        self.assertEqual(data["start_date"], "2026-09-13")
        self.assertEqual(len(data["days"]), 1)

    async def test_get_week_menu_404(self):
        mock_resp = AsyncMock()
        mock_resp.status = 404

        mock_session = MagicMock()
        mock_session.get.return_value.__aenter__.return_value = mock_resp

        client = NutrisliceApiClient(mock_session)
        with self.assertRaises(MenuNotFound):
            await client.async_get_week_menu("sample-district", "lincoln-elementary", "invalid-menu")


if __name__ == "__main__":
    unittest.main()

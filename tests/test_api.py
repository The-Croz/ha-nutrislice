"""Unit tests for the Nutrislice API client."""
import unittest
from unittest.mock import AsyncMock, MagicMock

from tests.ha_mock import setup_ha_mocks

setup_ha_mocks()

from custom_components.nutrislice.api import (
    CannotConnect,
    InvalidDistrict,
    MenuNotFound,
    NutrisliceApiClient,
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

"""Unit tests for Nutrislice config flow."""
import unittest
from unittest.mock import AsyncMock, patch

from tests.ha_mock import MockConfigEntry, setup_ha_mocks

setup_ha_mocks()

from custom_components.nutrislice.config_flow import (
    NutrisliceConfigFlow,
    NutrisliceOptionsFlowHandler,
)


class TestNutrisliceConfigFlow(unittest.IsolatedAsyncioTestCase):
    """Test config flow steps."""

    def setUp(self):
        self.flow = NutrisliceConfigFlow()
        self.flow.hass = unittest.mock.MagicMock()

    async def test_step_user_empty_input(self):
        """Test user step with empty input shows form."""
        result = await self.flow.async_step_user(None)
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "user")

    async def test_step_user_invalid_district(self):
        """Test user step with blank district shows error."""
        result = await self.flow.async_step_user({"district": "   "})
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["errors"], {"base": "invalid_district"})

    @patch("custom_components.nutrislice.config_flow.NutrisliceApiClient")
    async def test_step_user_valid_district(self, mock_client_cls):
        """Test valid district advances to school selection step."""
        mock_client = mock_client_cls.return_value
        mock_client.async_get_schools = AsyncMock(
            return_value=[
                {"name": "Lincoln Elementary", "slug": "lincoln-elementary", "active_menu_types": []}
            ]
        )

        result = await self.flow.async_step_user({"district": "sample-district"})
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "school")
        self.assertEqual(self.flow._district, "sample-district")
        self.assertEqual(len(self.flow._schools), 1)

    @patch("custom_components.nutrislice.config_flow.NutrisliceApiClient")
    async def test_step_user_full_url_shortcut(self, mock_client_cls):
        """Test pasting full URL skips school step directly to menu types."""
        mock_client = mock_client_cls.return_value
        mock_client.async_get_schools = AsyncMock(
            return_value=[
                {
                    "name": "Lincoln Elementary",
                    "slug": "lincoln-elementary",
                    "active_menu_types": [{"name": "Lunch", "slug": "lunch"}],
                }
            ]
        )

        url = "https://sample-district.nutrislice.com/menu/lincoln-elementary/lunch"
        result = await self.flow.async_step_user({"district": url})
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "menu_types")
        self.assertEqual(self.flow._district, "sample-district")
        self.assertEqual(self.flow._selected_school["slug"], "lincoln-elementary")

    async def test_step_school_selection(self):
        """Test selecting a school advances to menu types step."""
        self.flow._district = "sample-district"
        self.flow._schools = [
            {"name": "Lincoln Elementary", "slug": "lincoln-elementary", "active_menu_types": []}
        ]

        result = await self.flow.async_step_school({"school_slug": "lincoln-elementary"})
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "menu_types")
        self.assertEqual(self.flow._selected_school["name"], "Lincoln Elementary")

    async def test_step_menu_types_creation(self):
        """Test submitting menu types creates config entry."""
        self.flow._district = "sample-district"
        self.flow._selected_school = {
            "name": "Lincoln Elementary",
            "slug": "lincoln-elementary",
            "active_menu_types": [{"name": "Lunch", "slug": "lunch"}],
        }

        result = await self.flow.async_step_menu_types({"menu_types": ["lunch"]})
        self.assertEqual(result["type"], "create_entry")
        self.assertIn("Lincoln Elementary", result["title"])
        self.assertEqual(result["data"]["district"], "sample-district")
        self.assertEqual(result["data"]["school_slug"], "lincoln-elementary")
        self.assertEqual(result["data"]["menu_types"], [{"slug": "lunch", "name": "Lunch"}])

    async def test_options_flow(self):
        """Test options flow allows changing scan interval and weekend preference."""
        entry = MockConfigEntry(
            data={"district": "sample-district", "school_slug": "lincoln-elementary"},
            options={"scan_interval_hours": 4},
        )
        opt_flow = NutrisliceOptionsFlowHandler(entry)

        # Show form
        res_form = await opt_flow.async_step_init(None)
        self.assertEqual(res_form["type"], "form")

        # Submit change
        res_submit = await opt_flow.async_step_init({"scan_interval_hours": 6, "next_school_day_on_weekend": True})
        self.assertEqual(res_submit["type"], "create_entry")
        self.assertEqual(res_submit["data"]["scan_interval_hours"], 6)


if __name__ == "__main__":
    unittest.main()

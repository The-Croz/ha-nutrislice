"""Unit tests for Nutrislice config flow."""
import unittest
from unittest.mock import AsyncMock, patch

from tests.ha_mock import MockConfigEntry, setup_ha_mocks

setup_ha_mocks()

from custom_components.nutrislice.api import CannotConnect
from custom_components.nutrislice.const import LOOKUP_URL
from custom_components.nutrislice.config_flow import (
    NutrisliceConfigFlow,
    NutrisliceOptionsFlowHandler,
)

LINCOLN = {"name": "Lincoln Elementary", "slug": "lincoln-elementary", "active_menu_types": [{"name": "Lunch", "slug": "lunch"}]}


class TestNutrisliceConfigFlow(unittest.IsolatedAsyncioTestCase):
    """Test config flow steps."""

    def setUp(self):
        self.flow = NutrisliceConfigFlow()
        self.flow.hass = unittest.mock.MagicMock()

    async def test_step_user_empty_input(self):
        """Test user step with no input shows form."""
        result = await self.flow.async_step_user(None)
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "user")
        self.assertEqual(result["description_placeholders"]["lookup_url"], LOOKUP_URL)

    async def test_step_user_nothing_entered(self):
        """Both boxes left blank asks for one of them."""
        result = await self.flow.async_step_user({"link": "  ", "district": ""})
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["errors"], {"base": "nothing_entered"})

    @patch("custom_components.nutrislice.config_flow.NutrisliceApiClient")
    async def test_step_user_name_search_lists_schools(self, mock_client_cls):
        """A district name is searched and advances to school selection."""
        mock_client = mock_client_cls.return_value
        mock_client.async_find_districts = AsyncMock(return_value={"sample-district": [LINCOLN]})

        result = await self.flow.async_step_user({"district": "Sample District Schools"})

        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "school")
        candidates = mock_client.async_find_districts.call_args.args[0]
        self.assertIn("sampledistrictschools", candidates)
        self.assertIn("sample", candidates)
        self.assertEqual(self.flow._schools_by_district, {"sample-district": [LINCOLN]})
        self.assertEqual(result["description_placeholders"]["count"], "1")

    @patch("custom_components.nutrislice.config_flow.NutrisliceApiClient")
    async def test_step_user_plain_slug_still_works(self, mock_client_cls):
        """An exact district slug is among the candidates that get checked."""
        mock_client = mock_client_cls.return_value
        mock_client.async_find_districts = AsyncMock(return_value={"sample-district": [LINCOLN]})

        result = await self.flow.async_step_user({"district": "sample-district"})

        self.assertEqual(result["step_id"], "school")
        self.assertIn("sample-district", mock_client.async_find_districts.call_args.args[0])

    @patch("custom_components.nutrislice.config_flow.NutrisliceApiClient")
    async def test_step_user_no_match_suggests_a_link(self, mock_client_cls):
        """A name that matches no district points at the link instead."""
        mock_client_cls.return_value.async_find_districts = AsyncMock(return_value={})

        result = await self.flow.async_step_user({"district": "Nowhere Unified"})

        self.assertEqual(result["step_id"], "user")
        self.assertEqual(result["errors"], {"base": "no_districts_found"})

    @patch("custom_components.nutrislice.config_flow.NutrisliceApiClient")
    async def test_step_user_cannot_connect(self, mock_client_cls):
        mock_client_cls.return_value.async_find_districts = AsyncMock(side_effect=CannotConnect("offline"))

        result = await self.flow.async_step_user({"district": "sample-district"})

        self.assertEqual(result["errors"], {"base": "cannot_connect"})

    @patch("custom_components.nutrislice.config_flow.NutrisliceApiClient")
    async def test_step_user_unknown_error(self, mock_client_cls):
        mock_client_cls.return_value.async_find_districts = AsyncMock(side_effect=RuntimeError("boom"))

        result = await self.flow.async_step_user({"district": "sample-district"})

        self.assertEqual(result["errors"], {"base": "unknown"})

    @patch("custom_components.nutrislice.config_flow.NutrisliceApiClient")
    async def test_step_user_link_is_not_name_searched(self, mock_client_cls):
        """A link checks only its own district, and a miss is reported as a bad link."""
        mock_client = mock_client_cls.return_value
        mock_client.async_find_districts = AsyncMock(return_value={})

        result = await self.flow.async_step_user(
            {"link": "https://nowhere.nutrislice.com/menu/some-school/lunch"}
        )

        self.assertEqual(mock_client.async_find_districts.call_args.args[0], ["nowhere"])
        self.assertEqual(result["errors"], {"base": "invalid_link"})

    async def test_step_user_unparseable_link(self):
        """Something that isn't a Nutrislice address is rejected as a link."""
        result = await self.flow.async_step_user({"link": "https://example.com/"})

        self.assertEqual(result["errors"], {"base": "invalid_link"})

    @patch("custom_components.nutrislice.config_flow.NutrisliceApiClient")
    async def test_step_user_full_url_shortcut(self, mock_client_cls):
        """Pasting a link to a school skips straight to menu types."""
        mock_client = mock_client_cls.return_value
        mock_client.async_find_districts = AsyncMock(return_value={"sample-district": [LINCOLN]})

        url = "https://sample-district.nutrislice.com/menu/lincoln-elementary/lunch"
        result = await self.flow.async_step_user({"link": url})

        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "menu_types")
        self.assertEqual(self.flow._district, "sample-district")
        self.assertEqual(self.flow._selected_school["slug"], "lincoln-elementary")

    @patch("custom_components.nutrislice.config_flow.NutrisliceApiClient")
    async def test_step_user_link_wins_when_both_boxes_filled(self, mock_client_cls):
        """A link is authoritative, so the name box is ignored."""
        mock_client = mock_client_cls.return_value
        mock_client.async_find_districts = AsyncMock(return_value={"sample-district": [LINCOLN]})

        await self.flow.async_step_user(
            {"link": "https://sample-district.nutrislice.com/menu", "district": "Totally Different"}
        )

        self.assertEqual(mock_client.async_find_districts.call_args.args[0], ["sample-district"])

    @patch("custom_components.nutrislice.config_flow.NutrisliceApiClient")
    async def test_step_user_url_with_unknown_school_falls_back_to_picker(self, mock_client_cls):
        mock_client = mock_client_cls.return_value
        mock_client.async_find_districts = AsyncMock(return_value={"sample-district": [LINCOLN]})

        url = "https://sample-district.nutrislice.com/menu/renamed-school/lunch"
        result = await self.flow.async_step_user({"link": url})

        self.assertEqual(result["step_id"], "school")

    async def test_step_school_selection(self):
        """Test selecting a school advances to menu types step."""
        self.flow._schools_by_district = {"sample-district": [LINCOLN]}

        result = await self.flow.async_step_school({"school_slug": "sample-district/lincoln-elementary"})

        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "menu_types")
        self.assertEqual(self.flow._district, "sample-district")
        self.assertEqual(self.flow._selected_school["name"], "Lincoln Elementary")

    async def test_step_school_picks_the_right_district_when_several_matched(self):
        """Same school slug in two districts resolves to the district that was picked."""
        other = {"name": "Lincoln Elementary", "slug": "lincoln-elementary", "active_menu_types": []}
        self.flow._schools_by_district = {"first": [LINCOLN], "second": [other]}

        await self.flow.async_step_school({"school_slug": "second/lincoln-elementary"})

        self.assertEqual(self.flow._district, "second")
        self.assertIs(self.flow._selected_school, other)

    async def test_step_school_rejects_unknown_choice(self):
        self.flow._schools_by_district = {"sample-district": [LINCOLN]}

        result = await self.flow.async_step_school({"school_slug": "sample-district/missing"})

        self.assertEqual(result["step_id"], "school")
        self.assertEqual(result["errors"], {"base": "school_not_found"})

    async def test_step_school_options_name_district_only_when_several(self):
        """Schools are labelled with their district only when the search matched more than one."""
        maple = {"name": "Maple Middle", "slug": "maple-middle"}
        with patch("custom_components.nutrislice.config_flow.selector.SelectSelectorConfig") as config:
            self.flow._schools_by_district = {"only": [LINCOLN, maple]}
            await self.flow.async_step_school(None)
            single = config.call_args.kwargs["options"]

            self.flow._schools_by_district = {"first": [LINCOLN], "second": [maple]}
            await self.flow.async_step_school(None)
            several = config.call_args.kwargs["options"]

        self.assertEqual([o["label"] for o in single], ["Lincoln Elementary", "Maple Middle"])
        self.assertEqual(
            [(o["value"], o["label"]) for o in several],
            [
                ("first/lincoln-elementary", "Lincoln Elementary (first)"),
                ("second/maple-middle", "Maple Middle (second)"),
            ],
        )

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
        """Test options flow allows changing scan interval, weekend preference, and sync calendar."""
        entry = MockConfigEntry(
            data={"district": "sample-district", "school_slug": "lincoln-elementary"},
            options={"scan_interval_hours": 4},
        )
        opt_flow = NutrisliceOptionsFlowHandler()
        opt_flow.config_entry = entry

        # Show form
        res_form = await opt_flow.async_step_init(None)
        self.assertEqual(res_form["type"], "form")

        # Submit change
        res_submit = await opt_flow.async_step_init(
            {
                "scan_interval_hours": 6,
                "next_school_day_on_weekend": True,
                "sync_calendar": "calendar.family",
            }
        )
        self.assertEqual(res_submit["type"], "create_entry")
        self.assertEqual(res_submit["data"]["scan_interval_hours"], 6)
        self.assertEqual(res_submit["data"]["sync_calendar"], "calendar.family")


if __name__ == "__main__":
    unittest.main()

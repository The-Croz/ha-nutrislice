"""Unit tests for Nutrislice sensors."""
from datetime import date, datetime
import unittest

from tests.ha_mock import MockConfigEntry, setup_ha_mocks

setup_ha_mocks()

from custom_components.nutrislice.coordinator import (
    NutrisliceMenuData,
    ParsedDayMenu,
    ParsedFoodItem,
)
from custom_components.nutrislice.sensor import (
    NutrisliceFullMenuSensor,
    NutrisliceTodayMenuSensor,
    NutrisliceTomorrowMenuSensor,
)


class MockCoordinator:
    """Mock coordinator for sensor tests."""

    def __init__(self, data=None):
        self.district = "sample-district"
        self.school_slug = "lincoln-elementary"
        self.school_name = "Lincoln Elementary"
        self.data = data or {}


class TestNutrisliceSensors(unittest.TestCase):
    """Test sensor behavior and attributes."""

    def setUp(self):
        self.today_date = date.today()
        self.today_str = self.today_date.isoformat()

        today_menu = ParsedDayMenu(
            date_str=self.today_str,
            target_date=self.today_date,
            is_holiday=False,
            has_menu=True,
            entrees=["Cheeseburger", "Cheese Pizza"],
            sides=["Apple"],
            beverages=["Milk"],
            condiments=["Ketchup"],
            items=[
                ParsedFoodItem(
                    name="Cheeseburger",
                    category="sandwich",
                    section="Entree",
                    is_entree=True,
                    is_side=False,
                    calories=360.0,
                )
            ],
            raw_day={"date": self.today_str, "menu_items": []},
        )

        tomorrow_menu = ParsedDayMenu(
            date_str="2026-09-19",
            target_date=date(2026, 9, 19),
            is_holiday=False,
            has_menu=True,
            entrees=["Tacos"],
            sides=["Corn"],
            raw_day={"date": "2026-09-19", "menu_items": []},
        )

        self.menu_data = NutrisliceMenuData(
            district="sample-district",
            school_slug="lincoln-elementary",
            school_name="Lincoln Elementary",
            menu_type_slug="lunch",
            menu_type_name="Lunch",
            days=[today_menu.raw_day, tomorrow_menu.raw_day],
            days_by_date={self.today_str: today_menu, "2026-09-19": tomorrow_menu},
            today=today_menu,
            tomorrow=tomorrow_menu,
            next_school_day=tomorrow_menu,
            last_updated=datetime(2026, 9, 18, 12, 0, 0),
        )

        self.mock_coord = MockCoordinator(data={"lunch": self.menu_data})
        self.mock_entry = MockConfigEntry(
            data={"district": "sample-district", "school_slug": "lincoln-elementary"},
            options={},
        )

    def test_today_sensor(self):
        sensor = NutrisliceTodayMenuSensor(self.mock_coord, self.mock_entry, "lunch")
        self.assertEqual(sensor.native_value, "Cheeseburger, Cheese Pizza")
        attrs = sensor.extra_state_attributes
        self.assertEqual(attrs["date"], self.today_str)
        self.assertEqual(attrs["entrees"], ["Cheeseburger", "Cheese Pizza"])
        self.assertEqual(attrs["sides"], ["Apple"])
        self.assertEqual(attrs["school_name"], "Lincoln Elementary")
        self.assertEqual(len(attrs["menu_items"]), 1)
        self.assertEqual(attrs["menu_items"][0]["calories"], 360.0)

    def test_tomorrow_sensor(self):
        sensor = NutrisliceTomorrowMenuSensor(self.mock_coord, self.mock_entry, "lunch")
        self.assertEqual(sensor.native_value, "Tacos")
        attrs = sensor.extra_state_attributes
        self.assertEqual(attrs["date"], "2026-09-19")
        self.assertEqual(attrs["entrees"], ["Tacos"])

    def test_full_menu_legacy_sensor(self):
        sensor = NutrisliceFullMenuSensor(self.mock_coord, self.mock_entry, "lunch")
        self.assertEqual(sensor.native_value, self.today_str)
        attrs = sensor.extra_state_attributes
        self.assertIn("days", attrs)
        self.assertEqual(len(attrs["days"]), 2)
        self.assertEqual(attrs["school_name"], "Lincoln Elementary")


if __name__ == "__main__":
    unittest.main()

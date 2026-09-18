"""Unit tests for the Nutrislice coordinator and data parser."""
from datetime import date
import unittest

from tests.ha_mock import setup_ha_mocks

setup_ha_mocks()

from custom_components.nutrislice.coordinator import (
    NutrisliceMenuData,
    ParsedDayMenu,
    parse_day,
)


class TestNutrisliceCoordinatorParser(unittest.TestCase):
    """Test menu parsing and classification logic."""

    def test_parse_day_with_real_menu_items(self):
        """Test parsing day payload with entrees, sides, milk, and condiments."""
        raw_day = {
            "date": "2026-09-18",
            "is_holiday": False,
            "menu_items": [
                # Entree section
                {"is_section_title": True, "text": "Entree"},
                {
                    "food": {
                        "name": "Cheeseburger",
                        "food_category": "sandwich",
                        "rounded_nutrition_info": {"calories": 360.0},
                        "icons": {"food_icons": [{"name": "Milk"}, {"name": "Wheat"}]},
                    }
                },
                {
                    "food": {
                        "name": "Cheese Pizza",
                        "food_category": "pizza",
                        "rounded_nutrition_info": {"calories": 320.0},
                    }
                },
                # Fruit / Side section
                {"is_section_title": True, "text": "Fruit"},
                {
                    "food": {
                        "name": "Red Delicious Apple",
                        "food_category": "side",
                    }
                },
                # Vegetable section
                {"is_section_title": True, "text": "Vegetable"},
                {
                    "food": {
                        "name": "Fresh Cucumber Slices",
                        "food_category": "side",
                    }
                },
                # Milk section
                {"is_section_title": True, "text": "Milk"},
                {
                    "food": {
                        "name": "Chocolate Skim Milk",
                        "food_category": "beverage",
                    }
                },
                # Condiments
                {"is_section_title": True, "text": "Condiments"},
                {
                    "food": {
                        "name": "Ketchup",
                        "food_category": "condiment",
                    }
                },
            ],
        }

        parsed: ParsedDayMenu = parse_day(raw_day)

        self.assertEqual(parsed.date_str, "2026-09-18")
        self.assertEqual(parsed.target_date, date(2026, 9, 18))
        self.assertFalse(parsed.is_holiday)
        self.assertTrue(parsed.has_menu)

        # Verify entrees
        self.assertIn("Cheeseburger", parsed.entrees)
        self.assertIn("Cheese Pizza", parsed.entrees)
        self.assertEqual(len(parsed.entrees), 2)

        # Verify sides
        self.assertIn("Red Delicious Apple", parsed.sides)
        self.assertIn("Fresh Cucumber Slices", parsed.sides)

        # Verify beverages and condiments
        self.assertIn("Chocolate Skim Milk", parsed.beverages)
        self.assertIn("Ketchup", parsed.condiments)

        # Verify summary
        self.assertEqual(parsed.summary, "Cheeseburger, Cheese Pizza")

        # Verify formatted description
        desc = parsed.formatted_description
        self.assertIn("Cheeseburger", desc)
        self.assertIn("Red Delicious Apple", desc)
        self.assertIn("Chocolate Skim Milk", desc)

        # Verify individual parsed item details
        cheeseburger_item = next(i for i in parsed.items if i.name == "Cheeseburger")
        self.assertTrue(cheeseburger_item.is_entree)
        self.assertEqual(cheeseburger_item.calories, 360.0)
        self.assertEqual(cheeseburger_item.allergens, ["Milk", "Wheat"])

    def test_parse_day_empty_menu(self):
        """Test parsing weekend or holiday with no menu items."""
        raw_day = {
            "date": "2026-09-19",
            "is_holiday": False,
            "menu_items": [],
        }

        parsed = parse_day(raw_day)
        self.assertFalse(parsed.has_menu)
        self.assertEqual(parsed.entrees, [])
        self.assertEqual(parsed.summary, "No Menu Scheduled")

    def test_parse_day_long_summary_truncation(self):
        """Test summary truncates properly to prevent Home Assistant 255-char state limit."""
        raw_day = {
            "date": "2026-09-20",
            "menu_items": [
                {"is_section_title": True, "text": "Entree"},
            ]
            + [
                {"food": {"name": f"Super Long Entree Item Option Number {i} With Extra Description", "food_category": "entree"}}
                for i in range(15)
            ],
        }

        parsed = parse_day(raw_day)
        self.assertLessEqual(len(parsed.summary), 250)
        self.assertTrue(parsed.summary.endswith("..."))


if __name__ == "__main__":
    unittest.main()

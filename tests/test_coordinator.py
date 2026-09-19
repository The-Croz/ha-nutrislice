"""Unit tests for the Nutrislice coordinator and data parser."""
from datetime import date
import unittest

from tests.ha_mock import setup_ha_mocks

setup_ha_mocks()

from custom_components.nutrislice.coordinator import (
    NutrisliceMenuData,
    ParsedDayMenu,
    calendar_title_prefix,
    classify_item,
    parse_day,
)


def item(name, category):
    return {"food": {"name": name, "food_category": category}}


def section(text):
    return {"is_section_title": True, "text": text}


# A real Pender County Schools (greatschools) lunch, 2026-09-21
REAL_LUNCH = {
    "date": "2026-09-21",
    "menu_items": [
        section("Daily Serve Entree"),
        item("Peanut Butter & Jelly Sandwich", "sandwich"),
        section("Entree"),
        item("Fresh Baked Breadstick", "side"),
        item("Salisbury Steak", "entree"),
        item("Beef Gravy", "sauce_grvy"),
        item("Pepperoni Pizza", "pizza"),
        section("Express"),
        item("Egg Chef Salad", "salad"),
        item("Dinner Roll", "side"),
        section("Fruit"),
        item("Red Delicious Apple", "side"),
        item("Fruit Juice", "beverage"),
        section("Vegetable"),
        item("Mashed Potatoes", "side"),
        section("Milk"),
        item("1% Milk", "beverage"),
        section("Condiments"),
        item("Ketchup", "condiment"),
    ],
}


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


class TestEventTitleSections(unittest.TestCase):
    """The courses chosen in the options decide what an event title shows."""

    def setUp(self):
        self.day = parse_day(REAL_LUNCH)

    def test_default_is_entrees_with_meal_emoji(self):
        self.assertEqual(
            self.day.calendar_summary("Lunch"),
            "🍽️ Lunch: Peanut Butter & Jelly Sandwich, Salisbury Steak, Pepperoni Pizza, Egg Chef Salad",
        )
        self.assertEqual(self.day.calendar_summary("Lunch", ["entrees"]), self.day.calendar_summary("Lunch"))

    def test_several_courses_each_led_by_their_emoji(self):
        self.assertEqual(
            self.day.calendar_summary("Lunch", ["entrees", "sides", "fruits"]),
            "Lunch: 🍽️ Peanut Butter & Jelly Sandwich, Salisbury Steak, Pepperoni Pizza, Egg Chef Salad"
            " 🥖 Fresh Baked Breadstick, Dinner Roll 🍎 Red Delicious Apple",
        )

    def test_courses_follow_menu_order_not_selection_order(self):
        self.assertEqual(
            self.day.calendar_summary("Lunch", ["beverages", "vegetables"]),
            "Lunch: 🥦 Mashed Potatoes 🥛 Fruit Juice, 1% Milk",
        )

    def test_empty_course_is_skipped(self):
        no_veg = parse_day({**REAL_LUNCH, "menu_items": [i for i in REAL_LUNCH["menu_items"] if i.get("text") != "Vegetable" and (i.get("food") or {}).get("name") != "Mashed Potatoes"]})
        self.assertEqual(no_veg.calendar_summary("Lunch", ["vegetables", "fruits"]), "Lunch: 🍎 Red Delicious Apple")

    def test_nothing_selected_shows_just_the_meal(self):
        self.assertEqual(self.day.calendar_summary("Lunch", []), "🍽️ Lunch")
        self.assertEqual(self.day.calendar_summary("Breakfast", []), "🥞 Breakfast")


class TestClassification(unittest.TestCase):
    """Items are grouped by their own category before the section they're listed under."""

    def test_real_menu_entrees_are_only_the_mains(self):
        parsed = parse_day(REAL_LUNCH)
        self.assertEqual(
            parsed.entrees,
            ["Peanut Butter & Jelly Sandwich", "Salisbury Steak", "Pepperoni Pizza", "Egg Chef Salad"],
        )

    def test_breads_under_entree_headings_are_sides(self):
        parsed = parse_day(REAL_LUNCH)
        self.assertIn("Fresh Baked Breadstick", parsed.sides)
        self.assertIn("Dinner Roll", parsed.sides)

    def test_gravy_is_a_condiment(self):
        self.assertEqual(parse_day(REAL_LUNCH).condiments, ["Beef Gravy", "Ketchup"])

    def test_juice_listed_under_fruit_is_a_beverage(self):
        self.assertEqual(parse_day(REAL_LUNCH).beverages, ["Fruit Juice", "1% Milk"])

    def test_fruit_and_vegetables_split_out_of_sides(self):
        parsed = parse_day(REAL_LUNCH)
        self.assertEqual(parsed.fruits, ["Red Delicious Apple"])
        self.assertEqual(parsed.vegetables, ["Mashed Potatoes"])
        # sides still holds everything, so existing templates keep working
        self.assertEqual(
            parsed.sides,
            ["Fresh Baked Breadstick", "Dinner Roll", "Red Delicious Apple", "Mashed Potatoes"],
        )

    def test_description_groups_with_emoji_headings(self):
        self.assertEqual(
            parse_day(REAL_LUNCH).formatted_description,
            "🍽️ Entrees:\n• Peanut Butter & Jelly Sandwich\n• Salisbury Steak\n• Pepperoni Pizza\n• Egg Chef Salad"
            "\n\n🥖 Sides:\n• Fresh Baked Breadstick\n• Dinner Roll"
            "\n\n🍎 Fruit:\n• Red Delicious Apple"
            "\n\n🥦 Vegetables:\n• Mashed Potatoes"
            "\n\n🥛 Beverages:\n• Fruit Juice\n• 1% Milk",
        )

    def test_event_title_lists_only_entrees_with_emoji(self):
        self.assertEqual(
            parse_day(REAL_LUNCH).calendar_summary("Lunch"),
            "🍽️ Lunch: Peanut Butter & Jelly Sandwich, Salisbury Steak, Pepperoni Pizza, Egg Chef Salad",
        )

    def test_salad_depends_on_section(self):
        self.assertEqual(classify_item("salad", "express"), "entree")
        self.assertEqual(classify_item("salad", "vegetable"), "side")

    def test_section_decides_when_category_is_missing(self):
        self.assertEqual(classify_item("", "entree"), "entree")
        self.assertEqual(classify_item("", "milk"), "beverage")
        self.assertEqual(classify_item("", "condiments"), "condiment")
        self.assertEqual(classify_item("", "fruit"), "side")

    def test_menu_emoji(self):
        self.assertEqual(calendar_title_prefix("Lunch"), "🍽️ Lunch: ")
        self.assertEqual(calendar_title_prefix("Preschool Breakfast"), "🥞 Preschool Breakfast: ")
        self.assertEqual(calendar_title_prefix("After School Snack Menu"), "🍪 After School Snack Menu: ")


if __name__ == "__main__":
    unittest.main()

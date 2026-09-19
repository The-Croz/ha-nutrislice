"""Unit tests for Nutrislice sensors."""
from datetime import date, datetime
import types
import unittest

from tests.ha_mock import MockConfigEntry, setup_ha_mocks

setup_ha_mocks()

from custom_components.nutrislice.coordinator import (
    menu_entity_name,
    NutrisliceMenuData,
    ParsedDayMenu,
    ParsedFoodItem,
)
from custom_components.nutrislice.sensor import (
    _async_remove_raw_menu_entities,
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


class TestSensorStateSections(unittest.TestCase):
    """The event-title course checkboxes also decide the Today and Tomorrow sensor states."""

    def setUp(self):
        today = date.today()
        self.today = ParsedDayMenu(
            date_str=today.isoformat(),
            target_date=today,
            is_holiday=False,
            has_menu=True,
            entrees=["Cheeseburger", "Cheese Pizza"],
            sides=["Breadstick", "Apple", "Carrots"],
            fruits=["Apple"],
            vegetables=["Carrots"],
            beverages=["Milk"],
            raw_day={"date": today.isoformat()},
        )
        self.menu_data = NutrisliceMenuData(
            district="sample-district",
            school_slug="lincoln-elementary",
            school_name="Lincoln Elementary",
            menu_type_slug="lunch",
            menu_type_name="Lunch",
            days_by_date={self.today.date_str: self.today},
            today=self.today,
            tomorrow=self.today,
            next_school_day=None,
            last_updated=datetime(2026, 9, 18, 12, 0, 0),
        )
        self.coord = MockCoordinator(data={"lunch": self.menu_data})

    def states(self, **options):
        entry = MockConfigEntry(options=options)
        return (
            NutrisliceTodayMenuSensor(self.coord, entry, "lunch").native_value,
            NutrisliceTomorrowMenuSensor(self.coord, entry, "lunch").native_value,
        )

    def test_default_is_unchanged_entree_list(self):
        self.assertEqual(self.states(), ("Cheeseburger, Cheese Pizza",) * 2)

    def test_chosen_courses_each_led_by_emoji(self):
        expected = "🍽️ Cheeseburger, Cheese Pizza 🥖 Breadstick 🍎 Apple"
        self.assertEqual(
            self.states(title_sections=["entrees", "sides", "fruits"]), (expected, expected)
        )

    def test_state_matches_the_calendar_title_minus_the_menu_name(self):
        sections = ["entrees", "vegetables", "beverages"]
        title = self.today.calendar_summary("Lunch", sections)
        self.assertEqual(title, "Lunch: " + self.states(title_sections=sections)[0])

    def test_no_courses_selected_shows_the_meal_name(self):
        self.assertEqual(self.states(title_sections=[]), ("🍽️ Lunch",) * 2)

    def test_no_menu_is_always_no_menu_scheduled(self):
        """Automations rely on this exact value whatever the courses setting."""
        self.menu_data.today = self.menu_data.tomorrow = ParsedDayMenu(
            date_str="2026-09-19", target_date=date(2026, 9, 19), is_holiday=False, has_menu=False
        )
        for sections in (["entrees"], ["entrees", "sides"], []):
            with self.subTest(sections=sections):
                self.assertEqual(self.states(title_sections=sections), ("No Menu Scheduled",) * 2)

    def test_long_states_fit_home_assistants_limit(self):
        """Home Assistant rejects states over 255 characters."""
        self.today.entrees = [f"Entree number {i} with a long name" for i in range(12)]
        self.today.sides = self.today.fruits = [f"Fruit number {i} with a long name" for i in range(12)]
        self.today.vegetables = [f"Vegetable number {i} with a long name" for i in range(12)]
        state = self.states(title_sections=["entrees", "fruits", "vegetables", "beverages"])[0]
        self.assertLessEqual(len(state), 255)
        self.assertTrue(state.endswith("..."))

    def test_attributes_are_unaffected_by_the_setting(self):
        entry = MockConfigEntry(options={"title_sections": []})
        attrs = NutrisliceTodayMenuSensor(self.coord, entry, "lunch").extra_state_attributes
        self.assertEqual(attrs["entrees"], ["Cheeseburger", "Cheese Pizza"])
        self.assertEqual(attrs["fruits"], ["Apple"])


class TestMenuMarkdownAttribute(unittest.TestCase):
    """Today and Tomorrow carry the whole menu pre-formatted for a Markdown dashboard card."""

    def setUp(self):
        today = date.today()
        self.day = ParsedDayMenu(
            date_str=today.isoformat(),
            target_date=today,
            is_holiday=False,
            has_menu=True,
            entrees=["Cheeseburger", "Cheese Pizza"],
            sides=["Breadstick", "Apple"],
            fruits=["Apple"],
            beverages=["Milk"],
            condiments=["Ketchup"],
            raw_day={"date": today.isoformat()},
        )
        self.menu_data = NutrisliceMenuData(
            district="d", school_slug="s", school_name="Lincoln Elementary",
            menu_type_slug="lunch", menu_type_name="Lunch",
            days_by_date={self.day.date_str: self.day},
            today=self.day, tomorrow=self.day, next_school_day=None,
            last_updated=datetime(2026, 9, 18, 12, 0, 0),
        )
        self.coord = MockCoordinator(data={"lunch": self.menu_data})
        self.entry = MockConfigEntry()

    EXPECTED = (
        "**🍽️ Entrees**\n- Cheeseburger\n- Cheese Pizza\n\n"
        "**🥖 Sides**\n- Breadstick\n\n"
        "**🍎 Fruit**\n- Apple\n\n"
        "**🥛 Beverages**\n- Milk"
    )

    def test_today_and_tomorrow_have_it(self):
        for sensor in (NutrisliceTodayMenuSensor, NutrisliceTomorrowMenuSensor):
            with self.subTest(sensor=sensor.__name__):
                attrs = sensor(self.coord, self.entry, "lunch").extra_state_attributes
                self.assertEqual(attrs["menu_markdown"], self.EXPECTED)

    def test_is_not_affected_by_the_title_courses_setting(self):
        """The attribute is the full menu; only the state follows the checkboxes."""
        entry = MockConfigEntry(options={"title_sections": []})
        attrs = NutrisliceTodayMenuSensor(self.coord, entry, "lunch").extra_state_attributes
        self.assertEqual(attrs["menu_markdown"], self.EXPECTED)

    def test_condiments_are_left_out(self):
        attrs = NutrisliceTodayMenuSensor(self.coord, self.entry, "lunch").extra_state_attributes
        self.assertNotIn("Ketchup", attrs["menu_markdown"])

    def test_no_menu_gives_a_friendly_line_not_none(self):
        """A card templating this attribute must never render 'None'."""
        self.menu_data.today = None
        self.menu_data.tomorrow = None
        for sensor in (NutrisliceTodayMenuSensor, NutrisliceTomorrowMenuSensor):
            with self.subTest(sensor=sensor.__name__):
                attrs = sensor(self.coord, self.entry, "lunch").extra_state_attributes
                self.assertEqual(attrs["menu_markdown"], "No menu scheduled")

    def test_today_keeps_todays_date_when_there_is_no_menu(self):
        self.menu_data.today = None
        attrs = NutrisliceTodayMenuSensor(self.coord, self.entry, "lunch").extra_state_attributes
        self.assertEqual(attrs["date"], date.today().isoformat())

    def test_tomorrow_reports_whether_it_is_the_next_school_day(self):
        attrs = NutrisliceTomorrowMenuSensor(self.coord, self.entry, "lunch").extra_state_attributes
        self.assertIs(attrs["is_next_school_day"], False)


class FakeRegistry:
    """Just enough entity registry to test stale-entity cleanup."""

    def __init__(self, entities):
        self.entities = dict(entities)  # (domain, platform, unique_id) -> entity_id
        self.removed = []

    def async_get_entity_id(self, domain, platform, unique_id):
        return self.entities.get((domain, platform, unique_id))

    def async_remove(self, entity_id):
        self.removed.append(entity_id)


class TestRawMenuEntityCleanup(unittest.TestCase):
    """The raw Menu sensor from earlier releases is removed instead of left unavailable."""

    def test_removes_the_old_menu_sensor_and_nothing_else(self):
        registry = FakeRegistry({
            ("sensor", "nutrislice", "d_s_lunch_menu"): "sensor.school_lunch_menu",
            ("sensor", "nutrislice", "d_s_lunch_today"): "sensor.school_lunch_today",
        })
        hass = types.SimpleNamespace(entity_registry=registry)
        coord = MockCoordinator(data={"lunch": object()})
        coord.district, coord.school_slug = "d", "s"

        _async_remove_raw_menu_entities(hass, coord)

        self.assertEqual(registry.removed, ["sensor.school_lunch_menu"])

    def test_covers_every_menu_type(self):
        registry = FakeRegistry({
            ("sensor", "nutrislice", "d_s_lunch_menu"): "sensor.lunch_menu",
            ("sensor", "nutrislice", "d_s_breakfast_menu"): "sensor.breakfast_menu",
        })
        hass = types.SimpleNamespace(entity_registry=registry)
        coord = MockCoordinator(data={"lunch": object(), "breakfast": object()})
        coord.district, coord.school_slug = "d", "s"

        _async_remove_raw_menu_entities(hass, coord)

        self.assertEqual(sorted(registry.removed), ["sensor.breakfast_menu", "sensor.lunch_menu"])

    def test_nothing_to_remove_on_a_fresh_install(self):
        registry = FakeRegistry({})
        coord = MockCoordinator(data={"lunch": object()})
        coord.district, coord.school_slug = "d", "s"

        _async_remove_raw_menu_entities(types.SimpleNamespace(entity_registry=registry), coord)

        self.assertEqual(registry.removed, [])


class TestEntityNaming(unittest.TestCase):
    """Test that entity names never repeat what the device name already says."""

    def test_plain_school_name_keeps_the_menu_name(self):
        self.assertEqual(menu_entity_name("Surf City Elementary", "Lunch"), "Lunch")
        self.assertEqual(menu_entity_name("Surf City Elementary", "Lunch", "Today"), "Lunch Today")

    def test_school_name_ending_in_menu_name_drops_it(self):
        """A device called "Surf City Elementary Lunch" must not read "... Lunch Lunch"."""
        self.assertIsNone(menu_entity_name("Surf City Elementary Lunch", "Lunch"))
        self.assertEqual(menu_entity_name("Surf City Elementary Lunch", "Lunch", "Today"), "Today")

    def test_dedupe_ignores_case_and_surrounding_space(self):
        self.assertIsNone(menu_entity_name("Surf City Elementary LUNCH ", " Lunch "))

    def test_menu_name_only_matched_at_the_end(self):
        """"Lunch Bunch Academy" doesn't end with "Lunch", so nothing is dropped."""
        self.assertEqual(menu_entity_name("Lunch Bunch Academy", "Lunch"), "Lunch")

    def test_partial_word_is_not_treated_as_a_match(self):
        """A school whose name merely *ends in* the letters of the menu keeps it."""
        self.assertEqual(menu_entity_name("Deerlunch", "Lunch", "Today"), "Lunch Today")
        self.assertEqual(menu_entity_name("Brunch", "Lunch"), "Lunch")

    def test_school_named_exactly_the_menu_name(self):
        self.assertIsNone(menu_entity_name("Lunch", "Lunch"))


if __name__ == "__main__":
    unittest.main()

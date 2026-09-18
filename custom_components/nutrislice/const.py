"""Constants for the Nutrislice integration."""
from __future__ import annotations

import logging
from typing import Final

DOMAIN: Final = "nutrislice"
LOGGER = logging.getLogger(__package__)

CONF_DISTRICT: Final = "district"
CONF_SCHOOL_SLUG: Final = "school_slug"
CONF_SCHOOL_NAME: Final = "school_name"
CONF_MENU_TYPES: Final = "menu_types"
CONF_SCAN_INTERVAL_HOURS: Final = "scan_interval_hours"
CONF_NEXT_SCHOOL_DAY_ON_WEEKEND: Final = "next_school_day_on_weekend"
CONF_SYNC_CALENDAR: Final = "sync_calendar"

SERVICE_SYNC_CALENDAR: Final = "sync_calendar"

LOOKUP_URL: Final = "https://lookup.nutrislice.com"

DEFAULT_SCAN_INTERVAL_HOURS: Final = 4
DEFAULT_UPCOMING_WEEKS: Final = 2
DEFAULT_NEXT_SCHOOL_DAY_ON_WEEKEND: Final = True

ATTR_DAYS: Final = "days"
ATTR_DATE: Final = "date"
ATTR_ENTREES: Final = "entrees"
ATTR_SIDES: Final = "sides"
ATTR_MENU_ITEMS: Final = "menu_items"
ATTR_CATEGORIES: Final = "categories"
ATTR_SCHOOL_NAME: Final = "school_name"
ATTR_MENU_TYPE: Final = "menu_type"
ATTR_DISTRICT: Final = "district"
ATTR_LAST_UPDATED: Final = "last_updated"

# Entree category tags & section keywords for classifying items
ENTREE_FOOD_CATEGORIES: Final = {
    "entree",
    "sandwich",
    "pizza",
    "burger",
    "taco",
    "burrito",
    "wrap",
    "main",
}

ENTREE_SECTION_KEYWORDS: Final = (
    "entree",
    "main",
    "daily serve",
    "hot meal",
    "lunch entree",
    "breakfast entree",
    "pizza",
    "grill",
    "pop up",
    "promotions",
    "express",
)

SIDE_SECTION_KEYWORDS: Final = (
    "fruit",
    "vegetable",
    "side",
    "salad",
    "dessert",
)

IGNORE_SECTION_KEYWORDS: Final = (
    "condiment",
    "milk",
    "beverage",
    "dressing",
    "dip",
)

"""Tests for translation files, mirroring the rules hassfest enforces."""
import json
from pathlib import Path
import re
import unittest

COMPONENT = Path(__file__).parent.parent / "custom_components" / "nutrislice"
STRINGS = COMPONENT / "strings.json"
TRANSLATIONS = COMPONENT / "translations" / "en.json"


def walk_strings(node, path=""):
    """Yield every (path, string) pair in a nested translation structure."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield from walk_strings(value, f"{path}.{key}" if path else key)
    elif isinstance(node, str):
        yield path, node


class TestTranslations(unittest.TestCase):
    """Validate translation files before hassfest does it in CI."""

    def test_no_literal_urls(self):
        """hassfest rejects URLs in strings; they must be description placeholders."""
        for path in (STRINGS, TRANSLATIONS):
            for key, value in walk_strings(json.loads(path.read_text())):
                with self.subTest(file=path.name, key=key):
                    self.assertIsNone(
                        re.search(r"https?://", value),
                        f"{key} contains a literal URL: {value!r}",
                    )

    def test_strings_and_translations_match(self):
        """en.json must stay in sync with strings.json."""
        self.assertEqual(json.loads(STRINGS.read_text()), json.loads(TRANSLATIONS.read_text()))

    def test_every_placeholder_is_supplied_by_the_flow(self):
        """Every {placeholder} in a step must be one the config flow passes."""
        supplied = {
            "user": {"lookup_url", "example_url"},
            "school": {"count", "districts", "district"},
            "menu_types": {"school_name"},
            "init": set(),
        }
        strings = json.loads(STRINGS.read_text())
        for section in ("config", "options"):
            for step, body in strings.get(section, {}).get("step", {}).items():
                for key, value in walk_strings(body):
                    for placeholder in re.findall(r"\{(\w+)\}", value):
                        with self.subTest(step=step, key=key):
                            self.assertIn(placeholder, supplied[step])


if __name__ == "__main__":
    unittest.main()

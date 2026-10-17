import importlib.util
import sys
import types
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

SKIN_ROOT = Path(__file__).resolve().parents[1]


def load_letter_jump(letters):
    """Load letter_jump.py against a fake xbmc whose list holds the given sort letters."""
    xbmc = types.ModuleType("xbmc")
    xbmc.getInfoLabel = lambda label: letters[int(label.split("(")[1].split(")")[0])]
    sys.modules["xbmc"] = xbmc
    spec = importlib.util.spec_from_file_location("letter_jump", SKIN_ROOT / "letter_jump.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LetterJumpTests(unittest.TestCase):
    # The Living Room movie list starts with three digit titles in non-sorted letter order.
    LETTERS = list("212AAABBC") + ["é", "D"]

    def target(self, direction, current):
        module = load_letter_jump(self.LETTERS)
        return module.target_index(direction, current, len(self.LETTERS) - 1, 0)

    def test_digits_are_one_group(self):
        self.assertEqual(3, self.target("next", 0))
        self.assertEqual(3, self.target("next", 1))
        self.assertEqual(0, self.target("prev", 3))

    def test_next_and_prev_step_one_letter_group(self):
        self.assertEqual(6, self.target("next", 3))
        self.assertEqual(3, self.target("prev", 6))
        self.assertEqual(3, self.target("prev", 4))

    def test_non_latin_letters_count_as_hash(self):
        self.assertEqual(9, self.target("next", 8))
        self.assertEqual(10, self.target("next", 9))

    def test_ends_do_not_move(self):
        self.assertEqual(0, self.target("prev", 0))
        self.assertEqual(10, self.target("next", 10))

    def test_strip_has_no_focus_loop(self):
        # Kodi caches conditions per frame, so a hidden-button focus loop that re-checks
        # the letter never sees the change and spins the GUI thread forever.
        views = ET.parse(SKIN_ROOT / "1080i" / "Includes_Views.xml").getroot()
        ids = {node.findtext("param[@name='id']") for node in views.iter("include")}
        self.assertNotIn("613", ids)
        self.assertNotIn("614", ids)
        text = (SKIN_ROOT / "1080i" / "Includes_Views.xml").read_text(encoding="utf-8")
        self.assertNotIn("Action(NextLetter)", text)
        self.assertNotIn("Action(PrevLetter)", text)
        self.assertEqual(4, text.count("RunScript(special://skin/letter_jump.py"))


if __name__ == "__main__":
    unittest.main()

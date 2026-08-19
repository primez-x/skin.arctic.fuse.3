import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


SKIN_ROOT = Path(__file__).resolve().parents[1]


class ShortcutRebuildMarkerTests(unittest.TestCase):
    def test_shortcut_window_does_not_change_rebuild_marker_during_reload(self):
        root = ET.parse(
            SKIN_ROOT / "1080i" / "Custom_1115_Window_Shortcuts.xml"
        ).getroot()

        onloads = "\n".join(element.text or "" for element in root.findall("onload"))

        self.assertNotIn("Shortcuts.RebuildDateTime", onloads)

    def test_shortcut_editor_marks_rebuild_after_edit(self):
        root = ET.parse(
            SKIN_ROOT / "1080i" / "Custom_1116_Dialog_Shortcuts.xml"
        ).getroot()

        onunloads = "\n".join(
            element.text or "" for element in root.findall("onunload")
        )

        self.assertIn("Skin.SetString(Shortcuts.RebuildDateTime", onunloads)


if __name__ == "__main__":
    unittest.main()

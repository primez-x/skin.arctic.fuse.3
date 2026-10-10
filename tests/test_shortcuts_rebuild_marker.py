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

    def test_direct_shortcut_window_mutations_mark_rebuild(self):
        root = ET.parse(
            SKIN_ROOT / "1080i" / "Custom_1115_Window_Shortcuts.xml"
        ).getroot()
        mutation_tokens = (
            "Skin.SetString(",
            "Skin.Reset(",
            "Skin.ToggleSetting(",
        )

        mutation_items = []
        for item in root.findall(".//item"):
            onclicks = [element.text or "" for element in item.findall("onclick")]
            if any(token in onclick for onclick in onclicks for token in mutation_tokens):
                mutation_items.append("\n".join(onclicks))

        self.assertEqual(len(mutation_items), 5)
        self.assertTrue(
            all(
                "Skin.SetString(Shortcuts.RebuildDateTime" in onclicks
                for onclicks in mutation_items
            )
        )

    def test_nested_shortcut_settings_commit_through_editor_session(self):
        editor = ET.parse(
            SKIN_ROOT / "1080i" / "Custom_1116_Dialog_Shortcuts.xml"
        ).getroot()
        editor_includes = [
            element.text or "" for element in editor.findall(".//include")
        ]
        dialog = (
            SKIN_ROOT / "1080i" / "Dialog_DialogShortcuts.xml"
        ).read_text(encoding="utf-8")

        self.assertIn("DialogShortcuts", editor_includes)
        self.assertIn("ActivateWindow(1124)", dialog)
        self.assertIn("ActivateWindow(1125)", dialog)
        self.assertIn("ActivateWindow(1116)", dialog)
        self.assertIn("Skin.SetString(Shortcuts.RebuildDateTime", "\n".join(
            element.text or "" for element in editor.findall("onunload")
        ))

    def test_home_builds_shortcuts_only_when_marker_changed(self):
        actions = ET.parse(SKIN_ROOT / "1080i" / "Includes_Actions.xml").getroot()
        include = next(
            element for element in actions.findall("include")
            if element.get("name") == "Action_BuildShortcuts_OnLoad"
        )
        expression = next(
            element.text or "" for element in actions.findall("expression")
            if element.get("name") == "Exp_Shortcuts_BuildNeeded"
        )
        onloads = include.findall("onload")
        home = ET.parse(SKIN_ROOT / "1080i" / "Home.xml").getroot()

        self.assertIn(
            "Action_BuildShortcuts_OnLoad",
            [element.text for element in home.findall("include")],
        )
        self.assertTrue(onloads)
        self.assertTrue(
            all(
                element.get("condition") == "$EXP[Exp_Shortcuts_BuildNeeded]"
                for element in onloads
            )
        )
        self.assertIn(
            "skinvariables-build-templates.json", onloads[0].text or ""
        )
        self.assertIn(
            "!String.IsEqual(Window(Home).Property(Shortcuts.Checked),"
            "Skin.String(Shortcuts.RebuildDateTime))",
            expression,
        )
        # An unset marker must not suppress the build.
        self.assertIn(
            "String.IsEmpty(Skin.String(Shortcuts.RebuildDateTime))", expression
        )
        # Every property the check compares is recorded after the build.
        setters = "\n".join(element.text or "" for element in onloads[1:])
        for prop, value in (
            ("Shortcuts.Checked", "Skin.String(Shortcuts.RebuildDateTime)"),
            ("Shortcuts.Checked.SkinUser", "Skin.String(SkinVariables.SkinUser)"),
            ("Shortcuts.Checked.Version", "System.AddonVersion(skin.arctic.fuse.3)"),
        ):
            self.assertIn(f"Window(Home).Property({prop}),{value})", expression)
            self.assertIn(f"SetProperty({prop},$INFO[{value}],Home)", setters)


if __name__ == "__main__":
    unittest.main()

import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


SKIN_ROOT = Path(__file__).resolve().parents[1]
DATA = SKIN_ROOT / "shortcuts" / "generator" / "data"


def includes(name):
    root = ET.parse(SKIN_ROOT / "1080i" / name).getroot()
    return {
        element.get("name"): element
        for element in root.findall("include")
        if element.get("name")
    }


class LazyWidgetRowTests(unittest.TestCase):
    def test_standard_rows_take_their_path_through_the_lazy_rules(self):
        template = (DATA / "parts" / "widgets_row.xmltemplate").read_text(
            encoding="utf-8"
        )
        standard = (DATA / "base" / "home_widgets_standard.xml").read_text(
            encoding="utf-8"
        )

        self.assertIn(">{widget_content_path}</content>", template)
        self.assertNotIn(">{widget_path}</content>", template)
        self.assertIn(
            "SetProperty(Widgets.Reached,{item_x},{widget_lazy_window})", template
        )
        self.assertIn('content="Widget_Lazy_Placeholder"', template)
        self.assertIn("generator/data/setup/widgets_lazy.xml", standard)

    def test_lazy_path_variables_cover_the_same_rows(self):
        lazy = ET.parse(DATA / "setup" / "widgets_lazy.xml").getroot()
        values = {
            element.get("name"): element.text for element in lazy.findall("value")
        }
        rules = {
            element.get("name"): element for element in lazy.findall("rules")
        }
        paths_base = (DATA / "base" / "home_widgets_lazy.xml").read_text(
            encoding="utf-8"
        )
        path_template = (DATA / "parts" / "widgets_lazy_path.xmltemplate").read_text(
            encoding="utf-8"
        )
        widgets = (DATA / "base" / "home_widgets.xml").read_text(encoding="utf-8")

        # Rows 0-2 always load; later rows load once focus is two rows away.
        self.assertEqual(values["widget_lazy_threshold"], "$MATH[{item_x} - 2]")
        first_rule = rules["widget_lazy"].find("rule")
        self.assertEqual(
            first_rule.findtext("condition"), "{item_x}==0||{item_x}==1||{item_x}==2"
        )
        self.assertEqual(first_rule.findtext("value"), "False")
        for index in range(3):
            self.assertIn(f"<condition>{{item_x}}!={index}</condition>", paths_base)
        lazy_rule = rules["widget_content_path"].find("rule")
        self.assertEqual(
            lazy_rule.findtext("value"), "$VAR[Widget_Lazy_Path_{item}_{widget_id}]"
        )
        self.assertIn('<variable name="Widget_Lazy_Path_{item}_{widget_id}">', path_template)
        self.assertIn("generator/data/base/home_widgets_lazy.xml", widgets)

    def test_placeholder_keeps_unloaded_rows_focusable(self):
        placeholder = includes("Includes_Widgets.xml")["Widget_Lazy_Placeholder"]
        item = placeholder.find("content/item")

        self.assertEqual(item.findtext("visible"), "![$PARAM[reached]]")
        self.assertEqual(
            item.find("property[@name='widget_lazy']").text, "true"
        )

    def test_home_keeps_reached_rows_and_hubs_reset(self):
        hub_onload = includes("Includes_Hubs.xml")["Hub_Onload"]
        home = ET.parse(SKIN_ROOT / "1080i" / "Home.xml").getroot()
        home_onload = next(
            element for element in home.findall("include")
            if element.get("content") == "Hub_Onload"
        )

        self.assertEqual(hub_onload.findtext("param[@name='lazy_reset']"), "true")
        self.assertIn(
            "ClearProperty(Widgets.Reached,$PARAM[window_id])",
            [element.text for element in hub_onload.iter("onunload")],
        )
        self.assertEqual(home_onload.findtext("param[@name='lazy_reset']"), "false")


class StandardInfoPanelTests(unittest.TestCase):
    def test_standard_mode_uses_one_shared_info_panel(self):
        hubs = includes("Includes_Hubs.xml")
        text = (SKIN_ROOT / "1080i" / "Includes_Hubs.xml").read_text(encoding="utf-8")
        shared = hubs["Hub_Standard_Info"].find("include")

        self.assertEqual(shared.get("content"), "Hub_Combined_Info_Panels")
        self.assertEqual(shared.findtext("param[@name='container']"), "Container.")
        self.assertIn("ControlGroup(602).HasFocus()", shared.findtext("param[@name='visible']"))
        self.assertIn(
            'Mode),Standard)">Hub_Standard_Info</include>', text
        )
        self.assertNotIn("Mode),Standard)\">skinvariables-$PARAM[window]widgets-combined-info", text)


class PosterWallGenreTests(unittest.TestCase):
    def test_genre_is_a_static_label(self):
        details = includes("Includes_Views_Wall.xml")["View_Poster_Wall_Details"]
        genre = [
            control for control in details.iter("control")
            if control.findtext("label") == "$INFO[ListItem.Genre]"
        ]

        self.assertEqual(len(genre), 1)
        self.assertEqual(genre[0].get("type"), "label")
        self.assertEqual(genre[0].findtext("font"), "font_main")
        self.assertEqual(genre[0].findtext("textcolor"), "main_fg_70")


if __name__ == "__main__":
    unittest.main()

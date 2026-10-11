import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


SKIN_ROOT = Path(__file__).resolve().parents[1]


def _include(file_name, name):
    root = ET.parse(SKIN_ROOT / "1080i" / file_name).getroot()
    return root.find(f"./include[@name='{name}']")


class PosterWidgetTitleTests(unittest.TestCase):
    def test_widgets_follow_the_text_labels_setting(self):
        content = _include("Includes_Widgets.xml", "Widget_Content")
        self.assertEqual(
            "Skin.HasSetting(View.UseDetailedListLabels)",
            content.findtext("param[@name='show_wall_label']"),
        )
        row = next(
            node for node in content.iter("include") if node.get("content") == "$PARAM[include]"
        )
        self.assertEqual("$PARAM[show_wall_label]", row.findtext("param[@name='show_wall_label']"))

    def test_poster_row_passes_the_title_switch_to_its_layout(self):
        row = _include("Includes_Lists.xml", "List_Poster_Row")
        self.assertEqual("false", row.findtext("param[@name='show_wall_label']"))
        core = row.find(".//include[@content='List_Core']")
        self.assertEqual("$PARAM[show_wall_label]", core.findtext("param[@name='show_wall_label']"))

    def test_title_sits_in_the_cell_gap_and_skips_overlaid_tiles(self):
        layout = _include("Includes_Layouts.xml", "Layout_Poster")
        titles = layout.find(".//include[@condition='$PARAM[show_wall_label]']")
        visible = titles.findtext("visible")
        self.assertIn("!String.IsEqual($PARAM[listitem].DBType,actor)", visible)
        self.assertIn("![$PARAM[detailed]]", visible)
        labels = titles.findall("control")
        self.assertEqual(2, len(labels))
        for label in labels:
            self.assertEqual("$PARAM[item_h]", label.findtext("top"))
            self.assertEqual("40", label.findtext("height"))
        # The 40px label must fit between the poster and the cell edge.
        constants = ET.parse(SKIN_ROOT / "1080i" / "Includes_Constants.xml").getroot()
        value = {c.get("name"): float(c.text) for c in constants.findall("constant") if c.text and c.text.lstrip("-").replace(".", "").isdigit()}
        self.assertGreaterEqual(value["view_poster_itemlayout_h"] - value["view_poster_item_h"], 40)


if __name__ == "__main__":
    unittest.main()

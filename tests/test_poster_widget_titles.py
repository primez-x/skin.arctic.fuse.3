import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


SKIN_ROOT = Path(__file__).resolve().parents[1]


def _include(file_name, name):
    root = ET.parse(SKIN_ROOT / "1080i" / file_name).getroot()
    return root.find(f"./include[@name='{name}']")


class PosterWidgetLabelTests(unittest.TestCase):
    """Poster widget rows label their items like landscape rows: the title in
    Simple text mode, title and subtitle in Detailed (Layout_Labels)."""

    def test_widget_rows_ask_for_labels(self):
        content = _include("Includes_Widgets.xml", "Widget_Content")
        row = next(n for n in content.iter("include") if n.get("content") == "$PARAM[include]")
        self.assertEqual("true", row.findtext("param[@name='show_labels']"))

    def test_poster_rows_get_one_rhythm_step_more_space(self):
        content = _include("Includes_Widgets.xml", "Widget_Content")
        spacers = [
            c for c in content.find("definition").findall("include")
            if c.get("content") == "Widget_LabelsBelow_Spacer"
        ]
        self.assertEqual(1, len(spacers))
        self.assertEqual("$PARAM[detailed]", spacers[0].findtext("param[@name='detailed']"))
        self.assertTrue(spacers[0].findtext("param[@name='visible']").startswith("$PARAM[visible] + "))
        spacer = _include("Includes_Widgets.xml", "Widget_LabelsBelow_Spacer").find("definition/include")
        # The tile style is matched when the window loads (String.IsEqual cannot compare
        # two literals, so it was never true for the row include name).
        self.assertEqual("$EXP[Exp_LabelsBelow__$PARAM[include]]", spacer.get("condition"))
        self.assertEqual("group", spacer.findtext("param[@name='control']"))
        self.assertEqual("view_bar", spacer.findtext("height"))
        self.assertEqual("7$PARAM[id]", spacer.findtext("param[@name='id']"))
        visible = spacer.findtext("visible")
        self.assertNotIn("String.IsEqual($PARAM[include]", visible)
        self.assertIn("+ $PARAM[visible]", visible)

    def test_lists_forward_the_switch_to_the_layout(self):
        core = _include("Includes_Lists.xml", "List_Core")
        self.assertEqual("false", core.findtext("param[@name='show_labels']"))
        forwarded = [
            n for n in core.iter("include")
            if n.get("content") == "$PARAM[itemlayout_include]"
        ]
        self.assertEqual(4, len(forwarded))
        for node in forwarded:
            self.assertEqual("$PARAM[show_labels]", node.findtext("param[@name='show_labels']"))
        row = _include("Includes_Lists.xml", "List_Poster_Row")
        self.assertEqual("false", row.findtext("param[@name='show_labels']"))
        self.assertEqual(
            "$PARAM[show_labels]",
            row.find(".//include[@content='List_Core']").findtext("param[@name='show_labels']"),
        )

    def test_poster_layout_uses_the_shared_label_block(self):
        layout = _include("Includes_Layouts.xml", "Layout_Poster")
        self.assertEqual("false", layout.findtext("param[@name='show_labels']"))
        block = layout.find(".//include[@condition='$PARAM[show_labels] + ![$PARAM[hide_labels]]']")
        self.assertIn("![$PARAM[detailed]]", block.findtext("visible"))
        self.assertIn("!String.IsEqual($PARAM[listitem].DBType,actor)", block.findtext("visible"))
        labels = block.find("include[@content='Layout_Labels']")
        self.assertEqual("10", labels.findtext("param[@name='top']"))
        # Layout_Labels switches between title and title + subtitle on Text labels.
        shared = _include("Includes_Layouts.xml", "Layout_Labels")
        self.assertEqual(
            "Skin.HasSetting(View.UseDetailedListLabels)",
            shared.findtext("param[@name='include_detailed_labels']"),
        )
        # The poster wall uses the same block (centred): its own wall label is retired.
        self.assertIsNone(layout.find(".//include[@condition='$PARAM[show_wall_label]']"))
        self.assertEqual("$PARAM[labels_align]", labels.findtext("param[@name='align']"))


if __name__ == "__main__":
    unittest.main()


class TextLabelsOffTests(unittest.TestCase):
    def test_setting_cycles_simple_detailed_off(self):
        text = (SKIN_ROOT / "1080i" / "Includes_SkinSettings.xml").read_text(encoding="utf-8")
        for action in (
            '<onclick condition="!Skin.HasSetting(View.UseDetailedListLabels) + !Skin.HasSetting(View.HideWidgetLabels)">Skin.SetBool(View.UseDetailedListLabels)</onclick>',
            '<onclick condition="Skin.HasSetting(View.UseDetailedListLabels)">Skin.Reset(View.UseDetailedListLabels)</onclick>',
            '<onclick condition="Skin.HasSetting(View.UseDetailedListLabels)">Skin.SetBool(View.HideWidgetLabels)</onclick>',
            '<onclick condition="Skin.HasSetting(View.HideWidgetLabels)">Skin.Reset(View.HideWidgetLabels)</onclick>',
        ):
            self.assertIn(action, text)
        self.assertIn("<label2>$VAR[Label_Settings_TextLabels]</label2>", text)

    def test_off_reaches_every_labelled_widget_layout(self):
        content = _include("Includes_Widgets.xml", "Widget_Content")
        row = next(n for n in content.iter("include") if n.get("content") == "$PARAM[include]")
        self.assertEqual("Skin.HasSetting(View.HideWidgetLabels)", row.findtext("param[@name='hide_labels']"))
        spacer = _include("Includes_Widgets.xml", "Widget_LabelsBelow_Spacer").find("definition/include")
        self.assertIn("!Skin.HasSetting(View.HideWidgetLabels)", spacer.findtext("visible"))
        for row_name in ("List_Poster_Row", "List_Landscape_Row", "List_Board_Row", "List_Square_Row"):
            row = _include("Includes_Lists.xml", row_name)
            self.assertEqual("false", row.findtext("param[@name='hide_labels']"), row_name)
            core = row.find(".//include[@content='List_Core']")
            self.assertEqual("$PARAM[hide_labels]", core.findtext("param[@name='hide_labels']"), row_name)
        core = _include("Includes_Lists.xml", "List_Core")
        forwarded = [n for n in core.iter("include") if n.get("content") == "$PARAM[itemlayout_include]"]
        self.assertTrue(all(n.findtext("param[@name='hide_labels']") == "$PARAM[hide_labels]" for n in forwarded))
        layouts = ET.parse(SKIN_ROOT / "1080i" / "Includes_Layouts.xml").getroot()
        for name in ("Layout_Poster", "Layout_Landscape", "Layout_Square"):
            layout = layouts.find(f"./include[@name='{name}']")
            self.assertEqual("false", layout.findtext("param[@name='hide_labels']"), name)
            gated = [n for n in layout.iter("include") if "![$PARAM[hide_labels]]" in (n.get("condition") or "")]
            self.assertEqual(1, len(gated), name)

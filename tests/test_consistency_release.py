"""Structural guarantees of the 3.8.0 consistency release: one label system on
every tile style and view, the labels-below spacer, the shared next-item
overlay, and the shared stream-details / duration / episode-number labels."""

import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


SKIN_ROOT = Path(__file__).resolve().parents[1]
SKIN = SKIN_ROOT / "1080i"


def _root(file_name):
    return ET.parse(SKIN / file_name).getroot()


def _include(file_name, name):
    node = _root(file_name).find(f"./include[@name='{name}']")
    assert node is not None, (file_name, name)
    return node


def _variable(file_name, name):
    node = _root(file_name).find(f"./variable[@name='{name}']")
    assert node is not None, (file_name, name)
    return node


def _constants():
    return {c.get("name"): c.text for c in _root("Includes_Constants.xml").iter("constant")}


TALL_ROWS = ("List_Poster_Row", "List_Card_Row", "List_Circle_Row", "List_Banner_Row", "List_Board_Row")
SHORT_ROWS = ("List_Landscape_Row", "List_Square_Row")


class LabelsBelowSpacerTests(unittest.TestCase):
    def setUp(self):
        self.visible = _include("Includes_Widgets.xml", "Widget_LabelsBelow_Spacer").findtext(
            "definition/control/visible"
        )

    def test_spacer_only_for_tall_tiles_with_labels_below(self):
        for row in TALL_ROWS:
            self.assertIn(f"String.IsEqual($PARAM[include],{row})", self.visible, row)
        for row in SHORT_ROWS:
            # Landscape and Square cells already have room for their labels
            self.assertNotIn(row, self.visible, row)
        self.assertIn("![$PARAM[detailed]]", self.visible)
        self.assertIn("!Skin.HasSetting(View.HideWidgetLabels)", self.visible)

    def test_cast_and_crew_rows_get_no_spacer(self):
        first = "Container($PARAM[id]).ListItemAbsolute(0)"
        for check in (
            f"!String.IsEqual({first}.DBType,actor)",
            f"!String.IsEqual({first}.DBType,video)",
            f"String.IsEmpty({first}.Property(role))",
        ):
            self.assertIn(check, self.visible)
        # Info dialog cast/crew rows are detailed rows: no spacer for them either
        crew = _include("Includes_DialogInfo.xml", "DialogInfo_CrewWidget")
        self.assertEqual("true", crew.findtext(".//param[@name='detailed']"))
        content = _include("Includes_Widgets.xml", "Widget_Content")
        self.assertEqual("false", content.findtext("param[@name='detailed']"))

    def test_poster_tiles_overlay_labels_by_the_same_rule(self):
        layout = _include("Includes_Layouts.xml", "Layout_Poster")
        below = layout.find(".//include[@condition='$PARAM[show_labels] + ![$PARAM[hide_labels]]']")
        rule = below.findtext("visible")
        for check in ("DBType,actor", "DBType,video", "Property(role)", "$PARAM[detailed]"):
            self.assertIn(check, rule)
        # The row default no longer hides the role rule from rows that pass detailed=false
        self.assertEqual("false", _include("Includes_Lists.xml", "List_Poster_Row").findtext("param[@name='detailed']"))


class LabelSystemTests(unittest.TestCase):
    def test_every_tall_row_forwards_the_label_params(self):
        for row in TALL_ROWS:
            node = _include("Includes_Lists.xml", row)
            self.assertEqual("false", node.findtext("param[@name='hide_labels']"), row)
            core = node.find(".//include[@content='List_Core']")
            for name in ("show_labels", "hide_labels", "labels_align"):
                self.assertEqual(f"$PARAM[{name}]", core.findtext(f"param[@name='{name}']"), (row, name))

    def test_card_row_forwards_to_its_focused_card(self):
        card = _include("Includes_Lists.xml", "List_Card_Row")
        focused = [n for n in card.find(".//focusedlayout").iter("include")
                   if n.get("content") == "$PARAM[itemlayout_include]"]
        self.assertEqual(3, len(focused))
        for node in focused:
            for name in ("show_labels", "hide_labels", "labels_align"):
                self.assertEqual(f"$PARAM[{name}]", node.findtext(f"param[@name='{name}']"))

    def test_every_tile_layout_draws_layout_labels(self):
        for name in ("Layout_Poster", "Layout_Card", "Layout_Circle", "Layout_Banner", "Layout_Landscape", "Layout_Square"):
            layout = _include("Includes_Layouts.xml", name)
            labels = [n for n in layout.iter("include") if n.get("content") == "Layout_Labels"]
            self.assertTrue(labels, name)
            self.assertTrue(any(n.findtext("param[@name='align']") == "$PARAM[labels_align]" for n in labels), name)
        self.assertEqual("center", _include("Includes_Layouts.xml", "Layout_Circle").findtext("param[@name='labels_align']"))
        # Board (Landscape with detailed=true) labels when the row asks for it
        landscape = _include("Includes_Layouts.xml", "Layout_Landscape")
        self.assertIsNotNone(landscape.find(
            ".//include[@condition='[![$PARAM[detailed]] | $PARAM[show_labels]] + ![$PARAM[hide_labels]]']"
        ))

    def test_poster_layout_textcolor_and_progress(self):
        layout = _include("Includes_Layouts.xml", "Layout_Poster")
        self.assertEqual("main_fg", layout.findtext("param[@name='textcolor']"))
        labels = layout.find(".//include[@content='Layout_Labels']")
        self.assertEqual("$PARAM[textcolor]", labels.findtext("param[@name='textcolor']"))
        self.assertIsNotNone(layout.find(".//include[@content='Object_ProgressLine']"))

    def test_layout_labels_has_an_align_param_and_no_joined_label2(self):
        labels = _include("Includes_Layouts.xml", "Layout_Labels")
        self.assertEqual("left", labels.findtext("param[@name='align']"))
        text = ET.tostring(labels, encoding="unicode")
        self.assertNotIn("Label2, - ,", text)
        self.assertIn("$INFO[$PARAM[listitem].Label2]", text)


class ViewLabelTests(unittest.TestCase):
    def test_no_wall_label_left(self):
        for path in SKIN.glob("*.xml"):
            self.assertNotIn("show_wall_label", path.read_text(encoding="utf-8"), path.name)

    def test_walls_and_rows_pass_the_label_params(self):
        panel = _include("Includes_Views_Wall.xml", "View_Wall_Panel")
        row = _include("Includes_Views_Row.xml", "View_Row_Include")
        grid = _include("Includes_Views_Wall.xml", "View_515_Grid")
        for node in (panel, row, grid):
            call = next(n for n in node.iter("include") if n.get("content") in ("$PARAM[include]", "List_Poster_Row"))
            self.assertEqual("true", call.findtext("param[@name='show_labels']"))
            self.assertEqual("Skin.HasSetting(View.HideWidgetLabels)", call.findtext("param[@name='hide_labels']"))
        self.assertEqual("center", grid.findtext(".//param[@name='labels_align']"))

    def test_tall_walls_grow_by_one_rhythm_step(self):
        constants = _constants()
        self.assertEqual(
            float(constants["view_poster_itemlayout_h"]) + float(constants["view_bar"]),
            float(constants["view_poster_labelled_itemlayout_h"]),
        )
        self.assertEqual(
            float(constants["view_poster_wall_itemlayout_h"]) + float(constants["view_bar"]),
            float(constants["view_poster_wall_labelled_itemlayout_h"]),
        )
        for name in ("view_poster_labelled_itemlayout_h", "view_poster_wall_labelled_itemlayout_h",
                     "view_poster_wall_offset_x", "view_poster_wall_offset_y", "view_pad", "view_bar"):
            self.assertEqual("-" + constants[name], constants["-" + name], name)
        walls = _root("Includes_Views_Wall.xml")
        for view in ("View_512_Poster_Wall", "View_513_Circle_Wall", "View_514_Board_Wall"):
            self.assertEqual("true", walls.find(f"./include[@name='{view}']").findtext(".//param[@name='labels_below']"), view)
        wall = _include("Includes_Views_Wall.xml", "View_Wall_Include")
        labelled = wall.find(".//include[@condition='$PARAM[labels_below] + !Skin.HasSetting(View.HideWidgetLabels)']")
        self.assertEqual("view_poster_labelled_itemlayout_h", labelled.findtext("param[@name='itemlayout_h']"))

    def test_poster_wall_details_grid_uses_constants(self):
        grid = _include("Includes_Views_Wall.xml", "View_515_Grid")
        for name in ("offset_x", "offset_y", "indicator_top", "indicator_right"):
            value = grid.findtext(f".//param[@name='{name}']")
            self.assertTrue(value.lstrip("-").startswith("view_poster_wall_"), (name, value))


class PanelTests(unittest.TestCase):
    def test_poster_wall_details_uses_the_shared_info_blocks(self):
        details = _include("Includes_Views_Wall.xml", "View_Poster_Wall_Details")
        title = details.find(".//include[@content='Info_Title']")
        self.assertEqual("view_poster_wall_details_w", title.findtext("param[@name='width']"))
        self.assertEqual("false", title.findtext("param[@name='use_logo']"))
        plot = details.find(".//include[@content='Info_Plot']")
        self.assertEqual("view_poster_wall_details_w", plot.findtext("param[@name='width']"))
        self.assertEqual("true", plot.findtext("param[@name='use_textbox']"))
        self.assertLess(int(plot.findtext("param[@name='plotline_height']")), int(plot.findtext("param[@name='height']")))
        self.assertEqual([], [c for c in details.iter("control") if c.get("type") in ("label", "textbox")])

    def test_music_osd_title_composes_info_blocks(self):
        details = _include("Includes_OSD.xml", "OSD_TitleDetails")
        self.assertIsNotNone(details.find(".//include[@content='Info_Title']"))
        line = details.find(".//include[@content='Info_Line']")
        self.assertEqual("panel_fg", line.findtext("param[@name='colordiffuse']"))
        self.assertEqual("true", line.findtext("param[@name='show_artist']"))

    def test_info_panel_plot_width_is_the_constant(self):
        self.assertEqual("info_plot_w", _include("Includes_Info.xml", "Info_Panel").findtext("param[@name='plotwidth']"))
        self.assertEqual("800", _constants()["info_plot_w"])

    def test_info_blocks_never_hard_code_listitem(self):
        text = (SKIN / "Includes_Info.xml").read_text(encoding="utf-8")
        self.assertNotIn("$PARAM[container]ListItem.", text)
        self.assertNotIn("$INFO[ListItem.Property(watchedepisodes)", text)


class NextItemOverlayTests(unittest.TestCase):
    def test_both_overlays_use_the_shared_include(self):
        for name, shape, corner in (
            ("Custom_1143_OSD_NextOverlay.xml", "landscape", "left"),
            ("Custom_1154_OSD_NextOverlay_Music.xml", "square", "right"),
        ):
            overlays = _root(name).findall(".//include[@content='Object_NextItem']")
            self.assertEqual(1, len(overlays), name)
            self.assertEqual(shape, overlays[0].findtext("param[@name='shape']"))
            self.assertEqual(corner, overlays[0].findtext("param[@name='corner']"))
            text = (SKIN / name).read_text(encoding="utf-8")
            self.assertNotIn(" - ,", text)
            self.assertNotIn("<!-- <param", text)
            self.assertNotIn("EE121316", text)

    def test_shared_include_typography(self):
        item = _include("Includes_OSD.xml", "Object_NextItem")
        lines = item.findall(".//include[@content='Object_NextItem_Label']")
        styles = [(n.findtext("param[@name='font']"), n.findtext("param[@name='textcolor']")) for n in lines]
        self.assertEqual(
            [("font_tiny_bold", "panel_fg_50"), ("font_main_bold", "panel_fg_90"), ("font_main", "panel_fg_70")],
            styles,
        )
        grouplist = item.find(".//control[@type='grouplist']")
        self.assertEqual("center", grouplist.findtext("aligny"))
        self.assertIsNone(grouplist.find("align"))
        osd = _root("Includes_OSD.xml")
        self.assertEqual("right", osd.findtext("./include[@name='Object_NextItem_Label_right']/align"))

    def test_music_title_has_no_dash_prefix(self):
        for value in _variable("Includes_OSD.xml", "Label_OSD_MusicNext_Title").findall("value"):
            self.assertNotIn(" - ", value.text)

    def test_next_track_header_and_title(self):
        furniture = ET.tostring(_include("Includes_Furniture.xml", "Furniture_NextTrack"), encoding="unicode")
        self.assertIn("$VAR[Label_NextTrack_Header]", furniture)
        self.assertNotIn(",in ,", furniture)
        self.assertNotIn("panel_fg_100", furniture)
        header = ET.tostring(_variable("Includes_Labels.xml", "Label_NextTrack_Header"), encoding="unicode")
        self.assertIn("$LOCALIZE[31129]", header)

    def test_playlist_subline_never_leaves_a_stray_bullet(self):
        values = _variable("Includes_Labels.xml", "Label_OSD_UpNext_Playlist_SubTitle").findall("value")
        self.assertEqual(51 * 4, len(values))
        for value in values:
            text = value.text or ""
            # bullets only ever prefix a later field; no field carries a trailing bullet
            self.assertNotIn(",, [COLOR=panel_fg_30]•[/COLOR] ]", text)
            self.assertNotIn(".Rating", text)


class SharedLabelTests(unittest.TestCase):
    def test_stream_details_variable_used_everywhere(self):
        for name in ("Includes_DialogInfo.xml", "Dialog_Lists.xml"):
            text = (SKIN / name).read_text(encoding="utf-8")
            self.assertIn("$VAR[Label_ListItem_StreamDetails]", text, name)
            self.assertNotIn("$INFO[ListItem.VideoCodec]$VAR", text, name)
            self.assertNotIn("$INFO[ListItem.VideoCodec, • ,]", text, name)
        self.assertEqual(2, (SKIN / "Includes_DialogInfo.xml").read_text(encoding="utf-8").count("$VAR[Label_ListItem_StreamDetails]"))
        value = _variable("Includes_Labels.xml", "Label_ListItem_StreamDetails").find("value").text
        order = ["VideoCodec", "Label_ListItem_VideoQuality", "HdrType", "VideoAspect", "AudioCodec", "Label_ListItem_AudioChannels"]
        positions = [value.index(part) for part in order]
        self.assertEqual(sorted(positions), positions)

    def test_duration_variables_used(self):
        labels = _root("Includes_Labels.xml")
        self.assertIn("$VAR[Label_Duration_Compact]", ET.tostring(labels.find("./variable[@name='Label_MediaList_Details_RightLabel']"), encoding="unicode"))
        self.assertIn("$VAR[Label_Duration]", ET.tostring(labels.find("./variable[@name='Label_SortLetter']"), encoding="unicode"))
        full = ET.tostring(labels.find("./variable[@name='Label_Duration']"), encoding="unicode")
        info_line = ET.tostring(_include("Includes_Info.xml", "Info_Line"), encoding="unicode")
        for string in ("$LOCALIZE[31074]", "$LOCALIZE[31073]"):
            self.assertIn(string, full)
            self.assertIn(string, info_line)

    def test_padded_episode_numbers(self):
        pvr = ET.tostring(_variable("Includes_Labels.xml", "Label_PVR_Episode"), encoding="unicode")
        self.assertIn("$VAR[Label_Episode_Number", pvr)
        self.assertNotIn("Episode,,. ]", pvr)
        osd = (SKIN / "Includes_OSD.xml").read_text(encoding="utf-8")
        self.assertNotIn("$INFO[VideoPlayer.Episode,,. ]", osd)
        self.assertIn("$VAR[Label_OSD_Plot_Episode_Number,,. ]", osd)
        # The generated variable is kept in sync with its shortcuts/ source
        source = ET.parse(SKIN_ROOT / "shortcuts" / "skinvariables-labels.xml").getroot()
        self.assertIsNotNone(source.find("./variable[@name='Label_Episode_Number']"))
        generated = _root("script-skinvariables-labels-includes.xml")
        for name in ("Label_Episode_Number", "Label_Episode_Number_C450", "Label_Episode_Number_Container"):
            self.assertIsNotNone(generated.find(f"./variable[@name='{name}']"), name)

    def test_no_results_item_covers_every_style(self):
        item = _include("Includes_Widgets.xml", "_Widget_NoResults")
        props = {p.get("name") for p in item.iter("property")}
        for style in ("square", "poster", "landscape", "circle", "card", "banner"):
            self.assertIn(f"override_{style}", props)
        source = (SKIN_ROOT / "shortcuts" / "skinvariables-images.xml").read_text(encoding="utf-8")
        generated = (SKIN / "script-skinvariables-images-includes.xml").read_text(encoding="utf-8")
        for prop in ("override_circle", "override_banner"):
            self.assertIn(prop, source)
            self.assertIn(prop, generated)
        self.assertIn("override_card", (SKIN / "Includes_Images.xml").read_text(encoding="utf-8"))

    def test_no_literal_dash_or_prefix_in_touched_labels(self):
        labels = _root("Includes_Labels.xml")
        for name in ("Label_Reviews_Sub", "Label_Channel", "Label_Channel_C11", "Label_ListItem_StreamDetails",
                     "Label_NextTrack_Header", "Label_OSD_UpNext_Playlist_SubTitle"):
            text = ET.tostring(labels.find(f"./variable[@name='{name}']"), encoding="unicode")
            self.assertNotIn(" - ", text, name)
        reviews = ET.tostring(_include("Includes_Layouts.xml", "Layout_Reviews"), encoding="unicode")
        self.assertNotIn(",, - ]", reviews)
        guide = (SKIN / "DialogPVRChannelGuide.xml").read_text(encoding="utf-8")
        self.assertNotIn("Channel: ", guide)
        self.assertNotIn("(Ch.", (SKIN / "Dialog_DialogPVRInfo.xml").read_text(encoding="utf-8"))
        self.assertNotIn(",Channel ,", (SKIN / "Includes_Info.xml").read_text(encoding="utf-8"))

    def test_one_wording_for_ends_at_and_watched_episodes(self):
        text = "".join(p.read_text(encoding="utf-8") for p in SKIN.glob("*.xml"))
        self.assertNotIn("$LOCALIZE[31184]", text)
        self.assertNotIn("$LOCALIZE[16102] , $LOCALIZE[1443]", text)
        self.assertEqual(3, text.count("Property(watchedepisodes), • , [LOWERCASE]$LOCALIZE[16102][/LOWERCASE]]"))


class PlaceholderAndCleanupTests(unittest.TestCase):
    def test_placeholder_bars_follow_text_labels(self):
        blank = ET.tostring(_include("Includes_Widgets.xml", "Widget_Busy_BlankItem"), encoding="unicode")
        self.assertIn("<visible>!Skin.HasSetting(View.HideWidgetLabels)</visible>", blank)
        self.assertIn("<visible>Skin.HasSetting(View.UseDetailedListLabels) + !Skin.HasSetting(View.HideWidgetLabels)</visible>", blank)
        self.assertIn("<top>$PARAM[item_h]</top>", blank)
        for style in ("Poster", "Card", "Circle", "Banner", "Board"):
            node = _include("Includes_Widgets.xml", f"Widget_Busy_BlankItem_{style}")
            self.assertIsNone(node.find(".//param[@name='first_row']"), style)

    def test_unused_includes_are_gone(self):
        text = "".join(p.read_text(encoding="utf-8") for p in SKIN.glob("*.xml"))
        for name in ('"Widget_Busy_Spinner"', '"Object_BusySpinner"', '"Object_FakeSpinner"',
                     "Label_PVRRecordings_Sublabel_Channels", "constant_dialog_pad", "view_offx"):
            self.assertNotIn(name, text, name)

    def test_busy_dialog_chrome_is_muted(self):
        furniture = (SKIN / "Includes_Furniture.xml").read_text(encoding="utf-8")
        for label in ("$PARAM[minilabel]", "$PARAM[percentage_label]"):
            block = furniture[furniture.index(f"<label>{label}</label>") - 200:furniture.index(f"<label>{label}</label>")]
            self.assertIn("<textcolor>main_fg_30</textcolor>", block)

    def test_master_padding_uses_constants(self):
        core = _include("Includes_Lists.xml", "List_Core")
        self.assertEqual("view_pad", core.findtext("param[@name='offset_x']"))
        self.assertEqual("view_pad", core.findtext("param[@name='offset_y']"))
        panel = _include("Includes_Views_Wall.xml", "View_Wall_Panel")
        self.assertEqual("view_bar", panel.findtext(".//param[@name='offset_y']"))
        self.assertEqual("-view_bar", panel.findtext(".//bottom"))
        self.assertEqual("view_pad", _root("VideoFullScreen.xml").findtext(".//control[@id='0']/left"))


if __name__ == "__main__":
    unittest.main()

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


# Geometry of a view, resolved the way Kodi expands includes: a <param> whose whole value is
# an undefined $PARAM is dropped so the include's default applies; constants become numbers.
_PARAM = re.compile(r"\$PARAM\[(\w+)\]")
_ALL_INCLUDES = {}


def _includes():
    if not _ALL_INCLUDES:
        for path in SKIN.glob("Includes*.xml"):
            for node in ET.parse(path).getroot().findall("include"):
                if node.get("name"):
                    _ALL_INCLUDES.setdefault(node.get("name"), node)
    return _ALL_INCLUDES


def _number(value, constants):
    value = value.strip()
    return float(constants.get(value, value))


def _resolve(text, params):
    return _PARAM.sub(lambda m: params.get(m.group(1), ""), text or "")


def _call_params(call, params):
    """The params an include call passes, resolved against the caller's params."""
    passed = {}
    for param in call.findall("param"):
        whole = _PARAM.fullmatch((param.text or "").strip())
        if whole and whole.group(1) not in params:
            continue
        passed[param.get("name")] = _resolve(param.text, params)
    return passed


def _with_defaults(name, passed):
    params = {p.get("name"): (p.text or "") for p in _includes()[name].findall("param")}
    params.update(passed)
    return params


def _condition(text, params, labels_off):
    expressions = {e.get("name"): e.text for e in _root("Includes_Widgets.xml").findall("expression")}
    expr = re.sub(r"\$EXP\[(\w+)\]", lambda m: expressions.get(m.group(1), "false"), _resolve(text, params))
    expr = expr.replace("Skin.HasSetting(View.HideWidgetLabels)", str(labels_off).lower())
    expr = expr.replace("[", "(").replace("]", ")").replace("!", " not ").replace("+", " and ").replace("|", " or ")
    return eval(expr.replace("true", "True").replace("false", "False"), {"__builtins__": {}})


def _footer_top(constants):
    bar = _include("Includes_Dimensions.xml", "Dimension_Bottombar")
    furniture = _include("Includes_Dimensions.xml", "Dimension_Furniture")
    return 1080 - _number(bar.findtext("bottom"), constants) - _number(furniture.findtext("height"), constants)


def _labels_block(layout, params, labels_off):
    """(top offset below the tile, height) of the label block a tile layout draws below
    itself, or None when its condition hides it."""
    definition = _includes()[layout].find("definition")
    parents = {child: parent for parent in definition.iter() for child in parent}
    for call in definition.iter("include"):
        if call.get("content") != "Layout_Labels" or call.findtext("param[@name='top']") != "10":
            continue
        conditions = [call.get("condition")]
        parent = parents.get(call)
        if parent is not None and parent.tag == "include":
            conditions.append(parent.get("condition"))
        if all(_condition(c, params, labels_off) for c in conditions if c):
            block = next(g for g in _includes()["Layout_Labels"].iter("control") if g.findtext("top") == "$PARAM[top]")
            return 10, float(block.findtext("height"))
        return None
    return None


def _row_calls(name, params, labels_off):
    """The calls of the view's row include (List_*_Row) that the view template expands to."""
    node = _includes()[name]
    body = node.find("definition") if node.find("definition") is not None else node
    for call in body.iter("include"):
        if call.get("condition") and not _condition(call.get("condition"), params, labels_off):
            continue
        content = _resolve(call.get("content"), params)
        if content == params.get("include"):
            yield call, params
        elif content.startswith("View_") and content in _includes():
            yield from _row_calls(content, _with_defaults(content, _call_params(call, params)), labels_off)


def _view_tile_bottoms(call, labels_off, constants):
    """Yield (bottom, what) for each tile layout a row or combined view draws: the label
    block's bottom when it is shown, the tile's otherwise."""
    template = call.get("content")
    for row_call, params in _row_calls(template, _with_defaults(template, _call_params(call, {})), labels_off):
        top = _number(row_call.findtext("top"), constants)
        row_name = params["include"]
        row = _with_defaults(row_name, _call_params(row_call, params))
        definition = _includes()[row_name].find("definition")
        core = definition.find("include[@content='List_Core']")
        core_params = _with_defaults("List_Core", _call_params(core, row))
        layout = core_params["itemlayout_include"]
        tiles = [(layout, _with_defaults(layout, _call_params_from(core_params)), core_params)]
        for node in definition.iter("include"):
            content = _resolve(node.get("content"), row)
            if content.startswith("Layout_") and content in _includes():
                tiles.append((content, _with_defaults(content, _call_params(node, row)), row))
        for layout, layout_params, offsets in tiles:
            tile_bottom = top + _number(offsets["offset_y"], constants) + _number(layout_params["item_h"], constants)
            block = _labels_block(layout, layout_params, labels_off)
            if block:
                yield tile_bottom + block[0] + block[1], f"{row_name} {layout} labels"
            else:
                yield tile_bottom, f"{row_name} {layout} tile"


def _call_params_from(params):
    """List_Core passes its own params on to the item layout under the same names."""
    return {k: v for k, v in params.items() if not _PARAM.fullmatch(v.strip())}


TALL_ROWS = ("List_Poster_Row", "List_Card_Row", "List_Circle_Row", "List_Banner_Row", "List_Board_Row")
SHORT_ROWS = ("List_Landscape_Row", "List_Square_Row")


class LabelsBelowSpacerTests(unittest.TestCase):
    def setUp(self):
        self.spacer = _include("Includes_Widgets.xml", "Widget_LabelsBelow_Spacer").find("definition/include")
        self.visible = self.spacer.findtext("visible")
        self.expressions = {
            e.get("name"): e.text for e in _root("Includes_Widgets.xml").findall("expression")
        }

    def test_spacer_only_for_tall_tiles_with_labels_below(self):
        # String.IsEqual(List_Poster_Row,List_Poster_Row) is false in Kodi (the first
        # argument is resolved as an info label), so the row include is matched through an
        # expression name in the include condition when the window loads.
        self.assertEqual("$EXP[Exp_LabelsBelow__$PARAM[include]]", self.spacer.get("condition"))
        for row in TALL_ROWS:
            self.assertEqual("true", self.expressions.get(f"Exp_LabelsBelow__{row}"), row)
        for row in SHORT_ROWS:
            # Landscape and Square cells already have room for their labels
            self.assertIsNone(self.expressions.get(f"Exp_LabelsBelow__{row}"), row)
        self.assertNotIn("String.IsEqual($PARAM[include]", ET.tostring(
            _include("Includes_Widgets.xml", "Widget_LabelsBelow_Spacer"), encoding="unicode"))
        self.assertIn("![$PARAM[detailed]]", self.visible)
        self.assertIn("!Skin.HasSetting(View.HideWidgetLabels)", self.visible)

    def test_no_literal_include_comparisons_left(self):
        for path in SKIN.glob("*.xml"):
            self.assertIsNone(
                re.search(r"String\.IsEqual\(\$PARAM\[include\],", path.read_text(encoding="utf-8")),
                path.name,
            )

    def test_cast_and_crew_rows_get_no_spacer(self):
        check = self.spacer.find("include[@content='Widget_LabelsBelow_CastCheck']")
        self.assertEqual("$EXP[Exp_LabelsBelow_CastCheck__$PARAM[include]]", check.get("condition"))
        for row in ("List_Poster_Row", "List_Card_Row"):
            self.assertEqual("true", self.expressions.get(f"Exp_LabelsBelow_CastCheck__{row}"), row)
        rule = _include("Includes_Widgets.xml", "Widget_LabelsBelow_CastCheck").findtext("visible")
        first = "Container($PARAM[id]).ListItemAbsolute(0)"
        for check in (
            f"!String.IsEqual({first}.DBType,actor)",
            f"!String.IsEqual({first}.DBType,video)",
            f"String.IsEmpty({first}.Property(role))",
        ):
            self.assertIn(check, rule)
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
        row = _include("Includes_Views_Row.xml", "View_Row_List")
        grid = _include("Includes_Views_Wall.xml", "View_515_Grid")
        for node in (panel, row, grid):
            call = next(n for n in node.iter("include") if n.get("content") in ("$PARAM[include]", "List_Poster_Row"))
            self.assertEqual("true", call.findtext("param[@name='show_labels']"))
            self.assertEqual("Skin.HasSetting(View.HideWidgetLabels)", call.findtext("param[@name='hide_labels']"))
        self.assertEqual("center", grid.findtext(".//param[@name='labels_align']"))

    def test_view_labels_clear_the_footer(self):
        # The label block under a tall row view tile ended at 990, inside the item-count
        # footer bar (960-1000), so two-line titles ran into it (3.8.2: View 502; 3.8.3: the
        # Card row, View 505). Every view drawn under that footer is checked with Text labels
        # on and Off, from the includes and constants Kodi resolves.
        constants = _constants()
        footer_top = _footer_top(constants)
        views = [(f"View_{i}", "Includes_Views_Row.xml", "View_Row_Include") for i in range(500, 506)]
        views += [(f"View_{i}", "Includes_Views_Combined.xml", "View_Combined_Row") for i in range(520, 525)]
        checked = set()
        for prefix, file_name, template in views:
            root = _root(file_name)
            view = next(n for n in root.findall("include") if n.get("name").startswith(prefix + "_"))
            call = view.find(f"include[@content='{template}']")
            self.assertIsNotNone(call, view.get("name"))
            for labels_off in (False, True):
                for bottom, what in _view_tile_bottoms(call, labels_off, constants):
                    checked.add(view.get("name"))
                    with self.subTest(view=view.get("name"), labels_off=labels_off, what=what):
                        self.assertLessEqual(bottom, footer_top)
        self.assertEqual(11, len(checked))

    def test_views_without_the_footer_are_exempt_by_rule(self):
        # Walls (510-515) hide the item-count footer; list views end at Dimension_Info's bottom.
        constants = _constants()
        main = _include("Includes_Views.xml", "View_Main")
        footer = next(g for g in main.iter("control") if g.find("include") is not None
                      and g.find("include").text == "Furniture_Footer_Left")
        self.assertEqual("!$EXP[View_Mode_Wall_Expression]", footer.findtext("visible"))
        walls = next(e.text for e in _root("Includes_Views.xml").findall("expression")
                     if e.get("name") == "View_Mode_Wall_Expression")
        for view in range(510, 516):
            self.assertIn(f"$EXP[Exp_View_{view}]", walls)
        for view in list(range(500, 510)) + list(range(520, 529)) + [549]:
            self.assertNotIn(f"$EXP[Exp_View_{view}]", walls)
        info = _include("Includes_Dimensions.xml", "Dimension_Info")
        self.assertLessEqual(1080 - _number(info.findtext("bottom"), constants), _footer_top(constants))

    def test_tall_wall_tiles_give_one_rhythm_step_to_their_labels(self):
        # Taller cells (3.8.0: 390) pushed the second wall row's labels below the screen;
        # the tile now gives view_bar of its height to the labels and the cell stays.
        constants = _constants()
        bar = float(constants["view_bar"])
        self.assertEqual(float(constants["view_poster_item_h"]) - bar, float(constants["view_poster_labelled_item_h"]))
        self.assertEqual(float(constants["view_poster_wall_item_h"]) - bar,
                         float(constants["view_poster_wall_labelled_item_h"]))
        self.assertNotIn("view_poster_labelled_itemlayout_h", constants)
        self.assertNotIn("view_poster_wall_labelled_itemlayout_h", constants)
        # Widths keep each tile's aspect ratio
        for row, width, height in (
            ("List_Poster_Row", "view_poster_item_w", "view_poster_item_h"),
            ("List_Circle_Row", "view_poster_item_h", "view_poster_item_h"),
            ("List_Board_Row", "view_board_item_w", "view_poster_item_h"),
            ("List_Card_Row", "view_card_item_w", "view_poster_item_h"),
        ):
            ratio = float(constants[width]) / float(constants[height])
            labelled = float(constants[f"view_wall_labelled_item_w__{row}"]) / float(constants["view_poster_labelled_item_h"])
            self.assertAlmostEqual(ratio, labelled, places=3, msg=row)
        ratio = float(constants["view_poster_wall_item_w"]) / float(constants["view_poster_wall_item_h"])
        labelled = float(constants["view_poster_wall_labelled_item_w"]) / float(constants["view_poster_wall_labelled_item_h"])
        self.assertAlmostEqual(ratio, labelled, places=3)
        for name in ("view_poster_labelled_item_h", "view_poster_wall_labelled_item_h", "view_poster_wall_labelled_item_w",
                     "view_poster_wall_offset_x", "view_poster_wall_offset_y", "view_pad", "view_bar"):
            self.assertEqual("-" + constants[name], constants["-" + name], name)
        walls = _root("Includes_Views_Wall.xml")
        for view in ("View_512_Poster_Wall", "View_513_Circle_Wall", "View_514_Board_Wall"):
            self.assertEqual("true", walls.find(f"./include[@name='{view}']").findtext(".//param[@name='labels_below']"), view)
        for view in ("View_512_Poster_Wall", "View_513_Circle_Wall"):
            self.assertEqual("center", walls.find(f"./include[@name='{view}']").findtext(".//param[@name='labels_align']"), view)
        wall = _include("Includes_Views_Wall.xml", "View_Wall_Include")
        labelled = wall.find(".//include[@condition='$PARAM[labels_below] + !Skin.HasSetting(View.HideWidgetLabels)']")
        self.assertEqual("view_wall_labelled_item_w__$PARAM[include]", labelled.findtext("param[@name='item_w']"))
        self.assertEqual("view_poster_labelled_item_h", labelled.findtext("param[@name='item_h']"))
        self.assertIsNone(labelled.find("param[@name='itemlayout_h']"))

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

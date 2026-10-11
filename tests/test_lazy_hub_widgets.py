"""3.8.1: lazy Wall/Combined hub widgets, hub wall labels, and the layout maths of
View 515, the hub walls and the row-view scrollbar."""

import json
import math
import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


SKIN_ROOT = Path(__file__).resolve().parents[1]
SKIN = SKIN_ROOT / "1080i"
DATA = SKIN_ROOT / "shortcuts" / "generator" / "data"
SCREEN_H = 1080
SCREEN_W = 1920


def _root(path):
    return ET.parse(path).getroot()


def _include(file_name, name):
    node = _root(SKIN / file_name).find(f"./include[@name='{name}']")
    assert node is not None, (file_name, name)
    return node


def _constants():
    return {c.get("name"): c.text for c in _root(SKIN / "Includes_Constants.xml").iter("constant")}


def _setup_values(*names):
    """Values of generator setup files; for rules, the unconditional (True) fallback."""
    values = {}
    for name in names:
        root = _root(DATA / "setup" / name)
        for value in root.findall("value"):
            values[value.get("name")] = value.text or ""
        for rules in root.findall("rules"):
            for rule in rules.findall("rule"):
                if rule.findtext("condition") == "True":
                    values[rules.get("name")] = rule.findtext("value") or ""
    return values


def _render(template, values):
    """Substitute {name} like script.skinvariables does, then evaluate $MATH[...]."""
    text = template
    for _ in range(10):
        new = re.sub(r"\{(\w+)\}", lambda m: values.get(m.group(1), m.group(0)), text)
        if new == text:
            break
        text = new
    return re.sub(r"\$MATH\[([0-9+\- ]+)\]", lambda m: str(eval(m.group(1))), text)


ITEM = {
    "item": "homewidgets",
    "item_x": "3",
    "item_guid": "guid-504",
    "item_path": "plugin://plugin.video.example/?info=list",
    "item_label": "Example",
    "item_target": "",
    "item_widget_sortby": "",
    "item_widget_limit": "",
    "item_widget_style": "Poster",
    "window_id": "home",
}


class LazySelectorGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.values = {**_setup_values("widgets_row.xml", "widgets_lazy.xml"), **ITEM}

    def test_reached_is_the_selected_widget_its_neighbours_or_loaded(self):
        reached = _render("{widget_lazy_selector_reached}", self.values)
        self.assertEqual(
            "String.IsEqual(Container(601).ListItemNoWrap(-1).Property(guid),guid-504)"
            " | String.IsEqual(Container(601).ListItem.Property(guid),guid-504)"
            " | String.IsEqual(Container(601).ListItemNoWrap(1).Property(guid),guid-504)"
            " | [Integer.IsGreater(Container(504).NumItems,0)"
            " + !String.IsEqual(Container(504).ListItemAbsolute(0).Property(widget_lazy),true)]",
            reached,
        )
        self.assertNotIn("{", reached)

    def test_guid_matches_the_selector_property(self):
        self.assertEqual("{item_guid}", _setup_values("widgets_row.xml")["widget_guid"])
        selector = (DATA / "parts" / "widgets_selector.xmltemplate").read_text(encoding="utf-8")
        self.assertIn('<property name="guid">{widget_guid}</property>', selector)
        for name in ("home_widgets_wall_selector.xml", "home_widgets_combined_selector.xml"):
            base = (DATA / "base" / name).read_text(encoding="utf-8")
            self.assertIn("generator/data/parts/widgets_selector.xmltemplate", base)
            self.assertIn("generator/data/setup/widgets_row.xml", base)

    def test_path_variable_and_its_base(self):
        template = (DATA / "parts" / "widgets_lazy_selector_path.xmltemplate").read_text(encoding="utf-8")
        rendered = _root_from_text(_render(template, self.values))
        self.assertEqual("Widget_Lazy_Selector_Path_homewidgets_504", rendered.get("name"))
        value = rendered.find("value")
        self.assertEqual(_render("{widget_lazy_selector_reached}", self.values), value.get("condition"))
        self.assertEqual(ITEM["item_path"], value.text)

        base = _root(DATA / "base" / "home_widgets_lazy_selector.xml")
        self.assertEqual("generator/data/parts/widgets_lazy_paths.xmltemplate", base.findtext("template"))
        item = base.find(".//items/item")
        self.assertEqual("generator/data/parts/widgets_lazy_selector_path.xmltemplate", item.findtext("template"))
        self.assertEqual(
            ["generator/data/setup/widgets_row.xml", "generator/data/setup/widgets_lazy.xml"],
            [d.text for d in item.findall("datafile")],
        )
        # Every enabled widget gets a variable: the selector condition decides, not the index
        self.assertEqual(["{item_disabled}!=True"], [c.text for c in item.findall("condition")])
        widgets = (DATA / "base" / "home_widgets.xml").read_text(encoding="utf-8")
        self.assertIn("generator/data/base/home_widgets_lazy_selector.xml", widgets)

    def test_wall_and_combined_widgets_take_the_lazy_path(self):
        for base_name, template_name, include in (
            ("home_widgets_wall.xml", "widgets_wall.xmltemplate", "Hub_Wall_Widget"),
            ("home_widgets_combined.xml", "widgets_combined.xmltemplate", "Hub_Combined_Widget"),
        ):
            base = (DATA / "base" / base_name).read_text(encoding="utf-8")
            self.assertIn("generator/data/setup/widgets_lazy.xml", base, base_name)
            template = (DATA / "parts" / template_name).read_text(encoding="utf-8")
            self.assertNotIn(">{widget_path}<", template, template_name)
            rendered = _root_from_text(_render(template, self.values))
            self.assertEqual(include, rendered.get("content"))
            params = {p.get("name"): p.text for p in rendered.findall("param")}
            self.assertEqual("$VAR[Widget_Lazy_Selector_Path_homewidgets_504]", params["content"])
            self.assertEqual("true", params["lazy"])
            self.assertEqual(_render("{widget_lazy_selector_reached}", self.values), params["lazy_reached"])
            self.assertEqual("String.IsEqual(Container(601).ListItem.Property(guid),guid-504)", params["visible"])

    def test_selector_drops_widgets_that_loaded_empty(self):
        template = (DATA / "parts" / "widgets_selector.xmltemplate").read_text(encoding="utf-8")
        visible = _root_from_text(_render(template, {**self.values, "show_overlay": "", "hide_overlay": ""})).findtext("visible")
        self.assertEqual(
            "[!Integer.IsEqual(Container(504).NumItems,0)"
            " + !String.IsEqual(Container(504).ListItemAbsolute(0).Property(widget_lazy_empty),true)]"
            " | Container(504).IsUpdating",
            visible,
        )

    def test_generator_build_version_forces_a_rebuild(self):
        # script.skinvariables only rebuilds the generated includes when the generator json,
        # the profile, the build kwargs or the generated file change, not its data files.
        meta = json.loads((SKIN_ROOT / "shortcuts" / "skinvariables-generator.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(tuple(int(n) for n in meta["buildv"].split(".")), (0, 1, 6))
        self.assertIn({"datafile": "generator/data/base/home_widgets.xml"}, meta["genxml"])


def _root_from_text(text):
    return ET.fromstring(text.replace("&amp;", "&").replace("&", "&amp;"))


class LazyHubIncludeTests(unittest.TestCase):
    def test_hub_widgets_default_to_eager_loading(self):
        for name in ("Hub_Wall_Widget", "Hub_Combined_Widget"):
            include = _include("Includes_Hubs.xml", name)
            self.assertEqual("false", include.findtext("param[@name='lazy']"), name)
            self.assertEqual("true", include.findtext("param[@name='lazy_reached']"), name)

    def _lazy_items_before_content(self, container):
        children = list(container)
        lazy = [i for i, c in enumerate(children) if c.tag == "include" and c.get("content") == "Hub_Lazy_Items"]
        content = [i for i, c in enumerate(children) if c.tag == "content"]
        self.assertEqual(1, len(lazy))
        self.assertEqual(1, len(content))
        self.assertLess(lazy[0], content[0])
        node = children[lazy[0]]
        self.assertEqual("$PARAM[lazy]", node.get("condition"))
        self.assertEqual("$PARAM[lazy_reached]", node.findtext("param[@name='reached']"))
        self.assertEqual("$PARAM[id]", node.findtext("param[@name='id']"))

    def test_placeholder_and_marker_come_before_the_content(self):
        grid = _include("Includes_Hubs.xml", "Hub_Wall_Grid").find("include[@content='$PARAM[include]']")
        self._lazy_items_before_content(grid)
        combined = _include("Includes_Hubs.xml", "Hub_Combined_Widget").find("definition/include[@content='$PARAM[include]']")
        self._lazy_items_before_content(combined)
        items = _include("Includes_Hubs.xml", "Hub_Lazy_Items")
        self.assertEqual(["Widget_Lazy_Placeholder", "Widget_Lazy_Empty"], [i.get("content") for i in items.findall("include")])
        self.assertEqual("$PARAM[reached]", items.find("include").findtext("param[@name='reached']"))

    def test_wall_widget_passes_the_lazy_params_to_every_grid(self):
        widget = _include("Includes_Hubs.xml", "Hub_Wall_Widget")
        grids = [i for i in widget.iter("include") if i.get("content") == "Hub_Wall_Grid"]
        self.assertEqual(3, len(grids))
        for grid in grids:
            for name in ("id", "include", "content", "lazy", "lazy_reached", "target", "sortby", "sortorder", "limit"):
                self.assertEqual(f"$PARAM[{name}]", grid.findtext(f"param[@name='{name}']"), name)

    def test_empty_marker_keeps_itself_and_skips_loading(self):
        item = _include("Includes_Widgets.xml", "Widget_Lazy_Empty").find("content/item")
        self.assertEqual("true", item.find("property[@name='widget_lazy_empty']").text)
        visible = item.findtext("visible")
        self.assertTrue(visible.startswith("!Container($PARAM[id]).IsUpdating + "))
        self.assertIn("Integer.IsEqual(Container($PARAM[id]).NumItems,0)", visible)
        self.assertIn(
            "[Integer.IsEqual(Container($PARAM[id]).NumItems,1) + "
            "String.IsEqual(Container($PARAM[id]).ListItemAbsolute(0).Property(widget_lazy_empty),true)]",
            visible,
        )
        # The marker is not the placeholder, so a widget showing it counts as loaded.
        self.assertNotIn("widget_lazy)", visible)


class HubWallLabelTests(unittest.TestCase):
    def setUp(self):
        self.expressions = {
            e.get("name"): e.text for e in _root(SKIN / "Includes_Widgets.xml").findall("expression")
        }

    def test_every_wall_include_has_both_expressions(self):
        rules = _root(DATA / "setup" / "widgets_include_wall.xml").find("rules[@name='widget_include']")
        includes = {r.findtext("value") for r in rules.findall("rule")}
        # Fixed wall widgets elsewhere in the skin
        for file_name in ("Includes_Hubs.xml", "Includes_LiveTV.xml", "Includes_Addons.xml"):
            includes |= set(re.findall(r'name="include">(List_\w+_Row)<', (SKIN / file_name).read_text(encoding="utf-8")))
        includes.add(_include("Includes_Hubs.xml", "Hub_Wall_Widget").findtext("param[@name='include']"))
        for include in includes:
            for family in ("Exp_Wall_TallTile__", "Exp_Wall_CentredLabels__"):
                self.assertIn(self.expressions.get(family + include), ("true", "false"), family + include)
        for include in ("List_Poster_Row", "List_Circle_Row", "List_Board_Row"):
            self.assertEqual("true", self.expressions[f"Exp_Wall_TallTile__{include}"])
            self.assertIsNotNone(_include("Includes_Widgets.xml", f"Widget_Busy_BlankItems__{include}_Labelled"))
            self.assertIn(f"view_wall_labelled_item_w__{include}", _constants())

    def test_grids_label_their_tiles_and_follow_text_labels(self):
        widget = _include("Includes_Hubs.xml", "Hub_Wall_Widget")
        grids = [i for i in widget.iter("include") if i.get("content") == "Hub_Wall_Grid"]
        off = "Skin.HasSetting(View.HideWidgetLabels)"
        labelled = [g for g in grids if g.find("param[@name='item_h']") is not None]
        self.assertEqual(2, len(labelled))
        for grid in labelled:
            self.assertIn("$EXP[Exp_Wall_TallTile__$PARAM[include]]", grid.get("condition"))
            self.assertIn("!" + off, grid.get("condition"))
            self.assertEqual("view_poster_labelled_item_h", grid.findtext("param[@name='item_h']"))
            self.assertEqual("view_wall_labelled_item_w__$PARAM[include]", grid.findtext("param[@name='item_w']"))
            self.assertEqual("$PARAM[include]_Labelled", grid.findtext("param[@name='busy_include']"))
        self.assertEqual({"center", "left"}, {g.findtext("param[@name='labels_align']") for g in labelled})
        plain = [g for g in grids if g.find("param[@name='item_h']") is None][0]
        self.assertEqual("![$EXP[Exp_Wall_TallTile__$PARAM[include]]] | " + off, plain.get("condition"))
        self.assertEqual("$PARAM[include]", plain.findtext("param[@name='busy_include']"))

        row = _include("Includes_Hubs.xml", "Hub_Wall_Grid").find("include[@content='$PARAM[include]']")
        self.assertEqual("true", row.findtext("param[@name='show_labels']"))
        self.assertEqual(off, row.findtext("param[@name='hide_labels']"))
        self.assertIsNone(row.find("param[@name='itemlayout_h']"))
        busy = [b for b in _include("Includes_Hubs.xml", "Hub_Wall_Grid").findall("include") if b.get("content") == "Widget_Busy"]
        self.assertEqual(["250", "600"], [b.findtext("top") for b in busy])
        self.assertTrue(all(b.findtext("param[@name='include']") == "$PARAM[busy_include]" for b in busy))

    def test_two_whole_rows_with_labels_on_and_off(self):
        c = _constants()
        cell = float(c["view_poster_itemlayout_h"])
        top, inset = 290, float(c["view_bar"])
        label_end = 10 + 80 - 7  # Layout_Labels: block top 10, height 80, textbox inset 7
        for tile in (float(c["view_poster_item_h"]), float(c["view_poster_labelled_item_h"])):
            self.assertLessEqual(top + inset + cell + tile + label_end, SCREEN_H, tile)
        # Off keeps the 3.8.0 geometry; on, the tile gives one rhythm step to the labels:
        # tile + 40 gap + 40 labels = cell (the label text then runs into the gap, as it did
        # with the 3.8.0 390 cells).
        self.assertEqual(float(c["view_poster_labelled_item_h"]) + 2 * float(c["view_bar"]), cell)


class PosterWallDetailsMathsTests(unittest.TestCase):
    def test_three_whole_rows_and_no_fourth(self):
        c = _constants()
        top, height = float(c["view_poster_wall_grid_t"]), float(c["view_poster_wall_grid_h"])
        cell, inset = float(c["view_poster_wall_itemlayout_h"]), float(c["view_poster_wall_offset_y"])
        label_end = 10 + 80 - 7
        self.assertLessEqual(top + height, SCREEN_H)
        self.assertEqual(3, math.floor(height / cell))
        # Fourth row starts exactly where the grid clips
        self.assertGreaterEqual(3 * cell + inset, height)
        for tile, labels in ((float(c["view_poster_wall_item_h"]), 0), (float(c["view_poster_wall_labelled_item_h"]), label_end)):
            self.assertLessEqual(2 * cell + inset + tile + labels, height, tile)
        grid_w = SCREEN_W - float(c["view_poster_wall_grid_l"]) - float(c["view_poster_wall_grid_r"])
        self.assertEqual(5, math.floor(grid_w / float(c["view_poster_wall_itemlayout_w"])))

    def test_grid_uses_the_constants(self):
        view = _include("Includes_Views_Wall.xml", "View_515_Poster_Wall_Details")
        calls = {i.get("condition"): i for i in view.iter("include") if i.get("content") == "View_515_Grid"}
        on = calls["!Skin.HasSetting(View.HideWidgetLabels)"]
        off = calls["Skin.HasSetting(View.HideWidgetLabels)"]
        self.assertEqual("view_poster_wall_labelled_item_h", on.findtext("param[@name='item_h']"))
        self.assertEqual("view_poster_wall_labelled_item_w", on.findtext("param[@name='item_w']"))
        self.assertEqual("view_poster_wall_item_h", off.findtext("param[@name='item_h']"))
        grid = _include("Includes_Views_Wall.xml", "View_515_Grid").find("include")
        self.assertEqual("view_poster_wall_itemlayout_h", grid.findtext("param[@name='itemlayout_h']"))
        self.assertEqual("view_poster_wall_grid_t", grid.findtext("top"))
        self.assertEqual("view_poster_wall_grid_h", grid.findtext("height"))
        self.assertIsNone(grid.find("bottom"))


class RowScrollbarTests(unittest.TestCase):
    def test_scrollbar_sits_below_the_tall_row_labels(self):
        c = _constants()
        strip = _include("Includes_Views.xml", "View_Scrollbar_Strip")
        group = next(g for g in strip.iter("control") if g.find("control[@id='60']") is not None)
        self.assertEqual("view_pad", group.findtext("bottom"))
        self.assertEqual("scrollbar_w", group.findtext("height"))
        bar_top = SCREEN_H - float(c["view_pad"]) - float(c["scrollbar_w"])
        label_block_end = float(c["view_row"]) + float(c["view_pad"]) + float(c["view_poster_item_h"]) + 10 + 80
        self.assertGreaterEqual(bar_top, label_block_end)
        sub = _include("Includes_Views.xml", "View_Line_SubLabel").find("control")
        # Footer bar spans 960-1000; the sublabel is centred on the bar (990-1000)
        self.assertEqual(float(c["view_bar"]) - float(c["scrollbar_w"]) / 2, float(sub.findtext("centertop")))


if __name__ == "__main__":
    unittest.main()

"""The YouTube hub (window 1110) is wired into every hardcoded hub list like hubs 1101-1104,
ships default menus, and is enabled once when SmartTube is installed."""

import json
import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


SKIN_ROOT = Path(__file__).resolve().parents[1]
SKIN = SKIN_ROOT / "1080i"
SHORTCUTS = SKIN_ROOT / "shortcuts"
ICONS = "resource://resource.images.arctic.fuse.3/extras/icons/"
PLUGIN = "plugin://plugin.video.smarttube/"
# Order of the hub switcher: Search, Home, the custom hubs, then the fixed hubs.
ORDER = ["1105", "Home", "1101", "1102", "1103", "1104", "1110", "1106", "1107", "1108"]
TABS = ["home", "1101", "1102", "1103", "1104", "1110"]


def _root(name):
    return ET.parse(SKIN / name).getroot()


def _include(name, include):
    return next(n for n in _root(name).iter("include") if n.get("name") == include)


def _params(node):
    return {p.get("name"): (p.text or "") for p in node.findall("param")}


def _toggle_empty(window):
    return f"String.IsEmpty(Skin.String(HomeSwitcher.{window}.Toggle))"


class YouTubeHubWindowTests(unittest.TestCase):
    def test_window_1110_is_a_hub_and_unique(self):
        ids = [(p.name, _root(p.name).get("id")) for p in SKIN.glob("Custom_*.xml")]
        self.assertEqual([("Custom_1110_Hub.xml", "1110")], [i for i in ids if i[1] == "1110"])
        hub = _root("Custom_1110_Hub.xml")
        self.assertEqual("1110", hub.findtext("include[@content='Hub_Onload']/param[@name='window_id']"))
        self.assertEqual("1110", hub.findtext("controls/include[@content='Hub_Window']/param[@name='window']"))

    def test_hub_onload_names_the_hub_youtube(self):
        calls = {p["window"]: p for p in map(_params, _include("Includes_Hubs.xml", "Hub_Onload").findall(
            "definition/include[@content='Hub_Onload_Window']"))}
        self.assertEqual(["Home", "1101", "1102", "1103", "1104", "1110"], list(calls))
        self.assertEqual("YouTube", calls["1110"]["defaultname"])

    def test_icon_defaults_to_youtube(self):
        variable = next(n for n in _root("Includes_Home.xml").iter("variable") if n.get("name") == "Home_Icon_1110")
        values = variable.findall("value")
        self.assertEqual("!String.IsEmpty(Skin.String(HomeSwitcher.1110.Icon))", values[0].get("condition"))
        self.assertEqual(ICONS + "youtube.png", values[-1].text)

    def test_tmdbhelper_tracks_the_hub_window(self):
        onloads = [n.text for n in _root("Home.xml").findall("onload")]
        local_ids = next(t for t in onloads if "TMDbHelper.UseLocalWindowIDs" in t)
        self.assertIn("|11110", local_ids)
        overlay = next(n for n in _root("Includes_Overlay.xml").iter("variable") if n.get("name") == "Overlay_WidgetContainer")
        self.assertIn("Window.IsVisible(11110)", [v.get("condition") for v in overlay.findall("value")])


class HubListTests(unittest.TestCase):
    def test_switcher_items_follow_the_hub_order(self):
        items = _include("Includes_Home.xml", "Home_ControlList_Items")
        called = [n.get("content").rsplit("_", 1)[1] for n in items.findall("definition/include")]
        self.assertEqual(ORDER, called)
        for position, window in enumerate(ORDER[2:], 2):
            with self.subTest(window=window):
                item = _include("Includes_Home.xml", f"Home_ControlList_Item_{window}")
                visible = _params(item.find("include"))["visible"]
                expected = " | ".join(f"Window.IsVisible({w})" for w in ORDER[:position + 1])
                self.assertEqual(expected, visible)

    def test_every_hub_visibility_chain_lists_1110(self):
        # Every other "is a hub shown" chain names 1104; each must name 1110 as well.
        switcher = {f"Home_ControlList_Item_{w}" for w in ORDER}
        checked = 0
        for path in sorted(SKIN.glob("*.xml")):
            root = ET.parse(path).getroot()
            skip = {id(n) for d in root.iter("include") if d.get("name") in switcher for n in d.iter()}
            for node in root.iter():
                if id(node) in skip:
                    continue
                for value in [node.text or "", *node.attrib.values()]:
                    if "Window.IsVisible(1104)" in value and value != "Window.IsVisible(1104)":
                        checked += 1
                        with self.subTest(file=path.name, tag=node.tag):
                            self.assertIn("Window.IsVisible(1110)", value)
        self.assertGreaterEqual(checked, 5)

    def test_tab_bar_end_caps_follow_the_enabled_hubs(self):
        calls = [_params(n) for n in _include("Includes_Home.xml", "Home_Switcher_Horz").iter("include")
                 if n.get("content") == "Home_Object"]
        self.assertEqual(TABS, [c["window"] for c in calls])
        for index, call in enumerate(calls):
            with self.subTest(window=call["window"]):
                later = TABS[index + 1:]
                expected = " + ".join(_toggle_empty(w) for w in later) if later else "true"
                self.assertEqual(expected, call["last"])
                self.assertEqual(call["window"][-2:] if call["window"] != "home" else "00", call["id"])

    def test_submenu_controls_exist_for_every_tab(self):
        home = _root("Includes_Home.xml")
        ids = [t[-2:] if t != "home" else "00" for t in TABS]
        counters = [_params(n) for n in home.iter("include") if n.get("content") == "Home_Submenu_Counter"]
        self.assertEqual(list(zip(TABS, ids)), [(c["window"], c["id"]) for c in counters])
        for include in ("Home_Horz_Submenu", "Home_Vert_Submenu"):
            with self.subTest(include=include):
                node = _include("Includes_Home.xml", include)
                starts = [_params(n)["id"] for n in node.iter("include") if n.get("content") == "Home_Submenu_Start"]
                panels = [_params(n) for n in node.iter("include") if n.get("content") == "Home_Submenu_Panel"]
                self.assertEqual(ids, starts)
                self.assertEqual(list(zip(TABS, ids)), [(p["window"], p["id"]) for p in panels])
        vert = [_params(n)["window"] for n in _include("Includes_Home.xml", "Home_Switcher_Vert").iter("include")
                if n.get("content") == "Home_Object_VertIcon"]
        self.assertEqual(["1105", "home", "1101", "1102", "1103", "1104", "1110", "1106", "1107", "1108"], vert)
        dialog = _root("Custom_1181_Dialog_Submenu.xml")
        self.assertIn(("Window.IsVisible(1110)", "SetFocus(7010)"),
                      [(n.get("condition"), n.text) for n in dialog.findall("onload")])

    def test_menu_node_lists_offer_the_youtube_menus(self):
        menus = ["homewidgets", "1101widgets", "1102widgets", "1103widgets", "1104widgets", "1110widgets",
                 "homesubmenu", "1101submenu", "1102submenu", "1103submenu", "1104submenu", "1110submenu",
                 "powermenu", "powertray"]
        for name in ("Dialog_DialogContextMenu.xml", "Includes_Views.xml"):
            with self.subTest(file=name):
                text = (SKIN / name).read_text(encoding="utf-8")
                found = re.findall(r"set_listitem_to_menunode=([^,]+),", text)
                self.assertTrue(found)
                self.assertTrue(all(value.split("||") == menus for value in found))

    def test_shortcut_editor_and_hub_settings_cover_1110(self):
        rows = {n.findtext("property[@name='editmenu']"): n for n in _root("Custom_1115_Window_Shortcuts.xml").iter("item")}
        row = rows["menu=1110"]
        self.assertEqual("HomeSwitcher.1110", row.findtext("property[@name='rename']"))
        self.assertEqual("$INFO[Skin.String(HomeSwitcher.1110.Toggle)]", row.findtext("property[@name='enabled']"))
        self.assertEqual("$VAR[Home_Icon_1110]", row.findtext("icon"))
        self.assertEqual(rows["menu=1104"].findall("onclick")[0].text, row.findall("onclick")[0].text)
        shortcuts = _root("Dialog_DialogShortcuts.xml")
        expression = next(n.text for n in shortcuts.iter("expression") if n.get("name") == "DialogShortcuts_IsSubGrouping_Expression")
        self.assertIn("menu=1110submenu", expression)
        items = _include("Dialog_DialogShortcuts.xml", "DialogCustom_Shortcuts_Items")
        self.assertIn(("String.IsEqual(Window(Home).Property(Dialog.1124.Window),HomeSwitcher.1110)", "1110"),
                      [(n.get("condition"), _params(n).get("window")) for n in items.findall("include")])
        hubs = _params(_include("Dialog_DialogShortcuts.xml", "DialogShortcuts_Window_Settings_Hubs"))
        self.assertIn("String.IsEqual(Container(30000).ListItem.Property(editmenu),menu=1110)", hubs["visible"])

    def test_generator_builds_the_youtube_menus(self):
        for name, menu in (("home_widgets.xml", "1110widgets"), ("home_submenu.xml", "1110submenu")):
            with self.subTest(file=name):
                lists = ET.parse(SHORTCUTS / "generator/data/base" / name).getroot().find("lists")
                windows = {n.get("name"): n.findtext("value[@name='window_id']") for n in lists.findall("list")}
                self.assertEqual("1110", windows[menu])


class StartupTests(unittest.TestCase):
    """Evaluate skinvariables-startup.json and -splash.json the way script.skinvariables
    does (operations.py get_actions_list): strings are actions, lists recurse, and a rule
    dict whose rules all pass adds the dict value and ends the enclosing list."""

    @staticmethod
    def actions(entries, conditions):
        result = []
        for entry in entries if isinstance(entries, list) else [entries]:
            if isinstance(entry, str):
                result.append(entry)
            elif isinstance(entry, list):
                result += StartupTests.actions(entry, conditions)
            elif all(conditions(rule) for rule in entry["rules"]):
                result += StartupTests.actions(entry["value"], conditions)
                break
        return result

    def startup(self, true_conditions):
        meta = json.loads((SHORTCUTS / "skinvariables-startup.json").read_text())

        def conditions(rule):
            if rule.startswith("!"):
                return rule[1:] not in true_conditions
            return rule in true_conditions or rule.startswith("String.IsEmpty(")
        return self.actions(meta["actions"], conditions)

    def test_hub_is_enabled_once_when_smarttube_is_installed(self):
        actions = self.startup({"System.HasAddon(plugin.video.smarttube)", "Skin.HasSetting(DefaultConfig.InitDone)"})
        self.assertIn("Skin.SetString(HomeSwitcher.1110.Toggle,true)", actions)
        self.assertIn("Skin.SetBool(Migration.YouTubeHub)", actions)
        self.assertIn("Skin.SetString(HomeSwitcher.1110.Mode,Standard)", actions)
        # Every later startup action still runs.
        self.assertIn("SetProperty(ReloadDone,1)", actions)
        for state in ({"Skin.HasSetting(Migration.YouTubeHub)", "System.HasAddon(plugin.video.smarttube)"}, set()):
            with self.subTest(state=state):
                actions = self.startup(state | {"Skin.HasSetting(DefaultConfig.InitDone)"})
                self.assertNotIn("Skin.SetString(HomeSwitcher.1110.Toggle,true)", actions)
                self.assertNotIn("Skin.SetBool(Migration.YouTubeHub)", actions)
                self.assertIn("SetProperty(ReloadDone,1)", actions)

    def test_splash_preloads_the_hub(self):
        meta = json.loads((SHORTCUTS / "skinvariables-splash.json").read_text())
        actions = self.actions(meta["actions"][0]["value"], lambda rule: rule != "String.IsEmpty(x)")
        windows = [a[15:-1] for a in actions if a.startswith("ActivateWindow(")]
        self.assertEqual(["1101", "1102", "1103", "1104", "1110", "1106", "1107", "1108", "Home"], windows)


class DefaultMenuTests(unittest.TestCase):
    def menu(self, name):
        return json.loads((SHORTCUTS / f"skinvariables-shortcut-{name}.json").read_text(encoding="utf-8"))

    def test_tabs(self):
        menu = self.menu("1110submenu")
        self.assertEqual(
            [("Subscriptions", "subscriptions/"), ("Channels", "channels/"), ("History", "history/"),
             ("Watch later", "watch_later/"), ("Playlists", "playlists/"), ("Search", "search/")],
            [(i["label"], i["path"][len(PLUGIN):]) for i in menu])
        for item in menu:
            self.assertTrue(item["path"].startswith(PLUGIN))
            self.assertEqual("videos", item["target"])
            self.assertTrue(item["icon"].startswith(ICONS))

    def test_widgets(self):
        menu = self.menu("1110widgets")
        self.assertEqual(
            [("Continue watching", "continue/"), ("Latest from subscriptions", "subscriptions/"),
             ("Live now", "live_now"), ("Recommended", "recommended/"), ("Trending", "trending/"),
             ("Music", "explore/music/"), ("Gaming", "explore/gaming/"), ("News", "explore/news/"),
             ("Sports", "explore/sports/")],
            [(i["label"], i["path"][len(PLUGIN):]) for i in menu])
        for item in menu:
            self.assertTrue(item["path"].startswith(PLUGIN))
            self.assertEqual("videos", item["target"])
            self.assertEqual("Landscape", item["widget_style"])
            self.assertTrue(item["icon"].startswith(ICONS))


if __name__ == "__main__":
    unittest.main()

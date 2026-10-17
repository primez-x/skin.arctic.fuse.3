"""Profile and skin contracts for the Plex source migration."""

import json
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

from test_legacy_image_path_migration import SKIN_ROOT, _load_service

LISTS = "plugin://plugin.video.plexkodiconnect/?mode=discover_lists"
TRENDING = "plugin://plugin.video.plexkodiconnect/?mode=discover_hub&hub_id=trending-for-you"


class PlexSourceMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.profile = root / "profile"
        self.settings = self.profile / "addon_data/skin.arctic.fuse.3/settings.xml"
        self.nodes = self.profile / "addon_data/script.skinvariables/nodes/skin.arctic.fuse.3"
        self.settings.parent.mkdir(parents=True)
        self.nodes.mkdir(parents=True)
        self.values = {}
        self.commands = []
        self.service = _load_service(root / "skin", self.profile, root / "resource", self.values, [])
        self.service.xbmc.getInfoLabel = lambda query: next(
            (value for key, value in self.values.items() if key.lower() == query[12:-1].lower()), ""
        ) if query.startswith("Skin.String(") else ""
        self.service.xbmc.getCondVisibility = lambda query: next(
            (value for key, value in self.values.items() if key.lower() == query[16:-1].lower()), ""
        ) == "true"

        def execute(command):
            self.commands.append(command)
            match = re.fullmatch(r"Skin\.(SetString|SetBool|Reset)\(([^,()]+)(?:,(.*))?\)", command)
            if match:
                key = next((key for key in self.values if key.lower() == match[2].lower()), match[2])
                self.values[key] = match[3] if match[1] == "SetString" else "true" if match[1] == "SetBool" else ""

        self.service.xbmc.executebuiltin = execute

    def write_settings(self, values, bool_ids=()):
        self.values.update(values)
        root = ET.Element("settings")
        for key, value in values.items():
            ET.SubElement(root, "setting", id=key, type="bool" if key in bool_ids else "string").text = value
        self.settings.write_text(ET.tostring(root, encoding="unicode"), encoding="utf-8")

    def migrate(self):
        self.assertTrue(callable(getattr(self.service, "_migrate_plex_sources", None)), "Plex profile migration is absent")
        return self.service._migrate_plex_sources()

    def test_all_six_rating_slots_migrate_and_second_run_has_no_commands(self):
        slots = [f"CustomRating.{content}.Item{index:02}" for content in ("Movies", "TVShows") for index in (1, 2, 3)]
        self.write_settings(dict.fromkeys(slots, "Trakt"))
        self.assertTrue(self.migrate())
        self.assertEqual(["Plex"] * 6, [self.values[key] for key in slots])
        self.commands.clear()
        self.assertFalse(self.migrate())
        self.assertEqual([], self.commands)

    def test_lowercase_rating_slots_calendar_and_unrelated_values(self):
        slots = [f"customrating.{content}.item0{index}" for content in ("movies", "tvshows") for index in (1, 2, 3)]
        values = dict.fromkeys(slots, "Trakt")
        values.update({"homeswitcher.1106.upnextmode": "trakt_calendar", "custom.widget": "unchanged"})
        self.write_settings(values)
        self.assertTrue(self.migrate())
        self.assertEqual(["Plex"] * 6, [self.values[key] for key in slots])
        self.assertEqual("library_nextaired", self.values["homeswitcher.1106.upnextmode"])
        self.assertEqual("unchanged", self.values["custom.widget"])
        self.commands.clear()
        self.assertFalse(self.migrate())
        self.assertEqual([], self.commands)

    def test_lowercase_badge_bools_transfer_saved_choices_over_new_defaults(self):
        for enabled in ("true", "false"):
            for explicit in (None, "true", "false"):
                with self.subTest(enabled=enabled, explicit=explicit):
                    self.values.clear()
                    self.commands.clear()
                    values = {f"indicator.trakt{suffix}": enabled for suffix in ("watchlist", "favourites")}
                    if explicit is not None:
                        values.update({f"indicator.plex{suffix}": explicit for suffix in ("watchlist", "favourites")})
                    values["hub.home.disablesubmenu"] = "true"
                    self.write_settings(values, bool_ids=values)
                    with patch.object(self.service.xbmc, "getInfoLabel", wraps=self.service.xbmc.getInfoLabel) as labels:
                        self.assertTrue(self.migrate())
                    for suffix in ("watchlist", "favourites"):
                        old, new = f"indicator.trakt{suffix}", f"indicator.plex{suffix}"
                        self.assertEqual("", self.values[old])
                        actual = next((value for key, value in self.values.items() if key.lower() == new), "false")
                        self.assertEqual(enabled, actual or "false")
                    self.assertEqual("true", self.values["hub.home.disablesubmenu"])
                    queried = {call.args[0][12:-1].lower() for call in labels.call_args_list}
                    self.assertTrue(set(values).isdisjoint(queried))
                    self.assertFalse(any(command.lower().startswith("skin.setstring(indicator.") for command in self.commands))
                    self.assertTrue(all(node.get("type") == "bool" for node in ET.parse(self.settings).iter("setting")))
                    self.commands.clear()
                    self.assertFalse(self.migrate())
                    self.assertEqual([], self.commands)

    def test_lowercase_saved_path_and_case_variant_paired_label(self):
        for label_id in ("homeswitcher.home.shortcut.label", "HomeSwitcher.Home.Shortcut.Label"):
            with self.subTest(label_id=label_id):
                self.values.clear()
                self.write_settings({"homeswitcher.home.shortcut.path": "DefaultSearch-TMDBListsTrakt", label_id: "Old List", "homeswitcher.home.mode": "Wall"})
                self.assertTrue(self.migrate())
                self.assertEqual(LISTS, self.values["homeswitcher.home.shortcut.path"])
                self.assertEqual("My Plex Lists", self.values[label_id])
                self.assertEqual("Wall", self.values["homeswitcher.home.mode"])
                self.commands.clear()
                self.assertFalse(self.migrate())
                self.assertEqual([], self.commands)

    def test_badge_bools_and_calendar_migrate_without_resetting_customization(self):
        self.write_settings({"Indicator.TraktWatchlist": "true", "Indicator.TraktFavourites": "false", "HomeSwitcher.1106.UpNextMode": "trakt_calendar", "CustomRating.Movies.Item01": "IMDb", "CustomRating.TVShows.Item03": "Versions", "Custom.Widget": "unchanged"})
        self.assertTrue(self.migrate())
        self.assertEqual("true", self.values["Indicator.PlexWatchlist"])
        self.assertEqual("", self.values.get("Indicator.PlexFavourites", ""))
        self.assertEqual("", self.values["Indicator.TraktWatchlist"])
        self.assertEqual("", self.values["Indicator.TraktFavourites"])
        self.assertEqual("library_nextaired", self.values["HomeSwitcher.1106.UpNextMode"])
        self.assertEqual("IMDb", self.values["CustomRating.Movies.Item01"])
        self.assertEqual("Versions", self.values["CustomRating.TVShows.Item03"])
        self.assertEqual("unchanged", self.values["Custom.Widget"])
        self.commands.clear()
        self.assertFalse(self.migrate())
        self.assertEqual([], self.commands)

    def test_boolean_settings_are_not_read_through_the_string_api(self):
        self.write_settings({'Hub.Home.DisableSubmenu': 'true', 'OSD.DisplayInfoOnControls': 'true'})
        root = ET.parse(self.settings)
        for node in root.iter('setting'):
            node.set('type', 'bool')
        root.write(self.settings, encoding='unicode')
        labels = []
        original = self.service.xbmc.getInfoLabel
        self.service.xbmc.getInfoLabel = lambda query: labels.append(query) or original(query)
        self.migrate()
        self.assertNotIn('Skin.String(Hub.Home.DisableSubmenu)', labels)
        self.assertNotIn('Skin.String(OSD.DisplayInfoOnControls)', labels)

    def test_existing_plex_badge_preference_wins(self):
        self.write_settings({"Indicator.TraktWatchlist": "true", "Indicator.PlexWatchlist": "false", "Migration.PlexBadges": "1"})
        self.migrate()
        self.assertEqual("false", self.values["Indicator.PlexWatchlist"])
        self.assertEqual("true", self.values["Indicator.TraktWatchlist"])
        self.assertEqual([], self.commands)

    def test_badge_migration_uses_saved_values_before_runtime_visibility(self):
        values = {"indicator.traktwatchlist": "true", "indicator.traktfavourites": "true"}
        self.write_settings(values, bool_ids=values)
        self.service.xbmc.getCondVisibility = lambda query: False
        self.assertTrue(self.migrate())
        self.assertEqual("true", self.values["Indicator.PlexWatchlist"])
        self.assertEqual("true", self.values["Indicator.PlexFavourites"])

    def test_saved_routes_migrate_across_sibling_files_with_backups(self):
        routes = ["trakt_searchlists", "trakt_trendinglists", "trakt_popularlists", "trakt_likedlists", "trakt_mylists", "trakt_inlists", "trakt_userslists", "trakt_userlist", "random_trendinglists", "random_popularlists", "random_likedlists", "random_mylists", "trakt_becauseyouwatched", "trakt_becausemostwatched"]
        for index, info in enumerate(routes):
            path = self.nodes / f"widgets-{index}.json"
            route = f"plugin://plugin.video.themoviedb.helper/?tmdb_type=movie&info={info}&query=old"
            saved = {"nodes": [{"path": route, "label": "Old source", "icon": "custom.png", "target": "videos"}], "custom": "prefix " + route}
            path.write_text(json.dumps(saved), encoding="utf-8")
        self.assertTrue(self.migrate())
        for index, info in enumerate(routes):
            with self.subTest(info=info):
                path = self.nodes / f"widgets-{index}.json"
                saved = json.loads(path.read_text())
                seed = info.startswith("trakt_because")
                self.assertEqual(TRENDING if seed else LISTS, saved["nodes"][0]["path"])
                self.assertEqual("Plex: Trending for You" if seed else "My Plex Lists", saved["nodes"][0]["label"])
                self.assertEqual("custom.png", saved["nodes"][0]["icon"])
                self.assertTrue(saved["custom"].startswith("prefix plugin://plugin.video.themoviedb.helper/"))
                self.assertTrue(path.with_name(path.name + ".before-plex-source-migration").exists())
        snapshots = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.nodes.iterdir()}
        self.assertFalse(self.migrate())
        self.assertEqual(snapshots, {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.nodes.iterdir()})

    def test_symbolic_shortcut_and_builtin_routes_migrate_without_prompt(self):
        path = self.nodes / "search.json"
        path.write_text(json.dumps([{"path": "DefaultSearch-TMDBListsTrakt", "name": "Trakt Lists"}, {"path": "ActivateWindow(Videos,plugin://plugin.video.themoviedb.helper/?info=trakt_searchlists&query=old,return)", "label": "Trakt Lists"}]))
        self.migrate()
        migrated = json.loads(path.read_text())
        self.assertEqual({"path": LISTS, "name": "My Plex Lists"}, migrated[0])
        self.assertEqual(f"ActivateWindow(Videos,{LISTS},return)", migrated[1]["path"])

    def test_unrelated_and_malformed_profiles_remain_byte_identical(self):
        examples = {"malformed.json": '{"path":', "unrelated.json": json.dumps([{"path": "plugin://custom/?info=trakt_searchlists", "label": "My custom widget"}, {"path": "plugin://plugin.video.themoviedb.helper/?info=search&query=trakt_searchlists", "label": "Custom"}, {"path": "plugin://plugin.video.themoviedb.helper.evil/?info=trakt_searchlists"}, {"path": "plugin://plugin.video.themoviedb.helper/?info=mdblist_searchlists"}])}
        self.settings.write_text("<settings><broken>")
        for name, value in examples.items():
            (self.nodes / name).write_text(value)
        self.assertFalse(self.migrate())
        self.assertEqual("<settings><broken>", self.settings.read_text())
        self.assertEqual(examples, {p.name: p.read_text() for p in self.nodes.iterdir()})
        self.assertEqual([], self.commands)

    def test_failed_atomic_write_preserves_saved_profile(self):
        path = self.nodes / "widgets.json"
        original = json.dumps({"path": "DefaultSearch-TMDBListsTrakt"})
        path.write_text(original)
        with patch.object(self.service.os, "replace", side_effect=OSError("disk full")):
            self.assertFalse(self.migrate())
        self.assertEqual(original, path.read_text())
        self.assertEqual([], list(self.nodes.glob("*.tmp")))

    def test_quoted_and_two_argument_builtin_routes_migrate(self):
        path = self.nodes / "commands.json"
        path.write_text(json.dumps([
            {"path": 'ActivateWindow(Videos,"plugin://plugin.video.themoviedb.helper/?info=trakt_userlist&list_slug=old",return)', "label": "Old List"},
            {"path": 'ActivateWindow(Videos,plugin://plugin.video.themoviedb.helper/?info=trakt_mylists)', "label": "Old List"},
            {"path": 'RunPlugin("plugin://plugin.video.themoviedb.helper/?info=trakt_becauseyouwatched")', "label": "Old seed"},
        ]))
        self.assertTrue(self.migrate())
        values = json.loads(path.read_text())
        self.assertEqual('ActivateWindow(Videos,"' + LISTS + '",return)', values[0]["path"])
        self.assertEqual('ActivateWindow(Videos,' + LISTS + ')', values[1]["path"])
        self.assertEqual('RunPlugin("' + TRENDING + '")', values[2]["path"])
        self.assertEqual("Plex: Trending for You", values[2]["label"])

    def test_invalid_utf8_profile_data_remains_unchanged(self):
        self.settings.write_bytes(b"<settings>\xff</settings>")
        path = self.nodes / "invalid.json"
        path.write_bytes(b'{"path": "\xff"}')
        self.assertFalse(self.migrate())
        self.assertEqual(b"<settings>\xff</settings>", self.settings.read_bytes())
        self.assertEqual(b'{"path": "\xff"}', path.read_bytes())

    def test_live_saved_shortcut_settings_migrate_with_associated_label(self):
        self.write_settings({"HomeSwitcher.Home.Shortcut.Path": 'ActivateWindow(Videos,plugin://plugin.video.themoviedb.helper/?info=trakt_userlist,return)', "HomeSwitcher.Home.Shortcut.Label": "Old List", "HomeSwitcher.Home.Mode": "Wall"})
        self.assertTrue(self.migrate())
        self.assertEqual('ActivateWindow(Videos,' + LISTS + ',return)', self.values["HomeSwitcher.Home.Shortcut.Path"])
        self.assertEqual("My Plex Lists", self.values["HomeSwitcher.Home.Shortcut.Label"])
        self.assertEqual("Wall", self.values["HomeSwitcher.Home.Mode"])
        self.assertFalse(self.migrate())

    def test_version_change_runs_profile_migration(self):
        self.write_settings({"CustomRating.Movies.Item03": "Trakt"})
        self.service.main()
        self.assertEqual("Plex", self.values["CustomRating.Movies.Item03"])


class RatingRenderer:
    """Evaluate the rating include's public label and visibility contracts."""

    def __init__(self, settings, labels):
        self.root = ET.parse(SKIN_ROOT / "1080i/Includes_Info.xml")
        self.settings = settings
        self.labels = labels

    @staticmethod
    def split(expression, separator):
        depth = 0
        start = 0
        parts = []
        for index, character in enumerate(expression):
            if character in "([":
                depth += 1
            elif character in ")]":
                depth -= 1
            elif character == separator and not depth:
                parts.append(expression[start:index].strip())
                start = index + 1
        parts.append(expression[start:].strip())
        return parts

    def condition(self, expression):
        expression = expression.strip()
        if not expression:
            return True
        parts = self.split(expression, "|")
        if len(parts) > 1:
            return any(self.condition(part) for part in parts)
        parts = self.split(expression, "+")
        if len(parts) > 1:
            return all(self.condition(part) for part in parts)
        if expression.startswith("!"):
            return not self.condition(expression[1:])
        if expression.startswith("[") and expression.endswith("]"):
            return self.condition(expression[1:-1])
        if expression.lower() in ("true", "false"):
            return expression.lower() == "true"
        if expression.startswith("$EXP["):
            return True
        name, arguments = expression.split("(", 1)
        args = self.split(arguments[:-1], ",")
        if name == "Skin.String":
            return self.settings.get(args[0], "").lower() == args[1].lower()
        if name == "String.IsEmpty":
            return not self.labels.get(args[0], "")
        if name == "String.IsEqual":
            return self.labels.get(args[0], args[0]).lower() == args[1].lower()
        raise AssertionError("Unsupported rating condition: " + expression)

    def render(self, name="Info_Meta_Ratings", params=None):
        include = self.root.find(f"include[@name='{name}']")
        self_params = {p.get("name"): p.text or "" for p in include.findall("param")}
        self_params.update(params or {})
        def substitute(text):
            for key, value in self_params.items():
                text = text.replace("$PARAM[" + key + "]", value)
            return text
        output = []
        for child in include.findall("definition/include"):
            if not self.condition(substitute(child.get("condition", "true"))):
                continue
            values = {p.get("name"): substitute(p.text or "") for p in child.findall("param")}
            if child.get("content") != "Info_Meta_Object":
                output.extend(self.render(child.get("content"), values))
                continue
            if not self.condition(values.get("visible", "true")):
                continue
            def info(match):
                fields = match[1].split(",")
                value = self.labels.get(fields[0], "")
                return ((fields[1] if len(fields) > 1 else "") + value + (fields[2] if len(fields) > 2 else "")) if value else ""
            output.append(re.sub(r"\$INFO\[([^\[\]]+)\]", info, values.get("label", "")))
        return output


class PlexRatingContracts(unittest.TestCase):
    def render(self, labels, other=None, item="Item01"):
        settings = {"CustomRating.Movies." + item: "Plex"}
        settings.update(other or {})
        return RatingRenderer(settings, labels).render(params={"content": "Movies", "item": item, "listitem": "ListItem", "container": "", "visible": "true", "colordiffuse": "main_fg"})

    def test_each_public_provider_keeps_source_and_ten_point_scale(self):
        for key, source in (("imdb", "IMDb"), ("themoviedb", "TMDb"), ("tvdb", "TVDB"), ("tomatometerallaudience", "Rotten Tomatoes Audience"), ("tomatometerallcritics", "Rotten Tomatoes Critics")):
            with self.subTest(key=key):
                self.assertEqual([source + ": 8.4/10"], self.render({f"ListItem.Rating({key})": "8.4"}))

    def test_explicit_rating_takes_precedence_over_named_rating(self):
        self.assertEqual(["IMDb: 7.1/10"], self.render({"ListItem.Property(PlexRating)": "7.1", "ListItem.Property(PlexRatingSource)": "imdb", "ListItem.Rating(imdb)": "8.4"}))

    def test_duplicate_selected_provider_and_duplicate_plex_slot_stay_hidden(self):
        labels = {"ListItem.Rating(imdb)": "8.4"}
        self.assertEqual([], self.render(labels, {"CustomRating.Movies.Item02": "IMDb"}))
        self.assertEqual([], self.render(labels, {"CustomRating.Movies.Item01": "Plex"}, "Item03"))
        self.assertEqual([], self.render({"ListItem.Property(PlexRating)": "7.1", "ListItem.Property(PlexRatingSource)": "themoviedb"}, {"CustomRating.Movies.Item02": "TMDb"}))

    def test_missing_public_ratings_never_use_personal_rating_or_version_count(self):
        self.assertEqual([], self.render({"ListItem.UserRating": "9", "ListItem.Property(Versions)": "4", "ListItem.Rating": "0.0", "ListItem.Rating(imdb)": "0.0"}))
        self.assertEqual([], self.render({}))

    def test_disabled_other_slot_does_not_hide_unknown_provider(self):
        self.assertEqual(["Plex: 6.2/10"], self.render({"ListItem.Rating": "6.2"}, {"CustomRating.Movies.Item02": "None"}))

    def test_unknown_public_default_uses_plex_label(self):
        self.assertEqual(["Plex: 6.2/10"], self.render({"ListItem.Rating": "6.2"}))


class PlexSkinContracts(unittest.TestCase):
    def test_four_search_rules_browse_lists_without_query_affixes(self):
        rules = ET.parse(SKIN_ROOT / "shortcuts/generator/data/setup/search_path.xml").getroot()
        values = {}
        for group in rules.findall("rules"):
            for rule in group.findall("rule"):
                if rule.findtext("condition") == "{item_path}==" + LISTS:
                    values[group.get("name")] = rule.findtext("value") or ""
        self.assertEqual({"widget_path": "", "widget_path_end": "", "widget_target": "videos", "widget_search_variable": "Path_PlexLists"}, values)

    def test_startup_migrates_all_slots_and_preserves_blank_defaults(self):
        startup = json.loads((SKIN_ROOT / "shortcuts/skinvariables-startup.json").read_text())
        records = []
        def collect(value):
            if isinstance(value, dict):
                if "rules" in value:
                    records.append(value)
                for child in value.values():
                    collect(child)
            elif isinstance(value, list):
                for child in value:
                    collect(child)
        collect(startup)
        for content in ("Movies", "TVShows"):
            for index in (1, 2, 3):
                key = f"CustomRating.{content}.Item{index:02}"
                self.assertTrue(any(f"Skin.String({key},Trakt)" in row["rules"] and row["value"] == f"Skin.SetString({key},Plex)" for row in records), key)
            for index, source in ((1, "Plex"), (2, "Metacritic")):
                key = f"CustomRating.{content}.Item{index:02}"
                self.assertTrue(any(f"String.IsEmpty(Skin.String({key}))" in row["rules"] and row["value"] == f"Skin.SetString({key},{source})" for row in records), key)
            self.assertFalse(any(f"String.IsEmpty(Skin.String(CustomRating.{content}.Item03))" in row.get("rules", []) for row in records))

    def test_ratings_monitor_covers_third_slots(self):
        monitor = ET.parse(SKIN_ROOT / "1080i/Includes_Actions.xml").find("variable[@name='Action_RatingsMonitor']")
        for content in ("Movies", "TVShows"):
            for index in (1, 2, 3):
                for source in ("Plex", "IMDb"):
                    self.assertTrue(any(f"CustomRating.{content}.Item{index:02},{source}" in row.get("condition", "") for row in monitor), (content, index, source))

    def test_all_five_overlay_callers_allow_live_badge_setting_changes(self):
        root = ET.parse(SKIN_ROOT / "1080i/Includes_Layouts.xml")
        callers = root.findall(".//include[@content='Object_PlexOverlays']")
        self.assertEqual(len(callers), 5)
        for caller in callers:
            condition = caller.get("condition", "")
            with self.subTest(condition=condition):
                self.assertEqual(condition, "$PARAM[indicator]")

    def test_badge_controls_preserve_item_context_and_separate_icon_slots(self):
        root = ET.parse(SKIN_ROOT / "1080i/Includes_Objects.xml")
        overlay = root.find("include[@name='Object_PlexOverlays']/definition/control")
        self.assertEqual("group", overlay.get("type"), "A list-item layout cannot pass item context through a grouplist")
        self.assertIsNone(overlay.find("orientation"))
        self.assertIsNone(overlay.find("itemgap"))
        slots = {}
        for badge in overlay.findall("include[@content='Object_PlexMembershipBadge']"):
            params = {node.get("name"): node.text for node in badge.findall("param")}
            slots[(params["kind"], params["type"])] = params.get("top", "0")
        self.assertEqual({("Watchlist", "movie"): "0", ("Watchlist", "tvshow"): "0",
                          ("Favourites", "movie"): "48", ("Favourites", "tvshow"): "48",
                          ("Favourites", "season"): "0", ("Favourites", "episode"): "0"}, slots)
        badge = root.find("include[@name='Object_PlexMembershipBadge']")
        self.assertEqual("$PARAM[top]", badge.findtext("definition/control/top"))

    def test_nextaired_uses_local_calendar_independent_of_stored_mode(self):
        root = ET.parse(SKIN_ROOT / "1080i/Includes_NextAired.xml")
        info = root.find("include[@name='NextAired_Content']//param[@name='info']")
        self.assertEqual("library_nextaired", info.text)


if __name__ == "__main__":
    unittest.main()

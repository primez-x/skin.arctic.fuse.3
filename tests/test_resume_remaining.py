"""Resume button remaining time: resume_remaining.py keeps Home properties with the time left on the
Info page's item and on its focused episode. Each value is keyed by DBType and DBID, so the skin shows
a value only for its own item. These cases cover the ways the label could be wrong or stale."""

import importlib.util
import json
import sys
import types
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


SKIN_ROOT = Path(__file__).resolve().parents[1]


class FakeKodi:
    def __init__(self):
        self.labels = {}
        self.visible = True
        self.resume = {}
        self.calls = []
        self.properties = {}
        self.rpc_error = False

    def modules(self):
        xbmc = types.ModuleType("xbmc")
        xbmc.getInfoLabel = lambda label: self.labels.get(label, "")
        xbmc.getCondVisibility = lambda condition: self.visible
        xbmc.executeJSONRPC = self.execute
        xbmcgui = types.ModuleType("xbmcgui")
        fake = self

        class Window:
            def __init__(self, window_id):
                assert window_id == 10000

            def setProperty(self, name, value):
                fake.properties[name] = value

            def clearProperty(self, name):
                fake.properties.pop(name, None)

        xbmcgui.Window = Window
        return {"xbmc": xbmc, "xbmcgui": xbmcgui}

    def execute(self, payload):
        request = json.loads(payload)
        self.calls.append(request)
        if self.rpc_error:
            return json.dumps({"error": {"code": -32602, "message": "Invalid params."}})
        method = request["method"]
        key, result = {
            "VideoLibrary.GetMovieDetails": ("movieid", "moviedetails"),
            "VideoLibrary.GetEpisodeDetails": ("episodeid", "episodedetails"),
        }[method]
        position, total = self.resume.get(request["params"][key], (0, 0))
        return json.dumps({"result": {result: {"resume": {"position": position, "total": total}}}})


def _load(fake):
    saved = {name: sys.modules.get(name) for name in ("xbmc", "xbmcgui")}
    sys.modules.update(fake.modules())
    try:
        spec = importlib.util.spec_from_file_location("resume_remaining", SKIN_ROOT / "resume_remaining.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        for name, value in saved.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value
    return module


class FormatTests(unittest.TestCase):
    def setUp(self):
        self.module = _load(FakeKodi())

    def test_not_started_or_finished_items_have_no_remaining_time(self):
        for position, total in ((0, 3000), (3000, 3000), (3100, 3000), (120, 0)):
            self.assertEqual("", self.module.format_remaining(position, total), (position, total))

    def test_last_seconds_round_up_so_the_label_never_reads_zero(self):
        self.assertEqual("1m", self.module.format_remaining(2990, 3000))
        self.assertEqual("26m", self.module.format_remaining(3060 - 26 * 60 + 1, 3060))

    def test_hours_use_the_compact_duration_style(self):
        self.assertEqual("1h 26m", self.module.format_remaining(0.5, 86 * 60))
        self.assertEqual("2h", self.module.format_remaining(60, 2 * 3600 + 60))


class WatcherTests(unittest.TestCase):
    def setUp(self):
        self.kodi = FakeKodi()
        self.module = _load(self.kodi)
        self.watcher = self.module.Watcher("{0} left")
        self.kodi.labels = {
            "ListItem.DBType": "movie",
            "ListItem.DBID": "420",
            "Container(5019).ListItem.DBType": "",
            "Container(5019).ListItem.DBID": "",
        }
        self.kodi.resume = {420: (267.0, 7051.0), 7: (60.0, 3060.0), 8: (0, 3000.0)}

    def test_page_item_gets_its_time_and_key(self):
        self.watcher.poll()
        props = self.kodi.properties
        self.assertEqual("1h 54m left", props["DialogInfo.Remaining"])
        self.assertEqual("movie", props["DialogInfo.Remaining.DBType"])
        self.assertEqual("420", props["DialogInfo.Remaining.DBID"])

    def test_focused_episode_has_its_own_value(self):
        self.kodi.labels.update({"ListItem.DBType": "tvshow", "ListItem.DBID": "98",
                                 "Container(5019).ListItem.DBType": "episode", "Container(5019).ListItem.DBID": "7"})
        self.watcher.poll()
        props = self.kodi.properties
        self.assertEqual("50m left", props["DialogInfo.EpisodeRemaining"])
        self.assertEqual("7", props["DialogInfo.EpisodeRemaining.DBID"])
        # A TV show has no resume point and is never queried
        self.assertEqual("", props["DialogInfo.Remaining"])
        self.assertEqual(["VideoLibrary.GetEpisodeDetails"], [c["method"] for c in self.kodi.calls])

    def test_moving_to_an_unstarted_episode_replaces_the_old_value(self):
        self.kodi.labels.update({"Container(5019).ListItem.DBType": "episode", "Container(5019).ListItem.DBID": "7"})
        self.watcher.poll()
        self.kodi.labels["Container(5019).ListItem.DBID"] = "8"
        self.watcher.poll()
        self.assertEqual("", self.kodi.properties["DialogInfo.EpisodeRemaining"])
        self.assertEqual("8", self.kodi.properties["DialogInfo.EpisodeRemaining.DBID"])

    def test_unchanged_item_is_not_queried_again(self):
        for _ in range(5):
            self.watcher.poll()
        self.assertEqual(1, len(self.kodi.calls))

    def test_closing_the_page_clears_values_so_a_reopen_recomputes(self):
        self.watcher.poll()
        self.kodi.visible = False
        self.watcher.poll()
        self.assertNotIn("DialogInfo.Remaining", self.kodi.properties)
        self.assertNotIn("DialogInfo.Remaining.DBID", self.kodi.properties)
        # Playback moved the resume point while the page was closed
        self.kodi.resume[420] = (6000.0, 7051.0)
        self.kodi.visible = True
        self.watcher.poll()
        self.assertEqual("18m left", self.kodi.properties["DialogInfo.Remaining"])

    def test_rpc_errors_leave_an_empty_value(self):
        self.kodi.rpc_error = True
        self.watcher.poll()
        self.assertEqual("", self.kodi.properties["DialogInfo.Remaining"])
        self.assertEqual("420", self.kodi.properties["DialogInfo.Remaining.DBID"])

    def test_items_without_a_library_id_are_not_queried(self):
        self.kodi.labels.update({"ListItem.DBID": ""})
        self.watcher.poll()
        self.assertEqual([], self.kodi.calls)


class SkinWiringTests(unittest.TestCase):
    def test_resume_label_shows_the_value_only_for_its_own_item(self):
        labels = ET.parse(SKIN_ROOT / "1080i" / "Includes_Labels.xml").getroot()
        (variable,) = [v for v in labels.iter("variable") if v.get("name") == "Label_DialogInfo_PlayButton"]
        keyed = [v for v in variable.findall("value") if "Remaining)" in (v.text or "")]
        self.assertEqual(3, len(keyed))
        for value in keyed:
            condition = value.get("condition")
            prop = "EpisodeRemaining" if "Container(5019)" in condition else "Remaining"
            listitem = "Container(5019).ListItem" if prop == "EpisodeRemaining" else "ListItem"
            self.assertIn(f"String.IsEqual(Window(Home).Property(DialogInfo.{prop}.DBID),{listitem}.DBID)", condition)
            self.assertIn(f"String.IsEqual(Window(Home).Property(DialogInfo.{prop}.DBType),{listitem}.DBType)", condition)
            self.assertIn(f"Window(Home).Property(DialogInfo.{prop})", value.text)

    def test_service_starts_the_watcher(self):
        source = (SKIN_ROOT / "service.py").read_text(encoding="utf-8")
        self.assertIn("resume_remaining.watch(xbmc.Monitor(), xbmc.getLocalizedString(31997))", source)


if __name__ == "__main__":
    unittest.main()

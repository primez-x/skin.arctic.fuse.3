"""Info page details: dialoginfo_details.py keeps Home properties with the time left and the stream
chip labels of the Info page's item and of its focused episode. Each set is keyed by DBType and DBID,
so the skin shows a value only for its own item. These cases cover the ways a label could be wrong
or stale."""

import importlib.util
import json
import sys
import types
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


SKIN_ROOT = Path(__file__).resolve().parents[1]
LANGUAGES = {"eng": "English", "spa": "Spanish", "fre": "French"}


def _streams(video=None, audio=None, subtitle=None):
    return {"video": video or [], "audio": audio or [], "subtitle": subtitle or []}


class FakeKodi:
    def __init__(self):
        self.labels = {}
        self.visible = True
        self.details = {}
        self.calls = []
        self.properties = {}
        self.rpc_error = False
        self.audio_language = "English"

    def modules(self):
        xbmc = types.ModuleType("xbmc")
        xbmc.ENGLISH_NAME = 2
        xbmc.getInfoLabel = lambda label: self.labels.get(label, "")
        xbmc.getCondVisibility = lambda condition: self.visible
        xbmc.executeJSONRPC = self.execute
        xbmc.convertLanguage = lambda code, fmt: LANGUAGES.get(code, "")
        xbmc.getLocalizedString = lambda code: {287: "Subtitles"}[code]
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
        if request["method"] == "Settings.GetSettingValue":
            assert request["params"] == {"setting": "locale.audiolanguage"}
            return json.dumps({"result": {"value": self.audio_language}})
        key, result = {
            "VideoLibrary.GetMovieDetails": ("movieid", "moviedetails"),
            "VideoLibrary.GetEpisodeDetails": ("episodeid", "episodedetails"),
        }[request["method"]]
        self.assertion_properties = request["params"]["properties"]
        return json.dumps({"result": {result: self.details.get(request["params"][key], {})}})


def _load(fake):
    saved = {name: sys.modules.get(name) for name in ("xbmc", "xbmcgui")}
    sys.modules.update(fake.modules())
    try:
        spec = importlib.util.spec_from_file_location("dialoginfo_details", SKIN_ROOT / "dialoginfo_details.py")
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

    def test_video_follows_kodis_resolution_bands_and_names_hdr(self):
        video = self.module.format_video
        self.assertEqual("4K • Dolby Vision", video([{"width": 3840, "height": 2160, "hdrtype": "dolbyvision"}]))
        self.assertEqual("4K • HDR10", video([{"width": 3840, "height": 1600, "hdrtype": "hdr10"}]))
        # Scope 1080p and anamorphic DVD stay in their bands
        self.assertEqual("1080p", video([{"width": 1920, "height": 800, "hdrtype": ""}]))
        self.assertEqual("720p", video([{"width": 1280, "height": 720}]))
        self.assertEqual("SD", video([{"width": 720, "height": 480}]))
        self.assertEqual("8K", video([{"width": 7680, "height": 4320}]))
        self.assertEqual("", video([]))
        self.assertEqual("", video([{"width": 0, "height": 0}]))

    def test_audio_reads_like_plex(self):
        audio = self.module.format_audio
        self.assertEqual("English (EAC3 5.1)", audio([{"language": "eng", "codec": "eac3", "channels": 6}]))
        self.assertEqual("Spanish (TrueHD 7.1)", audio([{"language": "spa", "codec": "truehd", "channels": 8}]))
        self.assertEqual("AAC Stereo", audio([{"language": "", "codec": "aac", "channels": 2}]))
        self.assertEqual("DTS-HD MA 6.1", audio([{"language": "und", "codec": "dtshd_ma", "channels": 7}]))
        self.assertEqual("XYZ Mono", audio([{"codec": "xyz", "channels": 1}]))
        self.assertEqual("", audio([]))

    def test_audio_names_the_stream_kodi_plays(self):
        audio = self.module.format_audio
        # Like the test box movie: another language first, English with more channels
        streams = [{"language": "spa", "codec": "ac3", "channels": 6}, {"language": "eng", "codec": "aac", "channels": 8}]
        self.assertEqual("English (AAC 7.1)", audio(streams, "English"))
        # Without a preferred language, or when no stream has the language, the most channels win
        self.assertEqual("English (AAC 7.1)", audio(streams, ""))
        self.assertEqual("English (AAC 7.1)", audio(streams, "French"))
        both = [{"language": "spa", "codec": "truehd", "channels": 8}, {"language": "eng", "codec": "ac3", "channels": 6}]
        self.assertEqual("English (AC3 5.1)", audio(both, "English"))
        self.assertEqual("Spanish (TrueHD 7.1)", audio(both, ""))

    def test_subtitles_show_what_is_available_never_a_guessed_selection(self):
        subtitles = self.module.format_subtitles
        self.assertEqual("", subtitles([]))
        self.assertEqual("English", subtitles([{"language": "eng"}]))
        self.assertEqual("English +2", subtitles([{"language": "eng"}, {"language": "spa"}, {"language": "fre"}]))
        self.assertEqual("Subtitles", subtitles([{"language": ""}]))


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
        movie_streams = _streams(
            video=[{"width": 3840, "height": 2160, "hdrtype": "dolbyvision"}],
            audio=[{"language": "eng", "codec": "truehd", "channels": 8}],
            subtitle=[{"language": "eng"}],
        )
        self.kodi.details = {
            420: {"resume": {"position": 267.0, "total": 7051.0}, "streamdetails": movie_streams},
            7: {"resume": {"position": 60.0, "total": 3060.0}, "streamdetails": _streams()},
            8: {"resume": {"position": 0, "total": 3000.0}, "streamdetails": _streams()},
        }

    def test_page_item_gets_its_values_and_key(self):
        self.watcher.poll()
        props = self.kodi.properties
        self.assertEqual("1h 54m left", props["DialogInfo.Item.Remaining"])
        self.assertEqual("4K • Dolby Vision", props["DialogInfo.Item.Video"])
        self.assertEqual("English (TrueHD 7.1)", props["DialogInfo.Item.Audio"])
        self.assertEqual("English", props["DialogInfo.Item.Subtitles"])
        self.assertEqual("movie", props["DialogInfo.Item.DBType"])
        self.assertEqual("420", props["DialogInfo.Item.DBID"])
        self.assertEqual(["resume", "streamdetails"], self.kodi.assertion_properties)

    def test_focused_episode_has_its_own_values(self):
        self.kodi.labels.update({"ListItem.DBType": "tvshow", "ListItem.DBID": "98",
                                 "Container(5019).ListItem.DBType": "episode", "Container(5019).ListItem.DBID": "7"})
        self.watcher.poll()
        props = self.kodi.properties
        self.assertEqual("50m left", props["DialogInfo.Episode.Remaining"])
        self.assertEqual("7", props["DialogInfo.Episode.DBID"])
        # A TV show has no resume point or streams and is never queried
        self.assertEqual("", props["DialogInfo.Item.Remaining"])
        self.assertEqual(["VideoLibrary.GetEpisodeDetails", "Settings.GetSettingValue"],
                         [c["method"] for c in self.kodi.calls])

    def test_moving_to_another_episode_replaces_every_value(self):
        self.kodi.details[7]["streamdetails"] = _streams(audio=[{"language": "eng", "codec": "aac", "channels": 2}])
        self.kodi.labels.update({"Container(5019).ListItem.DBType": "episode", "Container(5019).ListItem.DBID": "7"})
        self.watcher.poll()
        self.kodi.labels["Container(5019).ListItem.DBID"] = "8"
        self.watcher.poll()
        self.assertEqual("", self.kodi.properties["DialogInfo.Episode.Remaining"])
        self.assertEqual("", self.kodi.properties["DialogInfo.Episode.Audio"])
        self.assertEqual("8", self.kodi.properties["DialogInfo.Episode.DBID"])

    def test_unchanged_item_is_not_queried_again(self):
        for _ in range(5):
            self.watcher.poll()
        self.assertEqual(["VideoLibrary.GetMovieDetails", "Settings.GetSettingValue"],
                         [c["method"] for c in self.kodi.calls])

    def test_closing_the_page_clears_values_so_a_reopen_recomputes(self):
        self.watcher.poll()
        self.kodi.visible = False
        self.watcher.poll()
        self.assertFalse([p for p in self.kodi.properties if p.startswith("DialogInfo.")])
        # Playback moved the resume point while the page was closed
        self.kodi.details[420]["resume"]["position"] = 6000.0
        self.kodi.visible = True
        self.watcher.poll()
        self.assertEqual("18m left", self.kodi.properties["DialogInfo.Item.Remaining"])

    def test_rpc_errors_leave_empty_values(self):
        self.kodi.rpc_error = True
        self.watcher.poll()
        for field in ("Remaining", "Video", "Audio", "Subtitles"):
            self.assertEqual("", self.kodi.properties[f"DialogInfo.Item.{field}"])
        self.assertEqual("420", self.kodi.properties["DialogInfo.Item.DBID"])

    def test_items_without_a_library_id_are_not_queried(self):
        self.kodi.labels.update({"ListItem.DBID": ""})
        self.watcher.poll()
        self.assertEqual([], self.kodi.calls)


def _keyed(condition, target, listitem):
    return (f"String.IsEqual(Window(Home).Property(DialogInfo.{target}.DBID),{listitem}.DBID)" in condition
            and f"String.IsEqual(Window(Home).Property(DialogInfo.{target}.DBType),{listitem}.DBType)" in condition)


class SkinWiringTests(unittest.TestCase):
    def test_resume_label_shows_the_value_only_for_its_own_item(self):
        labels = ET.parse(SKIN_ROOT / "1080i" / "Includes_Labels.xml").getroot()
        (variable,) = [v for v in labels.iter("variable") if v.get("name") == "Label_DialogInfo_PlayButton"]
        keyed = [v for v in variable.findall("value") if "Remaining)" in (v.text or "")]
        self.assertEqual(3, len(keyed))
        for value in keyed:
            condition = value.get("condition")
            target = "Episode" if "Container(5019)" in condition else "Item"
            listitem = "Container(5019).ListItem" if target == "Episode" else "ListItem"
            self.assertTrue(_keyed(condition, target, listitem), condition)
            self.assertIn(f"Window(Home).Property(DialogInfo.{target}.Remaining)", value.text)

    def test_stream_chips_show_values_only_for_their_own_item(self):
        expressions = ET.parse(SKIN_ROOT / "1080i" / "Includes_Expressions.xml").getroot()
        found = {e.get("name"): e.text for e in expressions.iter("expression")}
        self.assertTrue(_keyed(found["Exp_DialogInfo_Details_Item"], "Item", "ListItem"))
        self.assertTrue(_keyed(found["Exp_DialogInfo_Details_Episode"], "Episode", "Container(5019).ListItem"))

    def test_service_starts_the_watcher(self):
        source = (SKIN_ROOT / "service.py").read_text(encoding="utf-8")
        self.assertIn("dialoginfo_details.watch(xbmc.Monitor(), xbmc.getLocalizedString(31997))", source)


if __name__ == "__main__":
    unittest.main()

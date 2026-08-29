import json
import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


SKIN_ROOT = Path(__file__).resolve().parents[1]
VALID_TRAILER_PARAMS = {"trailer", "trailer_fallback"}
REMOVED_MODAL_FILES = {
    "1080i/Custom_1122_Dialog_SelectTrailer.xml",
    "1080i/Custom_1123_Dialog_Trailer.xml",
    "1080i/Dialog_DialogTrailer.xml",
}


def _action_include():
    root = ET.parse(SKIN_ROOT / "1080i" / "Includes_Actions.xml").getroot()
    return root.find("./include[@name='Action_PlayTrailer_OnClick']")


def _render_builtin(template, **values):
    return template.format(**values)


def _split_builtin_arguments(command):
    """Parse the arguments of a Kodi builtin while preserving quoted commas."""
    match = re.fullmatch(r"(?P<name>\w+)\((?P<arguments>.*)\)", command)
    if match is None:
        raise ValueError(f"not a builtin call: {command}")

    arguments = []
    current = []
    quoted = False
    for character in match.group("arguments"):
        if character == '"':
            quoted = not quoted
        if character == "," and not quoted:
            arguments.append("".join(current))
            current = []
        else:
            current.append(character)
    arguments.append("".join(current))
    return match.group("name"), arguments


class TrailerFullscreenPlaybackTests(unittest.TestCase):
    def test_action_dispatches_primary_and_fallback_directly_without_windowed_mode(self):
        action = _action_include()
        onclicks = action.findall("onclick")

        self.assertEqual(len(onclicks), 2)
        self.assertEqual(
            [onclick.get("condition") for onclick in onclicks],
            [
                "String.IsEmpty($PARAM[trailer]) + !String.IsEmpty($PARAM[trailer_fallback])",
                "!String.IsEmpty($PARAM[trailer])",
            ],
        )
        self.assertEqual(
            [onclick.text for onclick in onclicks],
            [
                "PlayMedia($ESCINFO[$PARAM[trailer_fallback]],False)",
                "PlayMedia($ESCINFO[$PARAM[trailer]],False)",
            ],
        )
        self.assertTrue(all("$ESCINFO[" in (onclick.text or "") for onclick in onclicks))
        self.assertTrue(all(",1)" not in (onclick.text or "") for onclick in onclicks))

    def test_action_callers_pass_only_supported_trailer_parameters(self):
        callers = []
        for source_path in (SKIN_ROOT / "1080i").glob("*.xml"):
            root = ET.parse(source_path).getroot()
            for include in root.findall(".//include[@content='Action_PlayTrailer_OnClick']"):
                params = {
                    param.get("name")
                    for param in include.findall("param")
                    if param.get("name")
                }
                callers.append((source_path.name, params))

        self.assertEqual(len(callers), 3)
        self.assertTrue(callers)
        self.assertTrue(all(params <= VALID_TRAILER_PARAMS for _, params in callers))

    def test_skinvariable_trailer_action_renders_comma_url_as_one_quoted_argument(self):
        shortcut = json.loads(
            (SKIN_ROOT / "shortcuts" / "builtins" / "skinvariables-playtrailer.json")
            .read_text(encoding="utf-8")
        )

        self.assertEqual(
            shortcut["infolabels"],
            {
                "listitem_trailer": "Container.ListItem.Trailer",
                "tmdbhelper_trailer": "Window(Home).Property(TMDbHelper.ListItem.Trailer)",
            },
        )
        self.assertEqual(
            shortcut["values"],
            {
                "trailer": [
                    {
                        "rules": ["!String.IsEmpty(Container.ListItem.Trailer)"],
                        "value": "{listitem_trailer}",
                    },
                    "{tmdbhelper_trailer}",
                ]
            },
        )
        self.assertEqual(shortcut["actions"], ['PlayMedia("{trailer}")'])

        trailer = "https://example.test/trailer?part=one,two&quote=%22inside%22"
        rendered = _render_builtin(shortcut["actions"][0], trailer=trailer)
        name, arguments = _split_builtin_arguments(rendered)

        self.assertEqual(name, "PlayMedia")
        self.assertEqual(arguments, [f'"{trailer}"'])
        self.assertIn("%22inside%22", arguments[0])

    def test_removed_modal_graph_and_legacy_state_are_gone(self):
        for relative_path in REMOVED_MODAL_FILES:
            self.assertFalse(
                (SKIN_ROOT / relative_path).exists(),
                f"legacy trailer modal remains: {relative_path}",
            )

        includes = ET.parse(SKIN_ROOT / "1080i" / "Includes.xml").getroot()
        include_files = [include.get("file") for include in includes.findall("include")]
        self.assertNotIn("Dialog_DialogTrailer.xml", include_files)

        custom_dialog = ET.parse(SKIN_ROOT / "1080i" / "Dialog_DialogCustom.xml").getroot()
        custom_dialog_text = ET.tostring(custom_dialog, encoding="unicode")
        self.assertNotIn("DialogCustom_Trailers", custom_dialog_text)
        self.assertNotIn("PlayTrailerItems", custom_dialog_text)

        context_menu = ET.parse(
            SKIN_ROOT / "1080i" / "Dialog_DialogContextMenu.xml"
        ).getroot()
        context_menu_text = ET.tostring(context_menu, encoding="unicode")
        self.assertNotIn("SetProperty(PlayTrailerItems", context_menu_text)
        self.assertIn("skinvariables-playtrailer.json", context_menu_text)

        for relative_path in (
            "1080i/Includes_Background.xml",
            "1080i/Includes_Expressions.xml",
            "1080i/Includes_Defaults.xml",
        ):
            source = (SKIN_ROOT / relative_path).read_text(encoding="utf-8")
            self.assertNotIn("1123", source, relative_path)

        for relative_path, variable_name in (
            ("1080i/Includes_Images.xml", "Image_Trailer_PlayPause"),
            ("1080i/Includes_Labels.xml", "Label_Trailer_PlayPause"),
        ):
            root = ET.parse(SKIN_ROOT / relative_path).getroot()
            self.assertIsNone(
                root.find(f".//variable[@name='{variable_name}']"),
                relative_path,
            )

        for source_path in (SKIN_ROOT / "1080i").glob("*.xml"):
            source = source_path.read_text(encoding="utf-8")
            self.assertNotIn("ActivateWindow(1122)", source, source_path.name)
            self.assertNotIn("ActivateWindow(1123)", source, source_path.name)
            self.assertNotIn("Dialog.Close(1123", source, source_path.name)
            self.assertNotIn("TrailerFullscreen", source, source_path.name)
            self.assertNotIn("PlayTrailerItems", source, source_path.name)
            self.assertNotIn("Window(Home).Property(PlayTrailer)", source, source_path.name)

    def test_video_info_trailer_rows_and_path_remain_available(self):
        paths = ET.parse(SKIN_ROOT / "1080i" / "Includes_Paths.xml").getroot()
        self.assertIsNotNone(
            paths.find("./variable[@name='Path_VideoInfo_Trailers']")
        )

        dialog_info = (SKIN_ROOT / "1080i" / "Includes_DialogInfo.xml").read_text(
            encoding="utf-8"
        )
        self.assertIn("Container(5014).ListItem.FileNameAndPath", dialog_info)
        self.assertIn("Container(5002).ListItem.FileNameAndPath", dialog_info)

    def test_localization_removes_replay_and_keeps_stop_without_deleted_source(self):
        catalogs = sorted((SKIN_ROOT / "language").glob("*/strings.po"))
        self.assertTrue(catalogs)
        for catalog in catalogs:
            source = catalog.read_text(encoding="utf-8")
            entries = re.split(r"\n\s*\n", source)
            self.assertFalse(
                any('msgctxt "#31483"' in entry for entry in entries),
                catalog.name,
            )
            stop_entries = [
                entry for entry in entries if 'msgctxt "#31485"' in entry
            ]
            self.assertEqual(len(stop_entries), 1, catalog.name)
            self.assertNotIn("Custom_1123_Dialog_Trailer.xml", stop_entries[0])

    def test_addon_version_and_news_identify_fullscreen_trailer_playback(self):
        addon = ET.parse(SKIN_ROOT / "addon.xml").getroot()
        self.assertEqual(addon.get("version"), "3.2.69")

        news = addon.find("./extension[@point='xbmc.addon.metadata']/news")
        self.assertIsNotNone(news)
        self.assertTrue((news.text or "").lstrip().startswith("v3.2.69"))
        self.assertIn("fullscreen trailer playback", (news.text or "").lower())


if __name__ == "__main__":
    unittest.main()

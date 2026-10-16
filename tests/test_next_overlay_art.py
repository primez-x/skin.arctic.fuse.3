import json
import runpy
import sys
import types
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch


SKIN_ROOT = Path(__file__).resolve().parents[1]


class SongInformationSettingTests(unittest.TestCase):
    def run_toggle(self, responses):
        calls, errors, notifications = [], [], []

        def execute(request):
            calls.append(json.loads(request))
            return json.dumps(responses[len(calls) - 1])

        xbmc = types.SimpleNamespace(executeJSONRPC=execute, LOGERROR=4,
                                     log=lambda *args: errors.append(args),
                                     getLocalizedString=lambda number: str(number))
        xbmcgui = types.SimpleNamespace(NOTIFICATION_ERROR="error",
                                        Dialog=lambda: types.SimpleNamespace(notification=lambda *args, **kwargs: notifications.append(args)))
        xbmcaddon = types.SimpleNamespace(Addon=lambda addon_id: types.SimpleNamespace(getLocalizedString=lambda number: str(number)))
        with patch.dict(sys.modules, xbmc=xbmc, xbmcgui=xbmcgui, xbmcaddon=xbmcaddon):
            runpy.run_path(str(SKIN_ROOT / "toggle_music_info.py"), run_name="__main__")
        return calls, errors, notifications

    def test_both_values_toggle_with_a_json_boolean(self):
        for previous in (False, True):
            calls, errors, notifications = self.run_toggle([{"result": {"value": previous}}, {"result": True}])
            self.assertEqual(["Settings.GetSettingValue", "Settings.SetSettingValue"], [call["method"] for call in calls])
            self.assertTrue(all(call["params"]["setting"] == "mymusic.songthumbinvis" for call in calls))
            self.assertIs(calls[1]["params"]["value"], not previous)
            self.assertEqual([], errors)
            self.assertEqual([], notifications)

    def test_failed_or_non_boolean_read_never_writes(self):
        for response in ({"error": {"code": -32602}}, {"result": {"value": "false"}}, {"result": {"value": 0}}):
            calls, errors, notifications = self.run_toggle([response])
            self.assertEqual(1, len(calls))
            self.assertEqual(1, len(errors))
            self.assertEqual(1, len(notifications))

    def test_rejected_write_reports_failure(self):
        for response in ({"error": {"code": -32602}}, {"result": False}):
            calls, errors, notifications = self.run_toggle([{"result": {"value": False}}, response])
            self.assertEqual(2, len(calls))
            self.assertEqual(1, len(errors))
            self.assertEqual(1, len(notifications))


class NextOverlayArtTests(unittest.TestCase):
    def test_music_next_overlay_shows_square_rounded_album_art(self):
        root = ET.parse(SKIN_ROOT / "1080i" / "Custom_1154_OSD_NextOverlay_Music.xml").getroot()
        overlay = root.find(".//include[@content='Object_NextItem']")
        self.assertEqual("square", overlay.findtext("param[@name='shape']"))
        self.assertEqual("$VAR[Image_OSD_MusicNext_Art]", overlay.findtext("param[@name='art']"))
        osd = ET.parse(SKIN_ROOT / "1080i" / "Includes_OSD.xml").getroot()
        image = osd.find("./include[@name='Object_NextItem_Art_square']/control")
        self.assertEqual("image", image.get("type"))
        self.assertEqual("diffuse/square_w217_h217.png", image.find("texture").get("diffuse"))
        self.assertEqual("scale", image.findtext("aspectratio"))
        # A square tile as tall as the video overlay's landscape one
        self.assertEqual("view_landscape_item_h", osd.findtext("./include[@name='Object_NextItem_Width_square']/width"))
        tile = osd.find("./include[@name='Object_NextItem']/definition/control/control")
        self.assertEqual("view_landscape_item_h", tile.findtext("height"))

    def test_music_next_preview_covers_any_music_source(self):
        root = ET.parse(SKIN_ROOT / "1080i" / "Includes_OSD.xml").getroot()
        available = root.find("./expression[@name='Exp_OSD_MusicNext_Available']").text
        self.assertIn("Spotify.NextTrackAvailable", available)
        self.assertIn("!String.IsEmpty(MusicPlayer.offset(1).Title)", available)
        for name, fallback in (
            ("Image_OSD_MusicNext_Art", "MusicPlayer.offset(1).Cover"),
            ("Label_OSD_MusicNext_Title", "MusicPlayer.offset(1).Title"),
            ("Label_OSD_MusicNext_Artist", "MusicPlayer.offset(1).Artist"),
        ):
            values = root.findall(f"./variable[@name='{name}']/value")
            self.assertTrue(all("Spotify" in (v.get("condition") or "") for v in values[:-1]), name)
            self.assertIsNone(values[-1].get("condition"), name)
            self.assertIn(fallback, values[-1].text)
        overlay = (SKIN_ROOT / "1080i" / "Custom_1154_OSD_NextOverlay_Music.xml").read_text(encoding="utf-8")
        self.assertIn("<visible>$EXP[Exp_OSD_MusicNext_Available]</visible>", overlay)
        osd = (SKIN_ROOT / "1080i" / "MusicOSD.xml").read_text(encoding="utf-8")
        self.assertIn('condition="$EXP[Exp_OSD_MusicNext_Available]">ActivateWindow(1154)', osd)

    def test_next_item_card_has_a_dark_corner_gradient_behind_it(self):
        osd = ET.parse(SKIN_ROOT / "1080i" / "Includes_OSD.xml").getroot()
        card = osd.find("./include[@name='Object_NextItem']/definition/control")
        children = [child.tag for child in card]
        backdrop_ref = next(
            (node for node in card.findall("./include") if node.text == "Object_NextItem_Backdrop_$PARAM[corner]"),
            None,
        )
        self.assertIsNotNone(backdrop_ref)
        # the gradient renders behind the art tile and the labels
        control_indexes = [i for i, tag in enumerate(children) if tag == "control"]
        self.assertLess(list(card).index(backdrop_ref), control_indexes[0])
        for corner, anchor, flipx in (("right", "right", None), ("left", "left", "true")):
            include = osd.find(f"./include[@name='Object_NextItem_Backdrop_{corner}']")
            image = include.find("./control")
            self.assertEqual("image", image.get("type"))
            self.assertEqual("-80", image.findtext(anchor))
            self.assertEqual("-80", image.findtext("top"))
            texture = image.find("texture")
            self.assertEqual("common/gradient-corner.png", texture.text)
            self.assertEqual(flipx, texture.get("flipx"))
        self.assertTrue((SKIN_ROOT / "media" / "common" / "gradient-corner.png").exists())

    def test_video_next_overlay_stays_landscape(self):
        text = (SKIN_ROOT / "1080i" / "Custom_1143_OSD_NextOverlay.xml").read_text(encoding="utf-8")
        self.assertNotIn("square_w217_h217", text)
        root = ET.parse(SKIN_ROOT / "1080i" / "Custom_1143_OSD_NextOverlay.xml").getroot()
        overlay = root.find(".//include[@content='Object_NextItem']")
        self.assertEqual("landscape", overlay.findtext("param[@name='shape']"))


if __name__ == "__main__":
    unittest.main()

import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


SKIN_ROOT = Path(__file__).resolve().parents[1]


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

    def test_video_next_overlay_stays_landscape(self):
        text = (SKIN_ROOT / "1080i" / "Custom_1143_OSD_NextOverlay.xml").read_text(encoding="utf-8")
        self.assertNotIn("square_w217_h217", text)
        root = ET.parse(SKIN_ROOT / "1080i" / "Custom_1143_OSD_NextOverlay.xml").getroot()
        overlay = root.find(".//include[@content='Object_NextItem']")
        self.assertEqual("landscape", overlay.findtext("param[@name='shape']"))


if __name__ == "__main__":
    unittest.main()

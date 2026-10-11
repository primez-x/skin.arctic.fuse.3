import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


SKIN_ROOT = Path(__file__).resolve().parents[1]


class NextOverlayArtTests(unittest.TestCase):
    def test_music_next_overlay_shows_square_rounded_album_art(self):
        root = ET.parse(SKIN_ROOT / "1080i" / "Custom_1154_OSD_NextOverlay_Music.xml").getroot()
        images = [
            image for image in root.iter("control")
            if image.get("type") == "image" and "Image_OSD_MusicNext_Art" in (image.findtext("texture") or "")
        ]
        self.assertEqual(1, len(images))
        for image in images:
            self.assertEqual("diffuse/square_w217_h217.png", image.find("texture").get("diffuse"))
            self.assertEqual("scale", image.findtext("aspectratio"))
        tile = next(
            group for group in root.iter("control")
            if group.get("type") == "group" and group.findtext("width") == "view_landscape_item_h"
        )
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


if __name__ == "__main__":
    unittest.main()

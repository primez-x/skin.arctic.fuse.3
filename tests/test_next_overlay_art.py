import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


SKIN_ROOT = Path(__file__).resolve().parents[1]


class NextOverlayArtTests(unittest.TestCase):
    def test_music_next_overlay_shows_square_rounded_album_art(self):
        root = ET.parse(SKIN_ROOT / "1080i" / "Custom_1154_OSD_NextOverlay_Music.xml").getroot()
        images = [
            image for image in root.iter("control")
            if image.get("type") == "image" and "Spotify.NextTrack" in (image.findtext("texture") or "")
        ]
        self.assertEqual(2, len(images))
        for image in images:
            self.assertEqual("diffuse/square_w217_h217.png", image.find("texture").get("diffuse"))
            self.assertEqual("scale", image.findtext("aspectratio"))
        tile = next(
            group for group in root.iter("control")
            if group.get("type") == "group" and group.findtext("width") == "view_landscape_item_h"
        )
        self.assertEqual("view_landscape_item_h", tile.findtext("height"))

    def test_video_next_overlay_stays_landscape(self):
        text = (SKIN_ROOT / "1080i" / "Custom_1143_OSD_NextOverlay.xml").read_text(encoding="utf-8")
        self.assertNotIn("square_w217_h217", text)


if __name__ == "__main__":
    unittest.main()

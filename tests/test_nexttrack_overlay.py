import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


SKIN_ROOT = Path(__file__).resolve().parents[1]
OVERLAY = SKIN_ROOT / "1080i" / "Custom_1155_Overlay_NextTrack.xml"


class NextTrackOverlayTests(unittest.TestCase):
    def setUp(self):
        self.window = ET.parse(OVERLAY).getroot()

    def test_overlay_is_a_modeless_dialog_driven_by_the_service_property(self):
        self.assertEqual(self.window.get("type"), "dialog")
        self.assertEqual(self.window.get("id"), "1155")
        # A <visible> condition makes Kodi open the dialog modeless by itself.
        visible = self.window.findtext("visible")
        self.assertIn("!String.IsEmpty(Window(Home).Property(NextTrack.IsVisible))", visible)

    def test_overlay_skips_windows_that_already_render_next_track(self):
        visible = self.window.findtext("visible")
        self.assertIn("!Window.IsActive(MusicVisualisation.xml)", visible)
        self.assertIn("!Window.IsActive(fullscreenvideo)", visible)
        visualisation = (SKIN_ROOT / "1080i" / "MusicVisualisation.xml").read_text(encoding="utf-8")
        self.assertIn("<include>Furniture_NextTrack</include>", visualisation)

    def test_overlay_never_takes_focus_or_input(self):
        self.assertIsNone(self.window.find("defaultcontrol"))
        self.assertEqual(
            [include.text for include in self.window.findall("./controls/include")],
            ["Furniture_NextTrack"],
        )
        furniture = ET.parse(SKIN_ROOT / "1080i" / "Includes_Furniture.xml").getroot()
        include = furniture.find("./include[@name='Furniture_NextTrack']")
        focusable = {"button", "radiobutton", "togglebutton", "edit", "list", "panel",
                     "wraplist", "fixedlist", "slider", "spincontrol", "spincontrolex",
                     "scrollbar", "textbox"}
        for control in include.iter("control"):
            self.assertNotIn(control.get("type"), focusable)
        for tag in ("onclick", "onfocus", "onup", "ondown", "onleft", "onright", "onback"):
            self.assertIsNone(include.find(".//" + tag), tag)
        for control in include.iter("control"):
            if control.get("type") == "grouplist":
                kinds = {child.get("type") for child in control.findall("control")}
                self.assertEqual(kinds, {"label"})

    def test_countdown_card_matches_the_music_osd_next_preview(self):
        furniture = ET.parse(SKIN_ROOT / "1080i" / "Includes_Furniture.xml").getroot()
        include = furniture.find("./include[@name='Furniture_NextTrack']")
        card = include.find(".//include[@content='Object_NextItem']")
        self.assertIsNotNone(card)
        self.assertEqual("square", card.findtext("param[@name='shape']"))
        self.assertEqual("right", card.findtext("param[@name='corner']"))
        # the countdown rides in the header line, as "Up next in 12s"
        self.assertEqual("$VAR[Label_NextTrack_Header]", card.findtext("param[@name='header']"))
        self.assertIn("NextTrack.thumb", card.findtext("param[@name='art']"))
        self.assertIn("NextTrack.title", card.findtext("param[@name='title']"))
        self.assertIn("NextTrack.artist", card.findtext("param[@name='subtitle']"))
        text = ET.tostring(include, encoding="unicode")
        self.assertNotIn("progress/circle", text)
        self.assertNotIn("<bottom>", text)
        visible = [node.text or "" for node in card.findall("visible")]
        self.assertTrue(any("NextTrack.IsVisible" in value for value in visible))
        # never stack on the identical OSD next preview (Custom 1154)
        self.assertTrue(any("1154" in value for value in visible))

    def test_header_clock_yields_the_corner_during_the_countdown(self):
        furniture = ET.parse(SKIN_ROOT / "1080i" / "Includes_Furniture.xml").getroot()
        header_right = furniture.find("./include[@name='Furniture_Header_Right']/definition/control")
        visible = [node.text or "" for node in header_right.findall("visible")]
        self.assertTrue(
            any("String.IsEmpty(Window(Home).Property(NextTrack.IsVisible))" in value for value in visible)
        )

    def test_service_still_skips_its_own_dialog_for_this_skin(self):
        # service.nexttrack opens a blocking dialog only when the skin lacks this file.
        self.assertTrue((SKIN_ROOT / "1080i" / "script-nexttrack-nexttrack.xml").exists())


if __name__ == "__main__":
    unittest.main()

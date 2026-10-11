import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


SKIN_ROOT = Path(__file__).resolve().parents[1]
WATCHER = SKIN_ROOT / "1080i" / "Custom_1156_Overlay_IdleReturn.xml"


def _expression(name):
    root = ET.parse(SKIN_ROOT / "1080i" / "Includes_Expressions.xml").getroot()
    node = root.find(f"./expression[@name='{name}']")
    return node.text if node is not None else None


class IdleReturnToPlayerTests(unittest.TestCase):
    def setUp(self):
        self.window = ET.parse(WATCHER).getroot()
        self.visible = self.window.findtext("visible")

    def test_watcher_is_a_modeless_dialog_without_controls(self):
        self.assertEqual(self.window.get("type"), "dialog")
        self.assertEqual(self.window.get("id"), "1156")
        self.assertIsNone(self.window.find("defaultcontrol"))
        self.assertEqual(list(self.window.find("controls")), [])

    def test_watcher_needs_playing_media_idle_time_and_no_blocker(self):
        for part in (
            "Player.HasMedia",
            "!Player.HasGame",
            "!Skin.String(Idle.ReturnToPlayer,Off)",
            "$EXP[Exp_IdleReturnToPlayer_Due]",
            "!$EXP[Exp_IdleReturnToPlayer_Blocked]",
        ):
            self.assertIn(part, self.visible)

    def test_dialogs_close_before_the_fullscreen_switch(self):
        onloads = [(node.get("condition"), node.text) for node in self.window.findall("onload")]
        self.assertEqual(onloads[0], (None, "Dialog.Close(all,true)"))
        self.assertEqual(
            onloads[1:],
            [
                ("Player.HasVideo", "ActivateWindow(fullscreenvideo)"),
                ("!Player.HasVideo", "ActivateWindow(visualisation)"),
            ],
        )

    def test_every_delay_choice_maps_to_its_idle_time(self):
        due = _expression("Exp_IdleReturnToPlayer_Due")
        self.assertIn("[String.IsEmpty(Skin.String(Idle.ReturnToPlayer)) + System.IdleTime(60)]", due)
        for seconds in ("30", "120", "300"):
            self.assertIn(
                f"[Skin.String(Idle.ReturnToPlayer,{seconds}) + System.IdleTime({seconds})]", due
            )

    def test_input_tasks_and_settings_block_the_return(self):
        blocked = _expression("Exp_IdleReturnToPlayer_Blocked")
        for window in (
            "Window.IsActive(fullscreenvideo)",
            "Window.IsActive(visualisation)",
            "Window.IsActive(slideshow)",
            "System.ScreenSaverActive",
            "Window.IsVisible(virtualkeyboard)",
            "Window.IsVisible(numericinput)",
            "Window.IsVisible(busydialog)",
            "Window.IsVisible(progressdialog)",
            "Window.IsVisible(yesnodialog)",
            "Window.IsVisible(settings)",
            "Window.IsVisible(skinsettings)",
            "Window.IsVisible(addonsettings)",
            "Window.IsVisible(filebrowser)",
        ):
            self.assertIn(window, blocked)
        # Every custom window it names must exist.
        for window_id in re.findall(r"Window\.IsVisible\((\d+)\)", blocked):
            self.assertTrue(list((SKIN_ROOT / "1080i").glob(f"Custom_{window_id}_*.xml")), window_id)

    def test_setting_cycles_through_every_choice(self):
        settings = (SKIN_ROOT / "1080i" / "Includes_SkinSettings.xml").read_text(encoding="utf-8")
        cycle = re.findall(
            r'<onclick condition="([^"]+)">(Skin\.(?:SetString|Reset)\(Idle\.ReturnToPlayer[^<]*)</onclick>',
            settings,
        )
        self.assertEqual(
            cycle,
            [
                ("Skin.String(Idle.ReturnToPlayer,30)", "Skin.Reset(Idle.ReturnToPlayer)"),
                ("String.IsEmpty(Skin.String(Idle.ReturnToPlayer))", "Skin.SetString(Idle.ReturnToPlayer,120)"),
                ("Skin.String(Idle.ReturnToPlayer,120)", "Skin.SetString(Idle.ReturnToPlayer,300)"),
                ("Skin.String(Idle.ReturnToPlayer,300)", "Skin.SetString(Idle.ReturnToPlayer,Off)"),
                ("Skin.String(Idle.ReturnToPlayer,Off)", "Skin.SetString(Idle.ReturnToPlayer,30)"),
            ],
        )
        strings = (SKIN_ROOT / "language" / "resource.language.en_gb" / "strings.po").read_text(encoding="utf-8")
        self.assertIn('msgctxt "#31992"\nmsgid "Return to playback when idle"', strings)


if __name__ == "__main__":
    unittest.main()

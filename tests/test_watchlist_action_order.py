import subprocess
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


SKIN_ROOT = Path(__file__).resolve().parents[1]


class WatchlistActionOrderTests(unittest.TestCase):
    def test_default_skinvariables_generated_include_is_packaged(self):
        fallback = (
            SKIN_ROOT / "1080i" / "script-skinvariables-generator-includes-.xml"
        )

        self.assertTrue(fallback.is_file())
        self.assertIn("<includes>", fallback.read_text(encoding="utf-8"))
        self.assertIn(
            "!1080i/script-skinvariables-generator-includes-.xml",
            (SKIN_ROOT / ".gitignore").read_text(encoding="utf-8"),
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(SKIN_ROOT),
                "ls-files",
                "--error-unmatch",
                "1080i/script-skinvariables-generator-includes-.xml",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

    def test_skin_timer_definition_is_packaged(self):
        timer_file = SKIN_ROOT / "1080i" / "Timers.xml"

        self.assertTrue(timer_file.is_file())
        self.assertEqual(ET.parse(timer_file).getroot().tag, "timers")

    def test_watchlist_command_keeps_the_detail_dialog_open_and_preserves_focus(self):
        source = (SKIN_ROOT / "1080i" / "Includes_DialogInfo.xml").read_text(
            encoding="utf-8"
        )
        button = source.split('<param name="id">4001</param>', 1)[1].split(
            "</include>", 1
        )[0]

        self.assertIn("<onclick>$VAR[Action_DialogInfo_PlayMedia]</onclick>", button)
        self.assertIn('content="Button_DialogInfo_ActionPill"', source)
        self.assertNotIn("<enable>", button)
        self.assertIn(
            "!$EXP[Exp_PlexWatchlist_Target]",
            button,
        )
        self.assertIn("String.IsEqual(ListItem.DBTYPE,movie)", button)
        self.assertIn("String.IsEqual(ListItem.DBTYPE,tvshow)", button)
        self.assertNotIn("<onclick>Dialog.Close(1190,true)</onclick>", button)

        actions = (SKIN_ROOT / "1080i" / "Includes_Actions.xml").read_text(
            encoding="utf-8"
        )
        self.assertIn("PKC.Watchlist.Detail.Pending", actions)
        self.assertIn("SetFocus(4001)", actions)

    def test_watchlist_detail_bootstraps_from_plex_and_projects_state(self):
        dialog = (SKIN_ROOT / "1080i" / "DialogVideoInfo.xml").read_text(
            encoding="utf-8"
        )
        labels = (SKIN_ROOT / "1080i" / "Includes_Labels.xml").read_text(
            encoding="utf-8"
        )
        actions = (SKIN_ROOT / "1080i" / "Includes_Actions.xml").read_text(
            encoding="utf-8"
        )

        self.assertIn("mode=watchlist_status_tmdb", dialog)
        self.assertIn("mode=watchlist_status_key", dialog)
        self.assertIn("mode=watchlist_status_monitor", dialog)
        self.assertNotIn(
            "<onload>ClearProperty(PKC.Watchlist.Detail.Revision,Home)</onload>",
            dialog,
        )
        self.assertIn(
            "<onunload>ClearProperty(PKC.Watchlist.Detail.Revision,Home)</onunload>",
            dialog,
        )
        self.assertIn(
            "<onunload>ClearProperty(PKC.Watchlist.Detail.StatusRevision,Home)</onunload>",
            dialog,
        )
        self.assertIn("PKC.Watchlist.Detail.RatingKey", dialog)
        self.assertIn("PKC.Watchlist.Detail.MonitorRevision", dialog)
        self.assertIn("PKC.Watchlist.Detail.State", labels)
        self.assertIn("PKC.Watchlist.Detail.State", actions)
        self.assertIn(
            "PKC.Watchlist.Detail.Identity",
            (SKIN_ROOT / "1080i" / "Includes_Expressions.xml").read_text(
                encoding="utf-8"
            ),
        )

        dialog_root = ET.fromstring(dialog)
        watchlist_onloads = [
            onload
            for onload in dialog_root.findall("onload")
            if "mode=watchlist_" in (onload.text or "")
        ]
        self.assertTrue(watchlist_onloads)
        self.assertTrue(
            all(
                "System.AddonIsEnabled(plugin.video.plexkodiconnect)"
                in onload.get("condition", "")
                for onload in watchlist_onloads
            )
        )

    def test_watchlist_actions_use_only_validated_monitor_identity(self):
        root = ET.parse(SKIN_ROOT / "1080i" / "Includes_Actions.xml").getroot()
        action = root.find("./variable[@name='Action_DialogInfo_PlayMedia']")
        watchlist_values = [
            value
            for value in action.findall("value")
            if "mode=watchlist_" in (value.text or "")
        ]

        self.assertEqual(len(watchlist_values), 8)
        self.assertTrue(
            all(
                "$EXP[Exp_PlexWatchlist_Target]" in value.get("condition", "")
                for value in watchlist_values
            )
        )
        action_source = "\n".join(value.text or "" for value in watchlist_values)
        action_conditions = "\n".join(
            value.get("condition", "") for value in watchlist_values
        )
        self.assertNotIn("TMDbHelper.ListItem.Monitor", action_source)
        self.assertNotIn("TMDbHelper.ListItem.Monitor", action_conditions)
        self.assertIn("PKC.Watchlist.Detail.TMDbId", action_source)
        self.assertIn("PKC.Watchlist.Detail.TMDbType", action_source)

    def test_detail_button_uses_png_hover_states_for_play_and_watchlist(self):
        root = ET.parse(SKIN_ROOT / "1080i" / "Includes_Images.xml").getroot()
        image_values = root.find(
            "./variable[@name='Image_DialogInfo_PlayButton']"
        ).findall("value")
        images = "\n".join(value.text or "" for value in image_values)
        conditions = "\n".join(value.get("condition", "") for value in image_values)

        for icon in (
            "play.png",
            "play3.png",
            "circle-check-regular.png",
            "circle-check.png",
            "circle-xmark-regular.png",
            "circle-xmark.png",
        ):
            self.assertIn(icon, images)
            self.assertTrue((SKIN_ROOT / "extras" / "icons" / icon).is_file())
        self.assertIn("Control.HasFocus(4001)", conditions)
        self.assertNotIn("circle-regular.png", images)
        self.assertNotIn("circle-plus.png", images)
        self.assertNotIn("square-plus.png", images)
        self.assertNotIn("play2.png", images)

    def test_detail_action_pills_keep_pngs_inside_their_button_geometry(self):
        root = ET.parse(SKIN_ROOT / "1080i" / "Includes_DialogInfo.xml").getroot()
        icon_controls = [
            control
            for control in root.findall(".//control[@type='image']")
            if control.findtext("texture")
            == "$VAR[Image_DialogInfo_PlayButton]"
        ]

        self.assertEqual(len(icon_controls), 2)
        self.assertTrue(
            all(
                control.findtext("width") == "56"
                and control.findtext("height") == "56"
                and control.findtext("left") == "26"
                and control.findtext("top") == "0"
                for control in icon_controls
            )
        )

        buttons = root.findall(".//include[@content='Button_DialogInfo_ActionPill']")
        self.assertEqual(len(buttons), 9)
        self.assertEqual(
            [button.findtext("param[@name='textoffsetx']") for button in buttons],
            ["58", None, None, None, None, "58", None, None, None],
        )
        for button in (buttons[0], buttons[5]):
            self.assertEqual(
                button.findtext("param[@name='width']"),
                "$VAR[Width_DialogInfo_PrimaryActionPill]",
            )
            self.assertEqual(button.findtext("param[@name='align']"), "left")

        button_template = (SKIN_ROOT / "1080i" / "Includes_Buttons.xml").read_text(
            encoding="utf-8"
        )
        self.assertIn('name="Button_DialogInfo_ActionPill"', button_template)
        self.assertIn('name="Width_DialogInfo_PrimaryActionPill"', button_template)
        self.assertIn('<param name="align">center</param>', button_template)
        self.assertIn("Texture_Highlight_ToggleButton_FakeFocus_H", button_template)
        self.assertIn("<focusedcolor>$VAR[ColorSelected]</focusedcolor>", button_template)


if __name__ == "__main__":
    unittest.main()

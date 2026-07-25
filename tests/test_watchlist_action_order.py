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

    def test_watchlist_command_runs_before_dialog_teardown(self):
        source = (SKIN_ROOT / "1080i" / "Includes_DialogInfo.xml").read_text(
            encoding="utf-8"
        )
        button = source.split('<param name="id">4001</param>', 1)[1].split(
            "</include>", 1
        )[0]

        self.assertLess(
            button.index("<onclick>$VAR[Action_DialogInfo_PlayMedia]</onclick>"),
            button.index("Dialog.Close(1190,true)"),
        )


if __name__ == "__main__":
    unittest.main()

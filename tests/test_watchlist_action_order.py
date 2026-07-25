import unittest
from pathlib import Path


SKIN_ROOT = Path(__file__).resolve().parents[1]


class WatchlistActionOrderTests(unittest.TestCase):
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

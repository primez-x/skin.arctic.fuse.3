import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


SKIN_ROOT = Path(__file__).resolve().parents[1]
NULL_PLAYLIST = "special://skin/extras/playlists/Null.xsp"
EPISODE_PATH = "$INFO[Container(5018).ListItem.FolderPath]"


class DialogInfoEpisodeProviderTests(unittest.TestCase):
    def test_episode_provider_has_a_nonempty_fallback_path(self):
        paths = ET.parse(SKIN_ROOT / "1080i" / "Includes_Paths.xml").getroot()
        variable = paths.find("./variable[@name='Path_VideoInfo_OnlineEpisodes']")

        self.assertIsNotNone(variable)
        values = variable.findall("value")
        self.assertEqual(len(values), 2)
        self.assertEqual(values[0].text, NULL_PLAYLIST)
        self.assertEqual(
            values[0].get("condition"),
            "String.IsEmpty(Container(5018).ListItem.FolderPath)",
        )
        self.assertEqual(values[1].text, EPISODE_PATH)

    def test_episode_widget_uses_the_guarded_path_variable(self):
        dialog_info = ET.parse(
            SKIN_ROOT / "1080i" / "Includes_DialogInfo.xml"
        ).getroot()
        episode_rows = [
            include
            for include in dialog_info.findall(".//include[@content='Widget_Info_Row']")
            if (include.find("param[@name='id']") is not None)
            and include.find("param[@name='id']").text == "19"
            and (include.find("param[@name='label']") is not None)
            and "Container(5018)" in (include.find("param[@name='label']").text or "")
        ]

        self.assertEqual(len(episode_rows), 1)
        self.assertEqual(
            episode_rows[0].find("content").text,
            "$VAR[Path_VideoInfo_OnlineEpisodes]",
        )


if __name__ == "__main__":
    unittest.main()

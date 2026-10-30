"""One-time addition of the YouTube search widget to an existing user searchwidgets menu.

The skin defaults carry the entry, but script.skinvariables copies the defaults into the
profile only when no user file exists, so menus saved before 4.5.0 never get the entry."""

import json
import re
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from test_legacy_image_path_migration import SKIN_ROOT, _load_service

MARKER = "Migration.YouTubeSearch"
ROLLBACK = ".before-youtube-search-migration"
NODE_PROPERTY = "SkinVariables.ShortcutsNode.skin.arctic.fuse.3-skinvariables-shortcut-searchwidgets.json"
ENTRY = {
    "label": "YouTube",
    "icon": "resource://resource.images.arctic.fuse.3/extras/icons/youtube.png",
    "path": "DefaultSearch-Youtube",
    "target": "videos",
    "widget_style": "Landscape",
}
SAVED = [
    {"label": "Movies", "icon": "resource://resource.images.arctic.fuse.3/extras/icons/film.png",
     "path": "DefaultSearch-Movies", "target": "videos", "widget_style": "Poster", "guid": "guid-808f8787"},
    {"label": "Spotify Tracks", "icon": "resource://resource.images.arctic.fuse.3/extras/icons/song.png",
     "path": "DefaultSearch-SpotifySongs", "target": "music", "widget_style": "Square", "guid": "guid-b3ccb14c"},
]


class YouTubeSearchMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.profile = root / "profile"
        self.nodes = self.profile / "addon_data/script.skinvariables/nodes/skin.arctic.fuse.3"
        self.nodes.mkdir(parents=True)
        self.menu = self.nodes / "skinvariables-shortcut-searchwidgets.json"
        self.rollback = self.menu.with_name(self.menu.name + ROLLBACK)
        self.values = {}
        self.commands = []
        self.addons = {"plugin.video.smarttube"}
        self.service = _load_service(root / "skin", self.profile, root / "resource", self.values, [])
        self.service.xbmc.getInfoLabel = lambda query: self.values.get(query[12:-1], "") \
            if query.startswith("Skin.String(") else ""

        def visible(condition):
            match = re.fullmatch(r"System\.HasAddon\(([^()]+)\)", condition)
            return bool(match) and match[1] in self.addons

        def execute(command):
            self.commands.append(command)
            match = re.fullmatch(r"Skin\.SetString\(([^,()]+),(.*)\)", command)
            if match:
                self.values[match[1]] = match[2]

        self.service.xbmc.getCondVisibility = visible
        self.service.xbmc.executebuiltin = execute

    def save(self, menu):
        text = json.dumps(menu, indent=4) + "\n"
        self.menu.write_text(text, encoding="utf-8")
        return text

    def migrate(self):
        self.assertTrue(callable(getattr(self.service, "_add_youtube_search_widget", None)),
                        "YouTube search migration is absent")
        return self.service._add_youtube_search_widget()

    def test_appends_entry_with_fresh_guid_and_keeps_a_rollback_copy(self):
        original = self.save(SAVED)
        self.assertTrue(self.migrate())
        menu = json.loads(self.menu.read_text(encoding="utf-8"))
        self.assertEqual(SAVED, menu[:2])
        self.assertEqual(3, len(menu))
        added = dict(menu[2])
        guid = added.pop("guid")
        self.assertEqual(ENTRY, added)
        self.assertRegex(guid, r"^guid-[0-9a-f]{8}$")
        self.assertNotIn(guid, {item["guid"] for item in SAVED})
        self.assertEqual(original, self.rollback.read_text(encoding="utf-8"))
        self.assertEqual("1", self.values[MARKER])
        self.assertIn("ClearProperty(Shortcuts.Checked.Version,Home)", self.commands)
        # script.skinvariables caches the parsed menu in a Home property and saves edits
        # from that copy; a stale copy would drop the new entry on the next edit.
        self.assertIn(f"ClearProperty({NODE_PROPERTY},Home)", self.commands)

    def test_second_run_is_a_no_op(self):
        self.save(SAVED)
        self.assertTrue(self.migrate())
        snapshot = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.nodes.iterdir()}
        self.commands.clear()
        self.assertFalse(self.migrate())
        self.assertEqual(snapshot, {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.nodes.iterdir()})
        self.assertEqual([], self.commands)

    def test_guid_never_collides_with_an_existing_one(self):
        self.save(SAVED)
        with patch.object(self.service.random, "randrange", side_effect=[0x808F8787, 0x12345678]):
            self.assertTrue(self.migrate())
        self.assertEqual("guid-12345678", json.loads(self.menu.read_text())[2]["guid"])

    def test_missing_user_file_is_left_to_the_skin_defaults(self):
        self.assertFalse(self.migrate())
        self.assertEqual([], list(self.nodes.iterdir()))
        self.assertEqual("1", self.values[MARKER])
        self.assertNotIn("ClearProperty(Shortcuts.Checked.Version,Home)", self.commands)

    def test_existing_entry_is_kept_even_when_disabled(self):
        for extra in ({}, {"disabled": "True"}):
            with self.subTest(extra=extra):
                self.values.clear()
                self.commands.clear()
                text = self.save(SAVED + [dict(ENTRY, label="My YouTube", guid="guid-0000abcd", **extra)])
                self.assertFalse(self.migrate())
                self.assertEqual(text, self.menu.read_text(encoding="utf-8"))
                self.assertFalse(self.rollback.exists())
                self.assertEqual("1", self.values[MARKER])
                self.assertEqual([f"Skin.SetString({MARKER},1)"], self.commands)

    def test_corrupt_or_unexpected_json_is_untouched_and_retried(self):
        for content in (b'[{"label": ', b"\xff", b"", b'{"label": "Movies"}', b'"text"'):
            with self.subTest(content=content):
                self.values.clear()
                self.commands.clear()
                self.menu.write_bytes(content)
                with patch.object(self.service.xbmc, "log") as log:
                    self.assertFalse(self.migrate())
                log.assert_called()
                self.assertEqual(content, self.menu.read_bytes())
                self.assertFalse(self.rollback.exists())
                self.assertNotIn(MARKER, self.values)
                self.assertEqual([], self.commands)
        self.save(SAVED)
        self.assertTrue(self.migrate())
        self.assertEqual("DefaultSearch-Youtube", json.loads(self.menu.read_text())[2]["path"])

    def test_smarttube_absent_changes_nothing_and_stays_pending(self):
        self.addons.clear()
        text = self.save(SAVED)
        with patch.object(self.service.xbmc, "log") as log:
            self.assertFalse(self.migrate())
        log.assert_not_called()
        self.assertEqual(text, self.menu.read_text(encoding="utf-8"))
        self.assertNotIn(MARKER, self.values)
        self.assertEqual([], self.commands)
        self.addons.add("plugin.video.smarttube")
        self.assertTrue(self.migrate())

    def test_marker_already_set_changes_nothing(self):
        self.values[MARKER] = "1"
        text = self.save(SAVED)
        with patch.object(self.service.xbmc, "log") as log:
            self.assertFalse(self.migrate())
        log.assert_not_called()
        self.assertEqual(text, self.menu.read_text(encoding="utf-8"))
        self.assertFalse(self.rollback.exists())
        self.assertEqual([], self.commands)

    def test_existing_rollback_copy_is_not_overwritten(self):
        self.save(SAVED)
        self.rollback.write_text("earlier backup", encoding="utf-8")
        self.assertTrue(self.migrate())
        self.assertEqual("earlier backup", self.rollback.read_text(encoding="utf-8"))

    def test_failed_write_preserves_the_menu_and_retries(self):
        text = self.save(SAVED)
        with patch.object(self.service.os, "replace", side_effect=OSError("disk full")):
            self.assertFalse(self.migrate())
        self.assertEqual(text, self.menu.read_text(encoding="utf-8"))
        self.assertEqual([], list(self.nodes.glob("*.tmp")) + list(self.nodes.glob(".*.tmp")))
        self.assertNotIn(MARKER, self.values)
        self.assertEqual([], self.commands)
        self.assertTrue(self.migrate())

    def test_startup_adds_the_entry_without_a_version_change(self):
        # SmartTube can be installed after the skin update, so the service checks on
        # every start until the marker is set, not only when the skin version changes.
        self.service.xbmc.Monitor = lambda: types.SimpleNamespace(waitForAbort=lambda seconds: False)
        self.service.xbmc.executeJSONRPC = lambda payload: json.dumps({"result": {"currentwindow": {"id": 10000}}})
        version = self.profile / "addon_data/skin.arctic.fuse.3/update_recovery.version"
        version.parent.mkdir(parents=True)
        version.write_text("3.9.0")
        self.save(SAVED)
        self.service.main()
        self.assertEqual("DefaultSearch-Youtube", json.loads(self.menu.read_text())[2]["path"])
        self.assertEqual("3.9.0", version.read_text())

    def test_skin_defaults_carry_the_entry(self):
        defaults = json.loads((SKIN_ROOT / "shortcuts/skinvariables-shortcut-searchwidgets.json").read_text())
        self.assertIn(ENTRY, defaults)


if __name__ == "__main__":
    unittest.main()

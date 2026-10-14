"""Regression coverage for update-time migration of legacy skin image paths."""

import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path


SKIN_ROOT = Path(__file__).resolve().parents[1]
LEGACY_PREFIX = "special://skin/extras/"
RESOURCE_PREFIX = "resource://resource.images.arctic.fuse.3/extras/"


def _load_service(skin_dir, profile_dir, resource_dir, values, builtin_calls):
    xbmc = types.ModuleType("xbmc")
    xbmc.LOGINFO, xbmc.LOGWARNING = 1, 2
    xbmc.log = lambda *args, **kwargs: None
    xbmc.getInfoLabel = lambda label: values.get(label[12:-1], "") if label.startswith("Skin.String(") else ""

    def execute_builtin(command):
        prefix = "Skin.SetString("
        if command.startswith(prefix) and command.endswith(")"):
            setting_id, value = command[len(prefix):-1].split(",", 1)
            builtin_calls.append((setting_id, value))
            values[setting_id] = value

    xbmc.executebuiltin = execute_builtin
    xbmc.getSkinDir = lambda: "skin.arctic.fuse.3"
    xbmc.Monitor = lambda: types.SimpleNamespace(waitForAbort=lambda seconds: True)

    xbmcaddon = types.ModuleType("xbmcaddon")
    xbmcaddon.Addon = lambda addon_id: types.SimpleNamespace(
        getAddonInfo=lambda name: "3.9.0" if name == "version" else ""
    )

    xbmcvfs = types.ModuleType("xbmcvfs")

    def translate_path(path):
        if path.startswith("special://skin/"):
            return str(skin_dir / path[len("special://skin/"):])
        if path.startswith("special://profile/"):
            return str(profile_dir / path[len("special://profile/"):])
        return path

    def local_path(path):
        if path.startswith(RESOURCE_PREFIX):
            return resource_dir / path[len(RESOURCE_PREFIX):]
        return Path(path)

    xbmcvfs.translatePath = translate_path

    def exists(path):
        candidate = local_path(path)
        if path.startswith(RESOURCE_PREFIX):
            return candidate.is_dir() if path.endswith("/") else candidate.is_file()
        return candidate.exists()

    xbmcvfs.exists = exists

    saved = {name: sys.modules.get(name) for name in ("xbmc", "xbmcaddon", "xbmcvfs")}
    sys.modules.update(xbmc=xbmc, xbmcaddon=xbmcaddon, xbmcvfs=xbmcvfs)
    try:
        spec = importlib.util.spec_from_file_location("skin_service_image_migration", SKIN_ROOT / "service.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        for name, value in saved.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value
    return module


class LegacyImagePathMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.skin = root / "skin"
        self.profile = root / "profile"
        self.resource = root / "resource" / "extras"
        self.settings = self.profile / "addon_data" / "skin.arctic.fuse.3" / "settings.xml"
        self.nodes = self.profile / "addon_data" / "script.skinvariables" / "nodes" / "skin.arctic.fuse.3"
        self.settings.parent.mkdir(parents=True)
        self.nodes.mkdir(parents=True)
        self.values = {
            "Background.Image": LEGACY_PREFIX + "backgrounds/default.jpg",
            "Startup.ImageFolder": LEGACY_PREFIX + "profiles",
            "OptionsTiles.01.Icon": LEGACY_PREFIX + "icons/custom.png",
            "Missing.Icon": LEGACY_PREFIX + "icons/missing.png",
            "External.Icon": "/storage/custom/icon.png",
            "Playlist.File": LEGACY_PREFIX + "playlists/default.xsp",
            "Shortcut.Data": LEGACY_PREFIX + "skinvariables-shortcut-config.json",
        }
        settings = "\n".join(
            f'<setting id="{key}" value="{value}" />' for key, value in self.values.items()
        )
        self.settings.write_text(f"<settings>{settings}</settings>\n", encoding="utf-8")
        self.settings_before = self.settings.read_text(encoding="utf-8")
        self._asset("backgrounds/default.jpg")
        self._asset("profiles/.keep")
        self._asset("icons/custom.png")
        self.calls = []

    def tearDown(self):
        self.tmp.cleanup()

    def _asset(self, relative):
        path = self.resource / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        return path

    def _service(self):
        return _load_service(self.skin, self.profile, self.resource, self.values, self.calls)

    def test_settings_migrate_only_existing_images_and_directories_through_live_skin_api(self):
        service = self._service()

        self.assertTrue(service._migrate_legacy_image_paths())

        self.assertEqual(RESOURCE_PREFIX + "backgrounds/default.jpg", self.values["Background.Image"])
        self.assertEqual(RESOURCE_PREFIX + "profiles/", self.values["Startup.ImageFolder"])
        self.assertEqual(RESOURCE_PREFIX + "icons/custom.png", self.values["OptionsTiles.01.Icon"])
        self.assertEqual(LEGACY_PREFIX + "icons/missing.png", self.values["Missing.Icon"])
        self.assertEqual("/storage/custom/icon.png", self.values["External.Icon"])
        self.assertEqual(LEGACY_PREFIX + "playlists/default.xsp", self.values["Playlist.File"])
        self.assertEqual(LEGACY_PREFIX + "skinvariables-shortcut-config.json", self.values["Shortcut.Data"])
        self.assertEqual(
            {"Background.Image", "Startup.ImageFolder", "OptionsTiles.01.Icon"},
            {setting_id for setting_id, _ in self.calls},
        )
        self.assertEqual(self.settings_before, self.settings.read_text(encoding="utf-8"))

    def test_saved_shortcut_siblings_migrate_with_scoped_rollback_and_idempotence(self):
        source = {
            "background": LEGACY_PREFIX + "backgrounds/default.jpg",
            "startup_folder": LEGACY_PREFIX + "profiles/",
            "custom_icon": LEGACY_PREFIX + "icons/custom.png",
            "missing_icon": LEGACY_PREFIX + "icons/missing.png",
            "playlist": LEGACY_PREFIX + "playlists/default.xsp",
            "skin_json": LEGACY_PREFIX + "skinvariables-shortcut-config.json",
            "external": "/storage/custom/icon.png",
            "nested": [{"icon": LEGACY_PREFIX + "icons/custom.png"}],
        }
        active = self.nodes / "skinvariables-shortcut-homewidgets.json"
        original = json.dumps(source, indent=4) + "\n"
        active.write_text(original, encoding="utf-8")
        sibling = self.profile / "addon_data" / "script.skinvariables" / "nodes" / "other.skin" / active.name
        sibling.parent.mkdir(parents=True)
        sibling.write_text(json.dumps({"icon": LEGACY_PREFIX + "icons/custom.png"}), encoding="utf-8")
        backup = self.profile / "addon_data" / "skin.arctic.fuse.3" / "codex-backups" / "old" / "Includes_Background.xml"
        backup.parent.mkdir(parents=True)
        backup.write_text(LEGACY_PREFIX + "backgrounds/default.jpg", encoding="utf-8")
        backup_before = backup.read_text(encoding="utf-8")
        rollback = active.with_name(active.name + ".before-resource-image-migration")

        service = self._service()
        self.assertTrue(service._migrate_legacy_image_paths())

        migrated = json.loads(active.read_text(encoding="utf-8"))
        self.assertEqual(RESOURCE_PREFIX + "backgrounds/default.jpg", migrated["background"])
        self.assertEqual(RESOURCE_PREFIX + "profiles/", migrated["startup_folder"])
        self.assertEqual(RESOURCE_PREFIX + "icons/custom.png", migrated["custom_icon"])
        self.assertEqual(LEGACY_PREFIX + "icons/missing.png", migrated["missing_icon"])
        self.assertEqual(LEGACY_PREFIX + "playlists/default.xsp", migrated["playlist"])
        self.assertEqual(LEGACY_PREFIX + "skinvariables-shortcut-config.json", migrated["skin_json"])
        self.assertEqual("/storage/custom/icon.png", migrated["external"])
        self.assertEqual(RESOURCE_PREFIX + "icons/custom.png", migrated["nested"][0]["icon"])
        self.assertEqual(original, rollback.read_text(encoding="utf-8"))
        self.assertEqual(LEGACY_PREFIX + "icons/custom.png", json.loads(sibling.read_text(encoding="utf-8"))["icon"])
        self.assertEqual(backup_before, backup.read_text(encoding="utf-8"))
        calls_after_first_run = list(self.calls)

        self.assertFalse(service._migrate_legacy_image_paths())
        self.assertEqual(calls_after_first_run, self.calls)
        self.assertEqual(original, rollback.read_text(encoding="utf-8"))

    def test_inactive_skin_preserves_pending_recovery_until_switch_back(self):
        version_file = self.settings.parent / "update_recovery.version"
        version_file.write_text("3.8.9", encoding="utf-8")
        template = SKIN_ROOT / "shortcuts" / "skinvariables-skinusers.xmltemplate"
        (self.skin / "shortcuts").mkdir(parents=True)
        (self.skin / "1080i").mkdir()
        (self.skin / "shortcuts" / template.name).write_text(template.read_text())
        standin = SKIN_ROOT / "1080i" / "script-skinvariables-generator-includes-.xml"
        (self.skin / "1080i" / standin.name).write_text(standin.read_text())
        self.values["SkinVariables.SkinUser"] = "anna"
        active = self.nodes / "skinvariables-shortcut-powermenu.json"
        active.write_text(json.dumps({"icon": LEGACY_PREFIX + "icons/custom.png"}))
        service = self._service()
        service.xbmc.getSkinDir = lambda: "skin.estuary"

        service.main()

        self.assertEqual("3.8.9", version_file.read_text())
        self.assertEqual(LEGACY_PREFIX + "icons/custom.png", json.loads(active.read_text())["icon"])
        self.assertFalse((self.skin / "1080i" / "script-skinvariables-skinusers.xml").exists())

        service.xbmc.getSkinDir = lambda: "skin.arctic.fuse.3"
        service.xbmc.Monitor = lambda: types.SimpleNamespace(waitForAbort=lambda seconds: False)
        service.xbmc.executeJSONRPC = lambda payload: json.dumps(
            {"result": {"currentwindow": {"id": 10000, "label": "Home"}}})
        service.main()

        self.assertEqual("3.9.0", version_file.read_text())
        self.assertEqual(RESOURCE_PREFIX + "icons/custom.png", json.loads(active.read_text())["icon"])
        restored = self.skin / "1080i" / "script-skinvariables-skinusers.xml"
        self.assertEqual(template.read_text().format(slug="anna"), restored.read_text())

    def test_inactive_skin_does_not_create_a_recovery_marker(self):
        service = self._service()
        service.xbmc.getSkinDir = lambda: "skin.estuary"
        service.main()
        self.assertFalse((self.settings.parent / "update_recovery.version").exists())

    def test_update_recovery_runs_path_migration_before_returning(self):
        version_file = self.settings.parent / "update_recovery.version"
        version_file.write_text("3.8.9", encoding="utf-8")
        active = self.nodes / "skinvariables-shortcut-powermenu.json"
        active.write_text(json.dumps({"icon": LEGACY_PREFIX + "icons/custom.png"}), encoding="utf-8")

        self._service().main()

        self.assertEqual(RESOURCE_PREFIX + "icons/custom.png", json.loads(active.read_text(encoding="utf-8"))["icon"])


if __name__ == "__main__":
    unittest.main()

import hashlib
import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


SKIN_ROOT = Path(__file__).resolve().parents[1]
SKIN_XML = SKIN_ROOT / "1080i"
RESOURCE_ID = "resource.images.arctic.fuse.3"
RESOURCE_PREFIX = f"resource://{RESOURCE_ID}/extras/"
LEGACY_PREFIX = "special://skin/extras/"
LEGACY_REFERENCE = re.compile(re.escape(LEGACY_PREFIX) + r"([^\"'<>\s,\]\)]+)")


class ResourceImageAndFontsetTests(unittest.TestCase):
    def test_runtime_artwork_paths_use_the_resource_addon(self):
        resource_paths = []
        source_roots = (SKIN_XML, SKIN_ROOT / "shortcuts")
        for source_root in source_roots:
            for path in source_root.rglob("*"):
                if path.suffix.lower() not in {".xml", ".json", ".py"}:
                    continue
                text = path.read_text(encoding="utf-8")
                for relative in LEGACY_REFERENCE.findall(text):
                    with self.subTest(file=path.name, reference=relative):
                        self.assertTrue(relative.lower().endswith((".xsp", ".json")))
                        self.assertTrue((SKIN_ROOT / "extras" / relative).is_file())
                for line in text.splitlines():
                    if RESOURCE_PREFIX not in line:
                        continue
                    with self.subTest(file=path.name, line=line.strip()):
                        self.assertNotRegex(line.lower(), r"\.(xsp|json)(?:[\"'<>\s,\]]|$)")
                resource_paths.extend(
                    line for line in text.splitlines() if RESOURCE_PREFIX in line
                )

        self.assertGreater(len(resource_paths), 0)
        addon = ET.parse(SKIN_ROOT / "addon.xml").getroot()
        imported_ids = {
            node.get("addon") for node in addon.findall("./requires/import")
        }
        self.assertIn(RESOURCE_ID, imported_ids)

    def test_skinvariables_default_icons_remain_as_exact_skin_fallbacks(self):
        expected_hashes = {
            "icons/folder.png": "ca578815dd9205a4a7c2fd51619b72504eee0524ecef668b0e53978c3f62935d",
            "icons/circle-plus.png": "b855a6eb916472ae4e8c72bcd209371fa2bd4c8605b7040d7866c4024ce4bc1f",
            "icons/shapes.png": "087b812154509a73d3551ad3a3398bc0eb8c039a65f2a42712768eae85eddc09",
        }
        skin_images = {
            path.relative_to(SKIN_ROOT / "extras").as_posix()
            for path in (SKIN_ROOT / "extras").rglob("*")
            if path.is_file() and path.suffix.lower() in {".jpg", ".png"}
        }

        self.assertEqual(set(expected_hashes), skin_images)
        for relative, expected_hash in expected_hashes.items():
            path = SKIN_ROOT / "extras" / relative
            with self.subTest(path=relative):
                self.assertEqual(expected_hash, hashlib.sha256(path.read_bytes()).hexdigest())

    def test_large_text_fontset_reuses_default_roles_and_keeps_default(self):
        fontsets = {
            node.get("id"): node
            for node in ET.parse(SKIN_XML / "Font.xml").getroot().findall("fontset")
        }
        self.assertIn("Default", fontsets)
        self.assertIn("Default (Unicode)", fontsets)
        self.assertEqual(fontsets["Default"].get("unicode"), "false")

        large = fontsets["Readable (Large Text)"]
        base_include = large.find("./include[@content='Font_Default']")
        self.assertIsNotNone(base_include)
        base_params = {
            node.get("name"): node.text
            for node in ET.parse(SKIN_XML / "Includes_Font.xml")
            .getroot()
            .find("./include[@name='Font_Default']")
            .findall("param")
        }
        large_params = {
            node.get("name"): node.text for node in base_include.findall("param")
        }
        role_sizes = (
            "size_hint",
            "size_tiny",
            "size_mini",
            "size_main",
            "size_midi",
            "size_head",
            "size_huge",
            "size_main_x2",
            "size_huge_x2",
            "size_midi_x2",
        )
        for name in role_sizes:
            with self.subTest(role=name):
                self.assertGreater(int(large_params[name]), int(base_params[name]))

    def test_settings_level_label_explains_existing_toggle(self):
        labels = ET.parse(SKIN_XML / "Includes_Labels.xml").getroot()
        variable = labels.find("./variable[@name='Label_SkinSettings_Level']")
        self.assertIsNotNone(variable)
        expected_labels = {
            "Integer.IsEqual(Skin.String(Skin.SettingsLevel),3)": "$LOCALIZE[5]: $LOCALIZE[10039]",
            "Integer.IsEqual(Skin.String(Skin.SettingsLevel),2)": "$LOCALIZE[5]: $LOCALIZE[10038]",
            "Integer.IsEqual(Skin.String(Skin.SettingsLevel),1)": "$LOCALIZE[5]: $LOCALIZE[10037]",
            None: "$LOCALIZE[5]: $LOCALIZE[10036]",
        }
        self.assertEqual(expected_labels, {
            value.get("condition"): (value.text or "")
            for value in variable.findall("value")
        })

        settings = (SKIN_XML / "SkinSettings.xml").read_text(encoding="utf-8")
        self.assertIn("Skin.String(Skin.SettingsLevel)", settings)
        self.assertIn("Skin.SetString(Skin.SettingsLevel", settings)
        settings_xml = ET.fromstring(settings)
        level_item = settings_xml.find(".//item[@id='8']")
        self.assertIsNotNone(level_item)
        self.assertEqual(level_item.get("description"), "Settings level")

    def test_fullscreen_overlay_textures_load_in_background(self):
        overlay_textures = []
        for path in SKIN_XML.glob("*.xml"):
            root = ET.parse(path).getroot()
            for texture in root.iter("texture"):
                value = texture.text or ""
                if "/extras/backgrounds/overlay/combined_" in value:
                    overlay_textures.append((path, texture))

        self.assertGreater(len(overlay_textures), 0)
        for path, texture in overlay_textures:
            with self.subTest(file=path.name, texture=texture.text):
                self.assertEqual(texture.get("background"), "true")


if __name__ == "__main__":
    unittest.main()

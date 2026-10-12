"""Skin users: after an install or update the skin-user include file is gone until the
user logs in again, so the skin ships a stand-in and service.py restores the user's file."""

import importlib.util
import sys
import tempfile
import types
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


SKIN_ROOT = Path(__file__).resolve().parents[1]
SKIN = SKIN_ROOT / "1080i"
TEMPLATE = SKIN_ROOT / "shortcuts" / "skinvariables-skinusers.xmltemplate"


class SkinUserStandInTests(unittest.TestCase):
    def test_skin_user_include_file_is_shipped(self):
        # Includes.xml loads it whenever Skin.String(SkinVariables.SkinUser) is set
        includes = ET.parse(SKIN / "Includes.xml").getroot()
        files = {n.get("file") for n in includes.findall("include") if n.get("file")}
        self.assertIn("script-skinvariables-skinusers.xml", files)
        standin = ET.parse(SKIN / "script-skinvariables-skinusers.xml").getroot()
        (include,) = standin.findall("include")
        # Same file the template names for the default user, and it exists in the package
        expected = ET.fromstring(TEMPLATE.read_text(encoding="utf-8").format(slug="")).find("include").get("file")
        self.assertEqual(expected, include.get("file"))
        self.assertTrue((SKIN / include.get("file")).is_file())


def _load_service(skin_dir, slug):
    xbmc = types.ModuleType("xbmc")
    xbmc.LOGINFO, xbmc.LOGWARNING = 1, 2
    xbmc.log = lambda *a, **k: None
    xbmc.getInfoLabel = lambda label: slug if label == "Skin.String(SkinVariables.SkinUser)" else ""
    xbmcaddon = types.ModuleType("xbmcaddon")
    xbmcvfs = types.ModuleType("xbmcvfs")
    xbmcvfs.translatePath = lambda path: path.replace("special://skin/", f"{skin_dir}/")
    saved = {name: sys.modules.get(name) for name in ("xbmc", "xbmcaddon", "xbmcvfs")}
    sys.modules.update(xbmc=xbmc, xbmcaddon=xbmcaddon, xbmcvfs=xbmcvfs)
    try:
        spec = importlib.util.spec_from_file_location("skin_service", SKIN_ROOT / "service.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        for name, value in saved.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value
    return module


class SkinUserRestoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.skin = Path(self.tmp.name)
        (self.skin / "shortcuts").mkdir()
        (self.skin / "1080i").mkdir()
        (self.skin / "shortcuts" / TEMPLATE.name).write_text(TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
        for name in ("script-skinvariables-skinusers.xml", "script-skinvariables-generator-includes-.xml"):
            (self.skin / "1080i" / name).write_text((SKIN / name).read_text(encoding="utf-8"), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_restores_the_logged_in_users_include_after_an_update(self):
        service = _load_service(self.skin, "anna")
        self.assertTrue(service._restore_skin_user_includes())
        skinusers = (self.skin / "1080i" / "script-skinvariables-skinusers.xml").read_text(encoding="utf-8")
        self.assertEqual(TEMPLATE.read_text(encoding="utf-8").format(slug="anna"), skinusers)
        user_file = self.skin / "1080i" / "script-skinvariables-generator-includes-anna.xml"
        self.assertEqual((SKIN / "script-skinvariables-generator-includes-.xml").read_text(encoding="utf-8"),
                         user_file.read_text(encoding="utf-8"))
        self.assertFalse(service._restore_skin_user_includes())  # idempotent

    def test_keeps_an_existing_generated_user_file(self):
        user_file = self.skin / "1080i" / "script-skinvariables-generator-includes-anna.xml"
        user_file.write_text("<includes>generated</includes>", encoding="utf-8")
        _load_service(self.skin, "anna")._restore_skin_user_includes()
        self.assertEqual("<includes>generated</includes>", user_file.read_text(encoding="utf-8"))

    def test_does_nothing_without_a_skin_user(self):
        before = (self.skin / "1080i" / "script-skinvariables-skinusers.xml").read_text(encoding="utf-8")
        self.assertFalse(_load_service(self.skin, "")._restore_skin_user_includes())
        self.assertEqual(before, (self.skin / "1080i" / "script-skinvariables-skinusers.xml").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

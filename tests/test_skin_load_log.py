"""Skin-caused Kodi log errors seen on CoreELEC boxes: generated includes missing on the
first load after an install or update, and resource:// image add-ons that are installed
but disabled."""

import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


SKIN = Path(__file__).resolve().parents[1] / "1080i"
PLACEHOLDER = "script-skinvariables-generator-includes-.xml"


def _skin_files():
    return [p for p in sorted(SKIN.glob("*.xml")) if not p.name.startswith("script-skinvariables")]


_TREES = {}


def _tree(path):
    if path not in _TREES:
        _TREES[path] = ET.parse(path).getroot()
    return _TREES[path]


def _definitions():
    found = {}
    for path in _skin_files():
        for node in _tree(path).iter("include"):
            if node.get("name"):
                found.setdefault(node.get("name"), node)
    return found


def _callers(name):
    for path in _skin_files():
        for node in _tree(path).iter("include"):
            if node.get("content") == name or (node.text or "").strip() == name:
                yield node


class GeneratedIncludePlaceholderTests(unittest.TestCase):
    """Until script.skinvariables writes the generated includes, Kodi loads the packaged
    placeholder. Every generated include the skin references must be defined there, or the
    first load logs "Skin has invalid include" and a <content> list keeps the literal
    <include> element, which Kodi fetches as the path "include"."""

    def _referenced(self):
        """Generated include names the skin uses: <include> text, include content= and
        <param> values (passed on to an <include>), with $PARAM[window] expanded over the
        windows the enclosing include is called with."""
        definitions = _definitions()
        names = set()
        for path in _skin_files():
            for node in _tree(path).iter():
                if node.tag == "include":
                    values = [node.get("content") or "", node.text or ""]
                elif node.tag == "param":
                    values = [node.text or ""]
                else:
                    continue
                for value in (v.strip() for v in values):
                    if not value.startswith("skinvariables-"):
                        continue
                    if "$PARAM[window]" not in value:
                        names.add(value)
                        continue
                    container = next(n for n, d in definitions.items() if node in set(d.iter()))
                    windows = {p.text for c in _callers(container) for p in c.findall("param[@name='window']")}
                    self.assertTrue(windows, container)
                    names |= {value.replace("$PARAM[window]", w) for w in windows}
        return names

    def test_placeholder_defines_every_generated_include(self):
        referenced = self._referenced()
        self.assertIn("skinvariables-homewidgets-standard", referenced)
        self.assertIn("skinvariables-powermenu-staticitems", referenced)
        self.assertIn("skinvariables-1104submenu-staticitems", referenced)
        stubs = {n.get("name") for n in ET.parse(SKIN / PLACEHOLDER).getroot().findall("include")}
        self.assertEqual(set(), referenced - stubs)

    def test_stubs_register_but_insert_nothing(self):
        # Kodi registers an include only when it has a child node, and inserts only its
        # child elements: a comment child registers the name and adds nothing (an element
        # in a <content> list would be fetched as a directory path).
        parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
        root = ET.parse(SKIN / PLACEHOLDER, parser=parser).getroot()
        for stub in root.findall("include"):
            children = list(stub)
            self.assertTrue(children, stub.get("name"))
            self.assertTrue(all(c.tag is ET.Comment for c in children), stub.get("name"))
            self.assertFalse((stub.text or "").strip(), stub.get("name"))


class ResourceImageAddonTests(unittest.TestCase):
    def test_resource_paths_require_the_addon_enabled(self):
        # resource:// only resolves enabled add-ons, so an installed but disabled one logged
        # "GetDirectory - Error getting resource://resource.images.arctic.waves/" each time
        # the busy dialog showed. System.HasAddon is true for disabled add-ons.
        definitions = _definitions()
        checked = 0
        for path in _skin_files():
            for node in ET.parse(path).getroot().iter():
                condition = node.get("condition") or ""
                for addon in re.findall(r"System\.(?:HasAddon|AddonIsEnabled)\((resource\.images\.[\w.]+)\)", condition):
                    body = node.text or ""
                    if body.strip() in definitions:
                        body = ET.tostring(definitions[body.strip()], encoding="unicode")
                    if f"resource://{addon}/" not in body:
                        continue
                    checked += 1
                    with self.subTest(file=path.name, addon=addon):
                        self.assertIn(f"System.AddonIsEnabled({addon})", condition)
        self.assertGreaterEqual(checked, 2)


if __name__ == "__main__":
    unittest.main()

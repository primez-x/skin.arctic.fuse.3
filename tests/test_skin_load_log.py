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
    """resource:// resolves enabled add-ons only, and System.HasAddon is true for a disabled
    one, so an unguarded directory path into an installed but disabled image pack logs
    "GetDirectory - Error getting resource://<pack>/" whenever Kodi lists it (<content>,
    <imagepath>, a variable value or param that feeds one). Every resource:// use in the
    skin is enumerated; directory-form ones (the value ends in "/") must be guarded by
    System.AddonIsEnabled(<pack>): a condition on the element or an ancestor, the <value>
    condition of a variable, or, inside an include definition, on every call of that include.
    File-form ones (icons, fonts, "$INFO[x,resource://pack/,.png]") are single textures."""

    PATH = re.compile(r"resource://([\w.]+)/")

    def _parents(self, root):
        return {child: parent for parent in root.iter() for child in parent}

    def _guarded(self, node, addon, parents, definitions, depth=0):
        guard = f"System.AddonIsEnabled({addon})"
        while node is not None:
            if guard in (node.get("condition") or ""):
                return True
            if node.tag == "include" and node.get("name"):
                calls = list(self._calls(node.get("name")))
                return bool(calls) and depth < 6 and all(
                    self._guarded(call, addon, call_parents, definitions, depth + 1)
                    for call, call_parents in calls)
            node = parents.get(node)
        return False

    def _calls(self, name):
        for path in _skin_files():
            root = _tree(path)
            parents = self._parents(root)
            for node in root.iter("include"):
                if node.get("content") == name or (node.text or "").strip() == name:
                    yield node, parents

    def test_every_resource_directory_path_requires_the_addon_enabled(self):
        definitions = _definitions()
        directories = 0
        for path in _skin_files():
            root = _tree(path)
            parents = self._parents(root)
            for node in root.iter():
                for value in [node.text or "", *node.attrib.values()]:
                    value = value.strip()
                    for addon in self.PATH.findall(value):
                        if not value.endswith("/"):
                            continue
                        directories += 1
                        with self.subTest(file=path.name, tag=node.tag, value=value[:80]):
                            self.assertTrue(self._guarded(node, addon, parents, definitions))
        self.assertGreaterEqual(directories, 5)


class ParamIncludeTests(unittest.TestCase):
    """An `<include>$PARAM[name]</include>` whose effective parameter value can be
    empty resolves to an empty include name, and Kodi logs "Skin has invalid
    include: " on every load of the window (seen for DialogSelect on CoreELEC).
    Following Kodi's semantics (caller parameters win, defaults fill gaps, an
    explicit empty value overrides a default, and a forward of an undefined
    parameter is dropped so the target's default applies), every direct call
    chain must leave the parameter non-empty: a literal, a non-empty default
    (a real include or the Include_Empty no-op stub), or a forward of a
    parameter that is itself guaranteed. Definitions only ever called
    indirectly (their name passed as a parameter value, e.g.
    DialogCustom_Favourites' include_list) have no direct callers to check
    and are out of scope here."""

    PARAM = re.compile(r"^\$PARAM\[([^\]]+)\]$")

    def _params(self, node):
        values = {}
        for child in node:
            if child.tag == "param" and child.get("name"):
                value = child.get("value") or child.get("default") or child.text or ""
                values[child.get("name")] = value.strip()
        return values

    def _parents(self, root):
        return {child: parent for parent in root.iter() for child in parent}

    def _owner(self, node, parents):
        owner = parents.get(node)
        while owner is not None and not (owner.tag == "include" and owner.get("name")):
            owner = parents.get(owner)
        return owner

    def _calls(self, name):
        for path in _skin_files():
            root = _tree(path)
            parents = self._parents(root)
            for node in root.iter("include"):
                if node.get("content") == name or (node.text or "").strip() == name:
                    yield node, parents

    def _guaranteed(self, name, param, definitions, seen=()):
        if (name, param) in seen:
            return True
        seen = seen + ((name, param),)
        default = self._params(definitions[name]).get(param)
        default_ok = bool(default) and not self.PARAM.match(default)
        calls = list(self._calls(name))
        if not calls:
            return True
        for call, parents in calls:
            supplied = self._params(call)
            if param not in supplied:
                if not default_ok:
                    return False
                continue
            value = supplied[param]
            if not value:
                return False
            forward = self.PARAM.match(value)
            if not forward:
                continue
            enclosing = self._owner(call, parents)
            if enclosing is None:
                if not default_ok:
                    return False
                continue
            if not (default_ok or self._guaranteed(
                    enclosing.get("name"), forward.group(1), definitions, seen)):
                return False
        return True

    def test_param_includes_never_resolve_empty(self):
        definitions = _definitions()
        checked = 0
        for path in _skin_files():
            root = _tree(path)
            parents = self._parents(root)
            for node in root.iter("include"):
                if node.get("name"):
                    continue
                match = self.PARAM.match((node.get("content") or "").strip()) or \
                    self.PARAM.match((node.text or "").strip())
                if not match:
                    continue
                owner = self._owner(node, parents)
                with self.subTest(file=path.name, param=match.group(1),
                                  owner=owner.get("name") if owner is not None else None):
                    self.assertIsNotNone(owner, "parameter include outside any definition")
                    checked += 1
                    self.assertTrue(
                        self._guaranteed(owner.get("name"), match.group(1), definitions),
                        f"{match.group(1)} can resolve empty in {owner.get('name')}")
        self.assertGreaterEqual(checked, 10)

    def test_include_empty_stub_registers_but_inserts_nothing(self):
        parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
        root = ET.parse(SKIN / "Includes_Objects.xml", parser=parser).getroot()
        stub = next(n for n in root.findall("include") if n.get("name") == "Include_Empty")
        children = list(stub)
        self.assertTrue(children)
        self.assertTrue(all(c.tag is ET.Comment for c in children))
        self.assertFalse((stub.text or "").strip())


if __name__ == "__main__":
    unittest.main()

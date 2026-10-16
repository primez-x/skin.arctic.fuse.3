"""Skin-caused Kodi log errors seen on CoreELEC boxes: generated includes missing on the
first load after an install or update, and resource:// image add-ons that are installed
but disabled."""

import re
import unittest
from collections import Counter
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


class SkinDependencyAndOverlayTests(unittest.TestCase):
    def test_dependencies_page_covers_every_non_kodi_import(self):
        addon = ET.parse(SKIN.parent / "addon.xml").getroot()
        imports = {n.get("addon") for n in addon.findall("./requires/import")
                   if not n.get("addon").startswith(("xbmc.", "kodi."))}
        page = _tree(SKIN / "Includes_SkinSettings.xml").find(
            "./include[@name='SkinSettings_Items_Dependecies']")
        buttons = page.findall("./include[@content='Settings_Button']")
        labels = {n.findtext("label"): n for n in buttons}
        self.assertEqual(set(), imports - labels.keys())
        ids = [n.findtext("param[@name='id']") for n in buttons]
        self.assertEqual(len(ids), len(set(ids)))
        for addon_id in imports:
            button = labels[addon_id]
            self.assertIn(f"EnableAddon({addon_id})", [n.text for n in button.findall("onclick")])
            self.assertIn(f"System.AddonIsEnabled({addon_id})", button.findtext("selected"))

    def test_optional_node_icon_packs_require_enabled_addons_and_have_a_fallback(self):
        variable = _tree(SKIN / "Includes_Images.xml").find("./variable[@name='Image_OtherIcon']")
        for value in variable.findall("value"):
            for addon_id in ResourceImageAddonTests.PATH.findall(value.text or ""):
                self.assertIn(f"System.AddonIsEnabled({addon_id})", value.get("condition", ""))
        fallback = next((n for n in variable.findall("value") if n.get("condition") is None), None)
        self.assertIsNotNone(fallback)
        self.assertTrue((SKIN.parent / "media" / fallback.text).is_file())

    def test_seekbar_uses_existing_fullscreen_overlays(self):
        seekbar = _tree(SKIN / "DialogSeekBar.xml")
        condition = " ".join(n.text or "" for n in seekbar.findall("visible"))
        ids = {int(value) for value in re.findall(r"Window.IsActive\((11\d\d)\)", condition)}
        existing = {int(_tree(p).get("id")) for p in SKIN.glob("Custom_*.xml") if _tree(p).get("id")}
        self.assertEqual(set(), ids - existing)
        self.assertIn(1153, ids)
        self.assertNotIn(1151, ids)  # The passive music screen shows no seek bar or clock.
        self.assertNotIn(1155, ids)  # Next Track excludes both fullscreen players.

    def test_pvr_genre_colours_use_backend_codes_without_text_scans(self):
        variable = _tree(SKIN / "Includes_Views_PVR.xml").find("./variable[@name='PVR_GenreType']")
        values = variable.findall("value")
        self.assertLessEqual(len(values), 3)
        self.assertNotIn("String.Contains", ET.tostring(variable, encoding="unicode"))
        self.assertEqual("0", values[0].text)
        self.assertEqual("Skin.HasSetting(PVR.DisableGenreColours)", values[0].get("condition"))
        self.assertIn("!String.IsEmpty(ListItem.Property(GenreType))", values[1].get("condition"))
        self.assertIn("!Integer.IsEqual(ListItem.Property(GenreType),256)", values[1].get("condition"))
        self.assertEqual("$INFO[ListItem.Property(GenreType)]", values[1].text)
        self.assertEqual("0", values[-1].text)
        for code in range(0, 256, 16):
            self.assertTrue((SKIN.parent / "media" / "pvr" / "genre" / f"{code}.png").is_file())
        layouts = _tree(SKIN / "Includes_Layouts.xml")
        textures = [n for n in layouts.iter("texture") if "PVR_GenreType" in (n.text or "")]
        self.assertTrue(textures)
        self.assertTrue(all(n.get("fallback") == "pvr/genre/0.png" for n in textures))


class IncludeReferenceTests(unittest.TestCase):
    # These families resolve names through parameters or Skin Variables templates.
    DYNAMIC_PREFIXES = (
        "defs_dialog_", "DialogKeyboard_Row_Buttons_", "Dimension_DialogMiniMenu_",
        "OSD_CastInfo_HintText_DirectionLabel_", "Object_Indicator_Visible_",
        "Object_NextItem_", "Object_SearchLetter_Click_", "SeasonalThemes_Animation_",
        "Settings_Button_", "View_Line_Divider_", "Widget_Busy_BlankItems__",
    )

    @staticmethod
    def unreferenced():
        references = Counter()
        root = SKIN.parent
        paths = list(SKIN.glob("*.xml")) + list((root / "shortcuts").rglob("*")) + list(root.glob("*.py"))
        for path in paths:
            if not path.is_file() or path.suffix not in {".xml", ".json", ".py", ".xmltemplate"}:
                continue
            source = re.sub(r'<include\s+name="[^"]+"', '<include', path.read_text(encoding="utf-8"))
            tokens = re.findall(r"[\w]+(?:-[\w]+)*", source)
            references.update(tokens)
            # Widget placeholder names contain the row name after a double underscore.
            references.update(token.split("__", 1)[1] for token in tokens if "__" in token)
        return {name for name in _definitions()
                if not references[name] and not name.startswith(IncludeReferenceTests.DYNAMIC_PREFIXES)}

    def test_every_include_has_a_literal_or_constructed_reference(self):
        self.assertEqual(set(), self.unreferenced())


if __name__ == "__main__":
    unittest.main()

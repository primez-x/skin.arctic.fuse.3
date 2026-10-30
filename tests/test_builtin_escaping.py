"""Free text in builtin parameters is escaped.

Kodi splits builtin parameters at every comma outside quotes and brackets.
On 2026-10-30 a YouTube title with a comma split SetProperty(BaseID,...) in
the video information dialog, and Kodi read the rest of the title as a
window name. $ESCINFO and $ESCVAR quote a value, so a comma stays inside it.
"""

import re
import unittest
from pathlib import Path


SKIN = Path(__file__).resolve().parents[1] / "1080i"
ACTION = re.compile(
    r"<(onload|onunload|onclick|onfocus|onunfocus|onback|onup|ondown|onleft|onright|oninfo)"
    r"(?:\s[^>]*)?>(.*?)</\1>", re.S)
VARIABLE = re.compile(r'<variable name="([^"]+)"[^>]*>(.*?)</variable>', re.S)
QUOTED = re.compile(r'"[^"]*"')
# Info labels that hold titles, names or paths, which can contain a comma.
FREE_TEXT = re.compile(
    r"\$INFO\[[^\]]*(?:Label|Title|Plot|Tagline|Album|Artist|Genre|Studio|Director|Writer"
    r"|FolderPath|FileNameAndPath|FolderName|PluginCategory|Property\((?:BaseID|CurrentID)\))")
VAR = re.compile(r"\$VAR\[([^\],]+)")


def _texts():
    return {path.name: path.read_text(encoding="utf-8") for path in sorted(SKIN.glob("*.xml"))}


class BuiltinEscapingTests(unittest.TestCase):
    def test_builtins_quote_free_text(self):
        texts = _texts()
        free_variables = set(
            name for text in texts.values() for name, body in VARIABLE.findall(text)
            if FREE_TEXT.search(body))
        found = []
        for name, text in texts.items():
            for match in ACTION.finditer(text):
                # A builtin that opens a plugin URL in quotes keeps commas inside the quotes.
                body = QUOTED.sub('""', match.group(2))
                if "(" not in body:
                    continue
                unescaped = FREE_TEXT.findall(body) + [
                    variable for variable in VAR.findall(body) if variable in free_variables]
                if unescaped:
                    line = text.count("\n", 0, match.start()) + 1
                    found.append("%s:%d %s" % (name, line, match.group(2).strip()[:120]))
        self.assertEqual([], found)


if __name__ == "__main__":
    unittest.main()

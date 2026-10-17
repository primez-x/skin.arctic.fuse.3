"""Remaining time for the Resume button on the video Info page.

Kodi has no info label for the time left on a part-watched item, and skin conditions cannot subtract.
While the Info page is open, this keeps Home properties with the time left on the page's item and on
the focused episode of the Episodes row. Each value is keyed by its DBType and DBID, so the skin shows a
value only while its own item is the one the button plays.
"""

import json
import math

import xbmc
import xbmcgui

POLL_SECONDS = 0.25
# Home property -> list item it describes
TARGETS = (
    ("DialogInfo.Remaining", "ListItem"),
    ("DialogInfo.EpisodeRemaining", "Container(5019).ListItem"),
)
DETAILS = {
    "movie": ("VideoLibrary.GetMovieDetails", "movieid", "moviedetails"),
    "episode": ("VideoLibrary.GetEpisodeDetails", "episodeid", "episodedetails"),
}


def format_remaining(position, total):
    """Time left in the compact duration style ("1h 26m"); empty unless the item is part-watched."""
    seconds = total - position
    if position <= 0 or seconds <= 0:
        return ""
    # Round up: a few seconds left still reads 1m, never 0m
    hours, minutes = divmod(math.ceil(seconds / 60), 60)
    if hours and minutes:
        return f"{hours}h {minutes}m"
    return f"{hours}h" if hours else f"{minutes}m"


def _resume_point(dbtype, dbid):
    method, id_key, result_key = DETAILS[dbtype]
    payload = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": {id_key: int(dbid), "properties": ["resume"]}}
    )
    try:
        resume = json.loads(xbmc.executeJSONRPC(payload))["result"][result_key]["resume"]
        return float(resume.get("position") or 0), float(resume.get("total") or 0)
    except (KeyError, TypeError, ValueError):
        return 0.0, 0.0


class Watcher:
    def __init__(self, template):
        self.template = template
        self.home = xbmcgui.Window(10000)
        self.keys = {}

    def poll(self):
        if not xbmc.getCondVisibility("Window.IsVisible(movieinformation)"):
            # Playback can move the resume point while the page is closed, so a reopen recomputes
            if self.keys:
                for prop, _ in TARGETS:
                    for name in (prop, f"{prop}.DBType", f"{prop}.DBID"):
                        self.home.clearProperty(name)
                self.keys = {}
            return
        for prop, listitem in TARGETS:
            dbtype = xbmc.getInfoLabel(f"{listitem}.DBType")
            dbid = xbmc.getInfoLabel(f"{listitem}.DBID")
            if self.keys.get(prop) == (dbtype, dbid):
                continue
            self.keys[prop] = (dbtype, dbid)
            text = ""
            if dbtype in DETAILS and dbid.isdigit():
                remaining = format_remaining(*_resume_point(dbtype, dbid))
                text = self.template.format(remaining) if remaining else ""
            self.home.setProperty(prop, text)
            self.home.setProperty(f"{prop}.DBType", dbtype)
            self.home.setProperty(f"{prop}.DBID", dbid)


def watch(monitor, template):
    watcher = Watcher(template)
    while not monitor.waitForAbort(POLL_SECONDS):
        watcher.poll()

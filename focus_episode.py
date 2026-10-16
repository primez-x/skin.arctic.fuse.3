import json
import sys

import xbmc

SEASONS = 5018
EPISODES = 5019
BUSY = "TVFocus.Busy"
TIMEOUT = 10


def rpc(method, params):
    response = json.loads(xbmc.executeJSONRPC(json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})))
    if "result" not in response:
        raise ValueError(f"{method} failed: {response}")
    return response["result"]


def target_episode(dbtype, dbid, tvshowid, season):
    """Return (season, episode DBID): the opened episode, else the first unwatched one."""
    if dbtype == "episode":
        return season, dbid
    params = {"tvshowid": tvshowid, "properties": ["season", "playcount"],
              "sort": {"method": "episode", "order": "ascending"}}
    if dbtype == "season":
        params["season"] = season
    episodes = rpc("VideoLibrary.GetEpisodes", params).get("episodes", [])
    episodes.sort(key=lambda item: (item["season"] == 0, item["season"]))
    if not episodes:
        return None
    pick = next((item for item in episodes if not item["playcount"]), episodes[0])
    return pick["season"], pick["episodeid"]


def wait_for(monitor, condition):
    """Wait while the info dialog stays open; give up after TIMEOUT seconds."""
    for _ in range(TIMEOUT * 10):
        if not xbmc.getCondVisibility("Window.IsVisible(movieinformation)"):
            return False
        if condition():
            return True
        if monitor.waitForAbort(0.1):
            return False
    return False


def loaded(container):
    return xbmc.getCondVisibility(f"!Container({container}).IsUpdating + Integer.IsGreater(Container({container}).NumItems,0)")


def index_of(container, label, value):
    count = int(xbmc.getInfoLabel(f"Container({container}).NumItems") or 0)
    return next((index for index in range(count)
                 if xbmc.getInfoLabel(f"Container({container}).ListItemAbsolute({index}).{label}") == value), None)


def focus_episode(dbtype, dbid, tvshowid, season):
    target = target_episode(dbtype, int(dbid), int(tvshowid or dbid), int(season or -1))
    if not target:
        return
    season, episode = str(target[0]), str(target[1])
    monitor = xbmc.Monitor()
    if not wait_for(monitor, lambda: loaded(SEASONS)):
        return
    # Only take focus from the initial Play button: never move a user who has started to navigate.
    if not xbmc.getCondVisibility("Control.HasFocus(4001)"):
        return
    position = index_of(SEASONS, "Season", season)
    if position is None:
        return
    xbmc.executebuiltin(f"SetProperty({BUSY},1,movieinformation)")
    try:
        xbmc.executebuiltin(f"SetFocus({SEASONS},{position},absolute)", True)
        if not wait_for(monitor, lambda: loaded(EPISODES) and xbmc.getInfoLabel(
                f"Container({EPISODES}).ListItemAbsolute(0).Season") == season):
            xbmc.executebuiltin("SetFocus(4001)")
            return
        position = index_of(EPISODES, "DBID", episode)
        xbmc.executebuiltin(f"SetFocus({EPISODES},{position or 0},absolute)", True)
    finally:
        xbmc.executebuiltin(f"ClearProperty({BUSY},movieinformation)")


if __name__ == "__main__":
    try:
        focus_episode(*(sys.argv[1:] + [""] * 4)[:4])
    except ValueError as error:
        xbmc.log(f"skin.arctic.fuse.3: {error}", xbmc.LOGERROR)

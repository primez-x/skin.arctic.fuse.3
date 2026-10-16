import json
import sys

import xbmc

SEASONS = 5018
EPISODES = 5019
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


def label(info):
    return xbmc.getInfoLabel(info)


def loaded(container, tvshowid):
    """The row has finished loading this show's items, not the previous page's."""
    return xbmc.getCondVisibility(
        f"!Container({container}).IsUpdating + Integer.IsGreater(Container({container}).NumItems,0)"
    ) and label(f"Container({container}).ListItemAbsolute(0).TvShowDBID") == tvshowid


def index_of(container, info, value):
    count = int(label(f"Container({container}).NumItems") or 0)
    return next((index for index in range(count)
                 if label(f"Container({container}).ListItemAbsolute({index}).{info}") == value), None)


def select(container, index):
    """Move the row's selection without taking focus. Return True when the item is selected."""
    current = int(label(f"Container({container}).CurrentItem") or 1) - 1
    if current == index:
        return True
    xbmc.executebuiltin(f"Control.Move({container},{index - current})", True)
    return False


def select_episode(dbtype, dbid, tvshowid, season):
    """Select the episode in the Episodes row; focus stays on the Play button."""
    tvshowid = str(int(tvshowid or dbid))
    target = target_episode(dbtype, int(dbid), int(tvshowid), int(season or -1))
    if not target:
        return
    season, episode = str(target[0]), str(target[1])
    monitor = xbmc.Monitor()
    # Both rows reload after the dialog opens, and the Episodes row reloads after a season change,
    # which resets the selection. Retry until the episode stays selected.
    for _ in range(TIMEOUT * 10):
        if not xbmc.getCondVisibility("Window.IsVisible(movieinformation)") or \
                xbmc.getCondVisibility(f"Control.HasFocus({SEASONS}) | Control.HasFocus({EPISODES})"):
            return  # The user has started to browse the rows.
        if loaded(SEASONS, tvshowid):
            position = index_of(SEASONS, "Season", season)
            if position is None:
                return
            if select(SEASONS, position) and loaded(EPISODES, tvshowid) and \
                    label(f"Container({EPISODES}).ListItemAbsolute(0).Season") == season:
                position = index_of(EPISODES, "DBID", episode)
                if position is None or select(EPISODES, position):
                    return
        if monitor.waitForAbort(0.1):
            return


if __name__ == "__main__":
    try:
        select_episode(*(sys.argv[1:] + [""] * 4)[:4])
    except ValueError as error:
        xbmc.log(f"skin.arctic.fuse.3: {error}", xbmc.LOGERROR)
    finally:
        # The details and play buttons follow the Episodes row from now on.
        xbmc.executebuiltin("SetProperty(TVSelect.Ready,1,movieinformation)")

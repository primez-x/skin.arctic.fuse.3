import json
import sys

import xbmc

METHODS = {
    "movie": ("VideoLibrary.GetMovieDetails", "VideoLibrary.SetMovieDetails", "movieid", "moviedetails"),
    "episode": ("VideoLibrary.GetEpisodeDetails", "VideoLibrary.SetEpisodeDetails", "episodeid", "episodedetails"),
}


def rpc(method, params):
    response = json.loads(xbmc.executeJSONRPC(json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})))
    if "result" not in response:
        raise ValueError(f"{method} failed: {response}")
    return response["result"]


def toggle_watched(dbtype, dbid):
    """Toggle the watched state of a library movie or episode, clearing any resume point."""
    get_method, set_method, id_param, result_key = METHODS[dbtype]
    dbid = int(dbid)
    details = rpc(get_method, {id_param: dbid, "properties": ["playcount"]}).get(result_key) or {}
    playcount = 0 if details.get("playcount") else 1
    rpc(set_method, {id_param: dbid, "playcount": playcount, "resume": {"position": 0, "total": 0}})
    # The dialog item keeps its load-time playcount, so publish the new state for
    # the caption and rebuild the action list to pick it up.
    state = "watched" if playcount else "unwatched"
    xbmc.executebuiltin(f"SetProperty(WatchedToggle,{state},movieinformation)")
    xbmc.executebuiltin("Container.Refresh")


if __name__ == "__main__":
    try:
        toggle_watched(*(sys.argv[1:] + [""] * 2)[:2])
    except (KeyError, ValueError) as error:
        xbmc.log(f"skin.arctic.fuse.3: {error}", xbmc.LOGERROR)

import json

import xbmc
import xbmcgui


def toggle_song_information():
    response = json.loads(xbmc.executeJSONRPC(json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "Settings.GetSettingValue",
        "params": {"setting": "mymusic.songthumbinvis"},
    })))
    value = response.get("result", {}).get("value")
    if not isinstance(value, bool):
        raise ValueError(f"Song information preference is unavailable: {response}")

    response = json.loads(xbmc.executeJSONRPC(json.dumps({
        "jsonrpc": "2.0", "id": 2, "method": "Settings.SetSettingValue",
        "params": {"setting": "mymusic.songthumbinvis", "value": not value},
    })))
    if response.get("result") is not True:
        raise ValueError(f"Song information preference was rejected: {response}")


if __name__ == "__main__":
    try:
        toggle_song_information()
    except ValueError as error:
        xbmc.log(f"skin.arctic.fuse.3: {error}", xbmc.LOGERROR)
        xbmcgui.Dialog().notification(
            xbmc.getLocalizedString(257),
            xbmc.getLocalizedString(31994),
            icon=xbmcgui.NOTIFICATION_ERROR,
        )

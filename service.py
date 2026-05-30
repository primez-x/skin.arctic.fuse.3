import json
import os

import xbmc
import xbmcaddon
import xbmcvfs


ADDON_ID = "skin.arctic.fuse.3"
RECOVERY_FILE = "update_recovery.version"
INVALID_WINDOW_IDS = {9999, 10101}
RECOVERY_DELAY_SECONDS = 6.0
RECOVERY_SETTLE_SECONDS = 1.5


def _log(message, level=xbmc.LOGINFO):
    xbmc.log(f"{ADDON_ID}:update_recovery: {message}", level=level)


def _addon_version():
    return xbmcaddon.Addon(ADDON_ID).getAddonInfo("version")


def _profile_path():
    path = xbmcvfs.translatePath(f"special://profile/addon_data/{ADDON_ID}/")
    os.makedirs(path, exist_ok=True)
    return path


def _version_file_path():
    return os.path.join(_profile_path(), RECOVERY_FILE)


def _read_recovered_version():
    try:
        with open(_version_file_path(), "r", encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def _write_recovered_version(version):
    with open(_version_file_path(), "w", encoding="utf-8") as handle:
        handle.write(version)


def _current_window_ids():
    try:
        payload = json.dumps(
            {
                "jsonrpc": "2.0",
                "method": "GUI.GetProperties",
                "params": {"properties": ["currentwindow"]},
                "id": 1,
            }
        )
        response = json.loads(xbmc.executeJSONRPC(payload))
        window_id = response.get("result", {}).get("currentwindow", {}).get("id", 0)
        return int(window_id or 0), 0
    except (TypeError, ValueError, KeyError):
        return 9999, 0


def _needs_window_recovery():
    window_id, dialog_id = _current_window_ids()
    return window_id in INVALID_WINDOW_IDS or dialog_id in INVALID_WINDOW_IDS


def _run_recovery(monitor):
    _log("Running post-update skin reload recovery.")
    for _ in range(3):
        xbmc.executebuiltin("Dialog.Close(all,true)")
        if monitor.waitForAbort(RECOVERY_SETTLE_SECONDS):
            return
        xbmc.executebuiltin("ActivateWindow(Home)")
        if monitor.waitForAbort(RECOVERY_SETTLE_SECONDS):
            return
        if not _needs_window_recovery():
            return
    _log("Skin reload recovery could not confirm a stable window.", xbmc.LOGWARNING)


def main():
    monitor = xbmc.Monitor()
    version = _addon_version()
    previous_version = _read_recovered_version()

    if xbmc.getSkinDir() != ADDON_ID:
        _write_recovered_version(version)
        return

    version_changed = previous_version != version
    if not version_changed and not _needs_window_recovery():
        return

    if monitor.waitForAbort(RECOVERY_DELAY_SECONDS):
        return

    _run_recovery(monitor)
    _write_recovered_version(version)


if __name__ == "__main__":
    main()

import json
import os
import re
import shutil
import stat
import tempfile
import xml.etree.ElementTree as ET
from urllib.parse import parse_qs, urlsplit

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


SKINUSERS_FILE = "script-skinvariables-skinusers.xml"
SKINUSERS_TEMPLATE = "special://skin/shortcuts/skinvariables-skinusers.xmltemplate"
GENERATED_STANDIN = "script-skinvariables-generator-includes-.xml"
GENERATED_USER_FILE = "script-skinvariables-generator-includes-{slug}.xml"
SKIN_SETTINGS_FILE = "special://profile/addon_data/skin.arctic.fuse.3/settings.xml"
SKINVARIABLES_NODES = "special://profile/addon_data/script.skinvariables/nodes/skin.arctic.fuse.3/"
LEGACY_EXTRAS_PREFIX = "special://skin/extras"
RESOURCE_EXTRAS_PREFIX = "resource://resource.images.arctic.fuse.3/extras"
IMAGE_EXTENSIONS = {".jpg", ".png"}
MIGRATION_ROLLBACK_SUFFIX = ".before-resource-image-migration"


def _read(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
    except (OSError, UnicodeError):
        return None


def _restore_skin_user_includes():
    """Point the skin-user include at the logged-in user's generated includes again.

    Workaround: script.skinvariables writes script-skinvariables-skinusers.xml only when a
    skin user logs in, and an install or update of the skin replaces 1080i/, so a logged-in
    user would get the packaged stand-in (no menus or widgets) until the next login. This
    rewrites it exactly as the login does and, if the user's generated file is missing,
    seeds it with the default stand-ins so the include file exists; script.skinvariables
    hashes that file's content, so it still regenerates it. The durable fix is for
    script.skinvariables to rewrite the skin-user file in update_xml.
    Returns True when a file was written."""
    slug = xbmc.getInfoLabel("Skin.String(SkinVariables.SkinUser)")
    if not slug:
        return False
    template = _read(xbmcvfs.translatePath(SKINUSERS_TEMPLATE))
    if not template:
        return False
    folder = xbmcvfs.translatePath("special://skin/1080i/")
    written = False
    content = template.format(slug=slug)
    target = os.path.join(folder, SKINUSERS_FILE)
    if _read(target) != content:
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(content)
        written = True
    user_file = os.path.join(folder, GENERATED_USER_FILE.format(slug=slug))
    standin = _read(os.path.join(folder, GENERATED_STANDIN))
    if not os.path.exists(user_file) and standin is not None:
        with open(user_file, "w", encoding="utf-8") as handle:
            handle.write(standin)
        written = True
    if written:
        _log(f"Restored the skin user include for {slug}.")
    return written


def _resource_image_path(value):
    if not isinstance(value, str):
        return None
    if value == LEGACY_EXTRAS_PREFIX:
        suffix = ""
    elif value.startswith(LEGACY_EXTRAS_PREFIX + "/"):
        suffix = value[len(LEGACY_EXTRAS_PREFIX) + 1:]
    elif value == f"{RESOURCE_EXTRAS_PREFIX}/backgrounds/pink_blur.jpg":
        suffix = "backgrounds/pink_blur.jpg"
    else:
        return None

    if suffix == "backgrounds/pink_blur.jpg":
        suffix = "backgrounds/blur/pink_blur.jpg"

    target = f"{RESOURCE_EXTRAS_PREFIX}/{suffix}" if suffix else RESOURCE_EXTRAS_PREFIX
    if suffix.endswith("/") or not suffix:
        directory_target = target if target.endswith("/") else target + "/"
        return directory_target if xbmcvfs.exists(directory_target) else None
    extension = os.path.splitext(suffix)[1].lower()
    if extension in IMAGE_EXTENSIONS:
        return target if xbmcvfs.exists(target) else None
    if not extension:
        directory_target = target.rstrip("/") + "/"
        return directory_target if xbmcvfs.exists(directory_target) else None
    return None


def _read_migration_settings():
    """Return the optional settings root and a separate completion status."""
    path = xbmcvfs.translatePath(SKIN_SETTINGS_FILE)
    try:
        with open(path, "r", encoding="utf-8") as source:
            return ET.fromstring(source.read()), True
    except FileNotFoundError:
        return None, True
    except (OSError, UnicodeError, ET.ParseError) as error:
        _log(f"Could not read skin settings during profile migration: {error}", xbmc.LOGWARNING)
        return None, False


def _migrate_skin_setting_images():
    root, complete = _read_migration_settings()
    if root is None:
        return False, complete

    changed = False
    for setting in root.iter("setting"):
        setting_id = setting.get("id", "")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", setting_id):
            continue
        current = setting.get("value")
        if current is None:
            current = setting.text or ""
        replacement = _resource_image_path(current)
        if replacement is None:
            continue
        if xbmc.getInfoLabel(f"Skin.String({setting_id})") != current:
            continue
        xbmc.executebuiltin(f"Skin.SetString({setting_id},{replacement})")
        changed = True
    return changed, True


def _rewrite_saved_values(value, rewrite_value, rewrite_record=None):
    if isinstance(value, dict):
        changed = False
        rewritten = {}
        for key, child in value.items():
            rewritten_child, child_changed = _rewrite_saved_values(child, rewrite_value, rewrite_record)
            rewritten[key] = rewritten_child
            changed = changed or child_changed
        if rewrite_record:
            rewritten, record_changed = rewrite_record(value, rewritten)
            changed = changed or record_changed
        return rewritten, changed
    if isinstance(value, list):
        changed = False
        rewritten = []
        for child in value:
            rewritten_child, child_changed = _rewrite_saved_values(child, rewrite_value, rewrite_record)
            rewritten.append(rewritten_child)
            changed = changed or child_changed
        return rewritten, changed
    replacement = rewrite_value(value)
    if replacement is None:
        return value, False
    return replacement, True


def _write_json_atomically(path, value):
    folder = os.path.dirname(path)
    filename = os.path.basename(path)
    handle, temporary_path = tempfile.mkstemp(prefix=f".{filename}.", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as output:
            json.dump(value, output, ensure_ascii=False, indent=4)
            output.write("\n")
        os.replace(temporary_path, path)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)


def _migrate_saved_shortcut_values(rewrite_value, rollback_suffix, rewrite_record=None):
    """Return (changed, complete) while preserving successful sibling migrations."""
    folder = xbmcvfs.translatePath(SKINVARIABLES_NODES)
    try:
        filenames = sorted(os.listdir(folder))
    except FileNotFoundError:
        return False, True
    except OSError as error:
        _log(f"Could not read saved shortcut folder: {error}", xbmc.LOGWARNING)
        return False, False

    changed = False
    complete = True
    for filename in filenames:
        if not filename.endswith(".json"):
            continue
        path = os.path.join(folder, filename)
        try:
            if not stat.S_ISREG(os.stat(path).st_mode):
                continue
            with open(path, "r", encoding="utf-8") as source:
                saved = json.load(source)
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            _log(f"Could not read saved shortcut data {filename}: {error}", xbmc.LOGWARNING)
            complete = False
            continue

        rewritten, file_changed = _rewrite_saved_values(saved, rewrite_value, rewrite_record)
        if not file_changed:
            continue

        rollback = path + rollback_suffix
        try:
            if not os.path.exists(rollback):
                shutil.copy2(path, rollback)
            _write_json_atomically(path, rewritten)
        except OSError as error:
            _log(f"Could not migrate saved shortcut data {filename}: {error}", xbmc.LOGWARNING)
            complete = False
            continue
        changed = True
    return changed, complete


def _migrate_saved_shortcut_images():
    return _migrate_saved_shortcut_values(_resource_image_path, MIGRATION_ROLLBACK_SUFFIX)


def _migrate_legacy_image_paths():
    settings_changed, settings_complete = _migrate_skin_setting_images()
    shortcut_data_changed, shortcuts_complete = _migrate_saved_shortcut_images()
    if settings_changed or shortcut_data_changed:
        _log("Migrated legacy skin image paths to the resource add-on.")
    return settings_changed or shortcut_data_changed, settings_complete and shortcuts_complete


PLEX_LISTS_PATH = "plugin://plugin.video.plexkodiconnect/?mode=discover_lists"
PLEX_TRENDING_PATH = "plugin://plugin.video.plexkodiconnect/?mode=discover_hub&hub_id=trending-for-you"
TRAKT_LIST_ROUTES = {
    "trakt_searchlists", "trakt_trendinglists", "trakt_popularlists", "trakt_likedlists",
    "trakt_mylists", "trakt_inlists", "trakt_userslists", "trakt_userlist",
    "random_trendinglists", "random_popularlists", "random_likedlists", "random_mylists",
}
SHORTCUT_ACTION = re.compile(
    r"((?:ActivateWindow\([^,()]+,)|(?:RunPlugin\())(.+?)(,return\)|\))", re.IGNORECASE)


def _plex_source_path(value):
    if not isinstance(value, str):
        return None
    if value in {"DefaultSearch-TMDBListsTrakt", "DefaultSearch-PlexLists"}:
        return PLEX_LISTS_PATH
    if len(value) > 1 and value[0] in {'"', "'"} and value[-1] == value[0]:
        path = _plex_source_path(value[1:-1])
        return value[0] + path + value[-1] if path else None
    action = SHORTCUT_ACTION.fullmatch(value)
    if action:
        path = _plex_source_path(action[2])
        return action[1] + path + action[3] if path else None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if parsed.scheme != "plugin" or parsed.netloc != "plugin.video.themoviedb.helper" or parsed.path not in {"", "/"}:
        return None
    info = parse_qs(parsed.query).get("info", [])
    if len(info) != 1:
        return None
    if info[0] in TRAKT_LIST_ROUTES:
        return PLEX_LISTS_PATH
    if info[0] in {"trakt_becauseyouwatched", "trakt_becausemostwatched"}:
        return PLEX_TRENDING_PATH
    return None


def _plex_source_label(path):
    action = SHORTCUT_ACTION.fullmatch(path)
    if action:
        return _plex_source_label(action[2])
    if len(path) > 1 and path[0] in {'"', "'"} and path[-1] == path[0]:
        return _plex_source_label(path[1:-1])
    return "Plex: Trending for You" if path == PLEX_TRENDING_PATH else "My Plex Lists"


def _rewrite_plex_shortcut_record(original, rewritten):
    changed = False
    for key in ("path", "widget_path"):
        replacement = _plex_source_path(original.get(key))
        if replacement is None:
            continue
        for label_key in ("label", "name", "widget_label"):
            if label_key in original:
                rewritten[label_key] = _plex_source_label(replacement)
                changed = True
    return rewritten, changed


def _migrate_plex_skin_settings():
    root, complete = _read_migration_settings()
    if root is None:
        return False, complete
    settings = {node.get("id", "").lower(): node for node in root.iter("setting")}
    changed = False
    for normalized_id, node in settings.items():
        if node.get("type", "string") != "string":
            continue
        setting_id = node.get("id")
        if not setting_id or not re.fullmatch(r"[A-Za-z0-9_.-]+", setting_id):
            continue
        current = xbmc.getInfoLabel(f"Skin.String({setting_id})")
        replacement = None
        if re.fullmatch(r"customrating\.(movies|tvshows)\.item0[123]", normalized_id) and current == "Trakt":
            replacement = "Plex"
        elif normalized_id == "homeswitcher.1106.upnextmode" and current == "trakt_calendar":
            replacement = "library_nextaired"
        else:
            replacement = _plex_source_path(current)
        if replacement is None:
            continue
        xbmc.executebuiltin(f"Skin.SetString({setting_id},{replacement})")
        if normalized_id.endswith(".path"):
            label = settings.get(normalized_id[:-5] + ".label")
            if label is not None and label.get("type", "string") == "string":
                label_id = label.get("id")
                xbmc.executebuiltin(f"Skin.SetString({label_id},{_plex_source_label(replacement)})")
        changed = True
    if xbmc.getInfoLabel("Skin.String(Migration.PlexBadges)") != "1":
        badge_changed = False
        for suffix in ("Watchlist", "Favourites"):
            old, new = f"Indicator.Trakt{suffix}", f"Indicator.Plex{suffix}"
            saved = settings.get(old.lower())
            if saved is None:
                continue
            enabled = saved.get("value", saved.text or "") == "true"
            # Skin conditions create new false settings before the first migration.
            xbmc.executebuiltin(f"Skin.SetBool({new})" if enabled else f"Skin.Reset({new})")
            xbmc.executebuiltin(f"Skin.Reset({old})")
            badge_changed = True
        if badge_changed:
            xbmc.executebuiltin("Skin.SetString(Migration.PlexBadges,1)")
            changed = True
    return changed, True


def _migrate_plex_sources():
    settings_changed, settings_complete = _migrate_plex_skin_settings()
    shortcuts_changed, shortcuts_complete = _migrate_saved_shortcut_values(
        _plex_source_path, ".before-plex-source-migration", _rewrite_plex_shortcut_record)
    if shortcuts_changed:
        xbmc.executebuiltin("ClearProperty(Shortcuts.Checked.Version,Home)")
    if settings_changed or shortcuts_changed:
        _log("Migrated legacy Trakt sources to Plex.")
    return settings_changed or shortcuts_changed, settings_complete and shortcuts_complete


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


def _is_playing():
    return xbmc.getCondVisibility("Player.HasMedia | Window.IsActive(fullscreenvideo)")


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
        return

    version_changed = previous_version != version
    migrations_complete = True
    if version_changed:
        _, images_complete = _migrate_legacy_image_paths()
        _, plex_complete = _migrate_plex_sources()
        migrations_complete = images_complete and plex_complete
        # Before script.skinvariables regenerates and reloads the skin, so that reload
        # picks the user's includes up (no reload of our own: a version change alone must not
        # reset the GUI, see below)
        _restore_skin_user_includes()
    if not version_changed and not _needs_window_recovery():
        return

    if monitor.waitForAbort(RECOVERY_DELAY_SECONDS):
        return

    # A version change alone is not a reason to reset the GUI: auto-updates
    # land in the background, often mid-playback or during startup windows.
    # Only recover when the skin reload actually left an invalid window.
    if _needs_window_recovery() and not _is_playing():
        _run_recovery(monitor)
    if migrations_complete:
        _write_recovered_version(version)


if __name__ == "__main__":
    main()

"""Details the video Info page cannot compose from info labels.

Kodi has no info label for the time left on a part-watched item, skin conditions cannot subtract, and
stream details come as raw codes ("eac3", 6 channels, "eng"). While the Info page is open, this keeps
Home properties with the time left and the stream chip labels of the page's item (DialogInfo.Item) and
of the focused episode of the Episodes row (DialogInfo.Episode). Each set is keyed by its DBType and
DBID, so the skin shows a value only while its own item is the one on the page.
"""

import json
import math

import xbmc
import xbmcgui

POLL_SECONDS = 0.25
# Home property prefix -> list item it describes
TARGETS = (
    ("DialogInfo.Item", "ListItem"),
    ("DialogInfo.Episode", "Container(5019).ListItem"),
)
FIELDS = ("Remaining", "Video", "Audio", "Subtitles", "DBType", "DBID")
DETAILS = {
    "movie": ("VideoLibrary.GetMovieDetails", "movieid", "moviedetails"),
    "episode": ("VideoLibrary.GetEpisodeDetails", "episodeid", "episodedetails"),
}
HDR_NAMES = {"dolbyvision": "Dolby Vision", "hdr10": "HDR10", "hdr10plus": "HDR10+", "hlg": "HLG"}
CODEC_NAMES = {
    "truehd": "TrueHD",
    "eac3": "EAC3",
    "ac3": "AC3",
    "dca": "DTS",
    "dts": "DTS",
    "dtshd_ma": "DTS-HD MA",
    "dtshd_hra": "DTS-HD HRA",
    "opus": "Opus",
    "vorbis": "Vorbis",
}
CHANNEL_NAMES = {1: "Mono", 2: "Stereo"}
SUBTITLES_STRING = 287
AUDIO_LANGUAGE_RULES = ("", "original", "default", "mediadefault")


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


def _resolution(width, height):
    # The bands of Kodi's CStreamDetails::VideoDimsToResolutionDescription
    if not width or not height:
        return ""
    if width <= 1024 and height <= 576:
        return "SD"
    if width <= 1280 and height <= 962:
        return "720p"
    if width <= 1920 and height <= 1440:
        return "1080p"
    if width <= 4096 and height <= 3072:
        return "4K"
    return "8K"


def format_video(streams):
    """"4K • Dolby Vision": resolution, then the HDR format joined as one compound value."""
    if not streams:
        return ""
    stream = streams[0]
    resolution = _resolution(stream.get("width") or 0, stream.get("height") or 0)
    hdr = HDR_NAMES.get(stream.get("hdrtype") or "", "")
    return " • ".join(part for part in (resolution, hdr) if part) if resolution else ""


def _language(code):
    return xbmc.convertLanguage(code, xbmc.ENGLISH_NAME) if code else ""


def _audio_stream(streams, preferred):
    # Kodi plays the preferred language when the file has the language, so the chip names that stream.
    # Among the candidates, the most channels win, as in Kodi's CStreamDetails best audio stream.
    candidates = [s for s in streams if preferred and _language(s.get("language") or "") == preferred]
    return max(candidates or streams, key=lambda s: s.get("channels") or 0)


def format_audio(streams, preferred=""):
    """"English (EAC3 5.1)" for the stream Kodi plays; codec and channels alone without a language."""
    if not streams:
        return ""
    stream = _audio_stream(streams, preferred)
    codec = stream.get("codec") or ""
    channels = stream.get("channels") or 0
    layout = CHANNEL_NAMES.get(channels, f"{channels - 1}.1" if channels > 2 else "")
    sound = " ".join(part for part in (CODEC_NAMES.get(codec, codec.upper()), layout) if part)
    language = _language(stream.get("language") or "")
    return f"{language} ({sound})" if language and sound else language or sound


def format_subtitles(streams):
    """Available subtitles ("English +2"). Kodi picks the stream at playback, so this never claims one."""
    if not streams:
        return ""
    first = _language(streams[0].get("language") or "") or xbmc.getLocalizedString(SUBTITLES_STRING)
    return f"{first} +{len(streams) - 1}" if len(streams) > 1 else first


def _rpc(method, params, result_key, default):
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    try:
        return json.loads(xbmc.executeJSONRPC(payload))["result"][result_key]
    except (KeyError, TypeError, ValueError):
        return default


def _details(dbtype, dbid):
    method, id_key, result_key = DETAILS[dbtype]
    return _rpc(method, {id_key: int(dbid), "properties": ["resume", "streamdetails"]}, result_key, {})


def _preferred_audio_language():
    # A language name, or a rule such as "original" or "mediadefault" that names no language
    value = _rpc("Settings.GetSettingValue", {"setting": "locale.audiolanguage"}, "value", "")
    return value if value not in AUDIO_LANGUAGE_RULES else ""


def _values(dbtype, dbid, template):
    values = dict.fromkeys(("Remaining", "Video", "Audio", "Subtitles"), "")
    if dbtype not in DETAILS or not dbid.isdigit():
        return values
    details = _details(dbtype, dbid)
    resume = details.get("resume") or {}
    remaining = format_remaining(float(resume.get("position") or 0), float(resume.get("total") or 0))
    streams = details.get("streamdetails") or {}
    values.update(
        Remaining=template.format(remaining) if remaining else "",
        Video=format_video(streams.get("video") or []),
        Audio=format_audio(streams.get("audio") or [], _preferred_audio_language()),
        Subtitles=format_subtitles(streams.get("subtitle") or []),
    )
    return values


class Watcher:
    def __init__(self, template):
        self.template = template
        self.home = xbmcgui.Window(10000)
        self.keys = {}

    def poll(self):
        if not xbmc.getCondVisibility("Window.IsVisible(movieinformation)"):
            # Playback can move the resume point while the page is closed, so a reopen recomputes
            if self.keys:
                for prefix, _ in TARGETS:
                    for field in FIELDS:
                        self.home.clearProperty(f"{prefix}.{field}")
                self.keys = {}
            return
        for prefix, listitem in TARGETS:
            dbtype = xbmc.getInfoLabel(f"{listitem}.DBType")
            dbid = xbmc.getInfoLabel(f"{listitem}.DBID")
            if self.keys.get(prefix) == (dbtype, dbid):
                continue
            self.keys[prefix] = (dbtype, dbid)
            values = _values(dbtype, dbid, self.template)
            values.update(DBType=dbtype, DBID=dbid)
            for field in FIELDS:
                self.home.setProperty(f"{prefix}.{field}", values[field])


def watch(monitor, template):
    watcher = Watcher(template)
    while not monitor.waitForAbort(POLL_SECONDS):
        watcher.poll()

"""Move a media view to the next or previous letter group from the A-Z strip.

All titles that do not start with A-Z form one "#" group, as on the strip. The
first item of the target group is placed on the top row (or the left edge of a
horizontal view): select the last item first, then the target, so the view
scrolls back up to the target.

Arguments: next|prev, the view container id, the strip control id.
"""
import sys

import xbmc

BUSY = "LetterJump.Busy"


def letter(index):
    value = xbmc.getInfoLabel(f"Container.ListItemAbsolute({index}).SortLetter").upper()
    return value if len(value) == 1 and "A" <= value <= "Z" else "#"


def group_start(index):
    group = letter(index)
    while index > 0 and letter(index - 1) == group:
        index -= 1
    return index


def target_index(direction, current, last, first):
    if direction == "next":
        group = letter(current)
        index = current + 1
        while index <= last and letter(index) == group:
            index += 1
        return index if index <= last else current
    start = group_start(current)
    if start < current:
        return start
    return group_start(start - 1) if start > first else current


def main(direction, view, strip):
    if not view.isdigit() or not xbmc.getCondVisibility(f"Control.IsVisible({view})"):
        return
    count = int(xbmc.getInfoLabel("Container.NumItems") or 0)
    if count < 2:
        return
    # A parent folder item sits before the counted items.
    first = 1 if xbmc.getCondVisibility("Container.ListItemAbsolute(0).IsParentFolder") else 0
    last = first + count - 1
    current = first + int(xbmc.getInfoLabel("Container.CurrentItem") or 1) - 1
    target = target_index(direction, current, last, first)
    if target == current:
        return
    xbmc.executebuiltin(f"SetFocus({view},{last},absolute)")
    xbmc.executebuiltin(f"SetFocus({view},{target},absolute)")
    xbmc.executebuiltin(f"SetFocus({strip})")


if __name__ == "__main__":
    # The strip sets the busy flag before the script starts, so a held key cannot stack runs.
    try:
        main(*(sys.argv[1:] + [""] * 3)[:3])
        xbmc.sleep(50)
    finally:
        xbmc.executebuiltin(f"ClearProperty({BUSY},Home)")

# skin.arctic.fuse.3 — Design Principles & Build Guide

Reverse-engineered from the upstream skin (jurialmunkey/skin.arctic.fuse.3) on 2026-06-19.
These are the rules the skin enforces. New views/panels must match them or the upstream
maintainer will reject them (see rejected PR #285: "breaks spacing requirements, consistency
in info displays, labeling style").

Target runtime: **CoreELEC 21.3 (Kodi Omega)**. Resolution baseline **1080i** (`1080i/`).

---

## 1. Skin Design Principles

### 1.1 Spacing (the system that was violated)

Two spacing mechanisms, both mandatory:

**A. Master padding = `view_pad` (80).** Every content margin, info-panel left edge,
furniture-bar inset, and dialog bound uses the constant `view_pad` (`Includes_Constants.xml`).
`view_bar` (40) is exactly half. Never hard-code `80`/`40` — use the constants. `view_pad` is
**never** overridden by aspect-ratio variants.

**B. Grid rhythm via paired `itemlayout_*` / `item_*` constants, not `<itemgap>`.**
Every grid view defines `view_<type>_itemlayout_w/h` (the cell) and `view_<type>_item_w/h`
(the visible item). The difference **is the gap**. For every view type this gap is **40** in
both axes — the skin's canonical inter-item rhythm. `poster_wall` is the one exception
(28×45) to fit extra columns. `<itemgap>` is only for stacking controls inside one column.

Canonical gap vocabulary (from real `<itemgap>` usage): `0, 8, 10, 12, 15, 20, 25, 37, 40, 80`.
- `10` — tight inline rows (info badge lines, keyboard keys)
- `20` — standard content separation (dialog sections, list rows)
- `40` — section separation (widget labels, category menus)
- `80` — structural (master padding)

**C. Aspect-ratio variants only touch width-dependent values.** `Includes_Constants_<aspect>.xml`
overrides `*_movement` (columns per page), full-width cell sizes, and dialog panel widths.
Structural paddings, vertical positions, gaps, and the 40px rhythm are **never** aspect-overridden.

### 1.2 Info display consistency (the system that was violated)

There is **one** canonical detail/info panel composite: **`Info_Panel`** (`Includes_Info.xml`).
It is used by every row view, wall view, combined view, hub, PVR guide, and playlist. It renders,
inside a vertical `grouplist` (`itemgap=0`, `top=-20`, `left=-40`, 20px spacer), in this order:

1. **`Info_Title`** — clearlogo chain → TVShowTitle → Artist → Title → Label. `font_title_midi`,
   `<colordiffuse>_100`. Params: `left` (40), `width` (`info_title_w`=640), `listitem`, `colordiffuse`.
2. **`Info_Line`** — horizontal grouplist (`itemgap=10`) of: resolution pill, HDR pill, audio-channels
   pill, star rating(s), then **dot-divider meta labels** (`Info_Line_Label`): Premiered, MPAA,
   Duration (movies/episodes), Year (albums/songs), plus actor/PVR fields. Height 80.
3. **`Info_Plot`** — plot body (+ optional plotline: tagline/genre/director). Params: `width`,
   `height` (default 120), `listitem`, `colordiffuse`, `use_textbox`.
4. **`Info_Meta`** — rating-service icons (IMDb/TMDb/Trakt/…) + misc meta.

**Rules:**
- **Do not hand-roll metadata.** If `Info_Line` / `Info_Panel` already composes it, call the
  include. Hand-assembling the pills, or concatenating `Year - MPAA - Duration` into one label,
  duplicates canonical logic and diverges on fonts/separators.
- **Separators between meta items are dot dividers** (`Info_Line_Divider`), never literal ` - `
  or `•` baked into a `$INFO` concatenation.
- **`Info_Line` already contains Premiered + MPAA + Duration for movies.** Do not add a second
  meta line for the same fields. (Movies show *Premiered*, not *Year*, by skin convention.)

### 1.3 Labeling style (the system that was violated)

- **Bare values, no `Field:` prefixes.** `Label_Genre`/`Label_Studio`/etc. (`Includes_Labels.xml`)
  are bare `$INFO[…]`. The only colon-prefixed labels in the whole skin are Audio/Subtitle languages.
- **Font → role** (Pentatonic scale, `Includes_Font.xml`):

| Role | Font | Color token |
|---|---|---|
| Detail panel title | `font_title_midi` | `main_fg_100` |
| Plotline / episode header | `font_main_bold` | `main_fg_90` |
| Meta subline (year/premiered/mpaa/duration) | `font_main` | `main_fg_70` |
| Plot body | `font_main_plot` | `main_fg_70` |
| Info-circle value (genre/studio/director) | `font_mini_bold` | `main_fg_90` |
| Counter / disabled / chrome | `font_hint_bold` | `main_fg_30` |

- **Color opacity hierarchy** (`colors/defaults.xml`, base `ededed`): `_100` primary title →
  `_90` secondary header → `_70` body/meta/plot → `_50` muted → `_30` counter/chrome → `_12`/`_06`
  dividers. Same scale for `dialog_fg` (overlays) and `panel_fg` (OSD).
- **`font_hint_bold` is forcibly UPPERCASE** and is for counters/sublabels/chrome only.
  **Never** use `font_hint_bold` + `main_fg_50` for metadata *values* like genre/studio — that
  reads as uppercase micro-chrome and is inconsistent with how metadata appears elsewhere.

### 1.4 Layout / component patterns

- **Reusable building blocks live in `Includes_Info.xml` (`Info_*`) and `Includes_Objects.xml`
  (`Object_*`).** `Includes_Layouts.xml` (`Layout_*`) are *item-layout* templates for
  `<itemlayout>`/`<focusedlayout>`, not free-standing panels.
- **Vertical panel layout = vertical `grouplist` with `itemgap=0` + a 20px spacer group at top**
  ("avoid grouplist chop"). Do not absolute-position children with hand-picked `top` offsets.
- **Horizontal label rows = horizontal `grouplist`, `itemgap=10`, `left=-20`, with a spacer group
  (`left=-10 width=20`)** before the first item — see `Info_Line`.
- **The `left=-40`/`left=40` idiom:** the panel grouplist sits at `left=-40`; its children use
  `left=40`, netting content at the panel's left edge. Preserve it when composing `Info_*` blocks.

---

## 2. View Architecture

- Views are `<include name="View_<id>_<Name>">` blocks, one per view ID. Wall views: 510 Square,
  511 Landscape, 512 Poster, 513 Circle, 514 Board, **515 Poster-Details** (this fork).
- Standard wall views (510–514) share `<include content="View_Wall_Include">` (`Includes_Views_Wall.xml`),
  which wraps the grid `panel` (id, `orientation=vertical`, `top=290`, `bottom=-40`, `pagecontrol=66`).
- **View 515 is intentionally not a `View_Wall_Include` consumer** — it renders a persistent
  left detail panel beside the grid, so it inlines the `List_Poster_Row` grid with
  `left=view_poster_wall_grid_l` (680) / `right=view_poster_wall_grid_r` (100) and overlays
  `View_Poster_Wall_Details`. This is a known, justified deviation.
- **Registration** (`Includes_Views.xml`): the view's `$EXP[Exp_View_<id>]` must be added to
  `View_Mode_Wall_Expression`. `View_Row_Info` (the standard overlay `Info_Panel`) already hides
  itself when `Control.IsVisible(515)` so the two panels don't collide.
- **Visibility** is driven by boolean expressions `Exp_View_<id>` (per-view enable toggles) and
  `Control.IsVisible(<id>)`. `viewtype label="$LOCALIZE[<id>]">wrap` sets the viewtype name.
- **Constants for this view** (`Includes_Constants.xml`):
  `view_poster_wall_details_w=540`, `view_poster_wall_grid_l=680`, `view_poster_wall_grid_r=100`,
  `view_poster_wall_item_w=200`, `_item_h=285`, `_itemlayout_w=228`, `_itemlayout_h=330`.
- **Strings** (`language/resource.language.en_gb/strings.po`): msgctxt `31558` = view label.

---

## 3. Info Panel Reference (canonical layout)

Sourced from `Info_Panel` + `Includes_DialogInfo.xml`. When building any detail panel:

```
<control type="group">                       <!-- set geometry here -->
    <left>view_pad</left> <top>view_pad</top>
    <width>…</width> <height>…</height>
    <control type="grouplist">               <!-- mirror Info_Panel exactly -->
        <top>-20</top> <left>-40</left>
        <hitrect x="0" y="0" w="0" h="0"/>
        <orientation>vertical</orientation> <itemgap>0</itemgap>
        <control type="group"><height>20</height></control>   <!-- chop spacer -->
        <include content="Info_Title">  … width=<panel> … </include>
        <include content="Info_Line">   …                   </include>
        <include content="Info_Plot">   … width=<panel> height=… … </include>
        <include content="Info_Meta">   … (optional)        </include>
    </control>
</control>
```

- If the panel is **narrower** than `info_title_w` (640) / default plot width (800), pass a smaller
  `width` to `Info_Title` and `Info_Plot` so they don't overflow into adjacent content.
- **Genre/Studio are not in `Info_Line`.** Their canonical homes are the DialogInfo circle grid
  or the plotline. If shown in a custom panel, render them as `Info_Line_Label` items
  (`font_main`, `_70`, dot divider) — the same component `Info_Line` uses — so the labeling matches.
- Prefer reusing `Info_*` blocks over writing fresh `<control type="label">` for metadata.

---

## 4. Coding Conventions

- **Constants over literals.** Reference `view_*`, `info_*`, `dialog_*` constant *names* in
  size attributes and as `<param>` values; Kodi resolves them. Define new sizes as paired
  `view_<type>_*` + negated `-view_<type>_*` constants in `Includes_Constants.xml`.
- **Parametric includes:** `<include content="X"><param name="p">v</param></include>`; consumed
  as `$PARAM[p]`. Default a param inside the include with `<param name="p">default</param>`.
- **Always provide a `<hitrect x="0" y="0" w="0" h="0"/>`** on decorative grouplists so they don't
  steal focus/click.
- **`preloaditems>0`** on view grids. `pagecontrol>66` for the scrollbar.
- **`onfocus`** on the grid: `ClearProperty(TMDbHelper.WidgetContainer)`,
  `SetProperty(Background.ShowOverlay,True,Home)`, `SetProperty(InfoPanel.FullSwitch,Wall,Home)`.
- **Validation:** `python3 -c "import xml.etree.ElementTree as ET; ET.parse('1080i/Includes_Views_Wall.xml')"`
  (Kodi resolves includes/constants at runtime; stdlib parse catches unclosed tags / bad nesting).
- **Do not edit** upstream `Includes_Info.xml`, `Includes_Constants.xml`, `Includes_Font.xml`,
  `Includes_Labels.xml`, `Includes_Objects.xml`, or `strings.po` in this fork unless unavoidable —
  extend by *calling* existing includes, not by modifying them.

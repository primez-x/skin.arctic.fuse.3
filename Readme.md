# Arctic Fuse 3

Arctic Fuse 3 is a customizable, row-based Kodi skin. Primez maintains this fork of the skin originally created by jurialmunkey.

## Install

1. Install the [Primez repository ZIP](https://primez-x.github.io/kodi.addons/repository.primez.addons/repository.primez.addons-1.0.0.zip) in Kodi with **Install from zip file**.
2. In Kodi, open **Add-ons > Install from repository > Primez Kodi Add-ons > Look and feel > Skins**.
3. Install **Arctic Fuse 3**, then select the skin under **Settings > Interface > Skin**.

Kodi installs the dependencies declared in `addon.xml` with the skin.

| Add-on dependency | Required version |
| --- | ---: |
| `xbmc.gui` | `5.17.0` |
| `xbmc.python` | `3.0.0` |
| `script.skinvariables` | `2.2.2` |
| `script.texturemaker` | `0.2.9` |
| `plugin.video.themoviedb.helper` | `6.14.3` |
| `resource.images.weathericons.white` | `0.0.1` |
| `resource.images.studios.coloured` | `0.0.1` |
| `resource.images.arctic.fuse.3` | `0.0.1` |
| `resource.font.robotocjksc` | `0.0.3` |

## Setup and use

Open **Skin Settings** to customize menus, widgets, library views, text labels, playback, and other skin behavior. Skin Variables supplies the menu and widget shortcut controls.

The **Text labels** setting offers **Off**, **Simple**, and **Detailed** choices for widget and library labels. Detailed labels add a subtitle where the view provides one.

Select the **Settings: …** row on the Skin Settings page to cycle through **Standard**, **Advanced**, and **Expert**.

For larger text, select **Readable (Large Text)** under **Settings > Interface > Skin > Fonts**. The font set supports Unicode and uses larger sizes across the defined text roles. The skin also fits two-line widget titles at the larger size.

The skin service migrates matching saved image paths from `special://skin/extras/` to `resource://resource.images.arctic.fuse.3/extras/`. Migration covers existing JPG and PNG files and directories in skin settings and this skin's Skin Variables shortcut files. Missing images, other file types, and external paths stay unchanged. Changed shortcut files keep a `.before-resource-image-migration` backup.

## Source layout

- `1080i/` — skin windows, dialogs, includes, fonts, and script integrations.
- `shortcuts/` — menu, widget, view-type, and Skin Variables shortcut definitions.
- `colors/` — color presets.
- `fonts/` — bundled typefaces.
- `media/`, `extras/`, `language/` — images, playlists, and translations.
- `service.py` — update recovery and saved image-path migration.
- `tests/` — source and layout checks.

## Maintenance

The tracked branch is `primez`. Run the configured check from the repository root:

```sh
python3 -m unittest discover -s tests
```

Enable the local pre-push checks with:

```sh
git config core.hooksPath .githooks
```

For changes to shipped behavior, update the root `addon.xml` version and add the matching `<news>` entry. README-only edits need no version bump. Follow the central [versioning policy](https://github.com/primez-x/kodi.addons/blob/main/VERSIONING.md). The central [repository guide](https://github.com/primez-x/kodi.addons/blob/main/README.md) documents the source webhook and GitHub Actions publish flow.

## Credit and license

The original skin is by [jurialmunkey](https://github.com/jurialmunkey). Primez maintains this fork. The skin uses the [Creative Commons Attribution-NonCommercial-ShareAlike 4.0 license](LICENSE.txt).

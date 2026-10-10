# Repository Guidelines

## Project Structure & Module Organization

This repository is a Kodi skin add-on (`skin.arctic.fuse.3`). Core skin XML windows, dialogs, and includes live in `1080i/`. Skin color presets are in `colors/`; generated shortcut and Skin Variables configuration is in `shortcuts/`; localization files are under `language/resource.language.*/strings.po`. Static assets are committed directly: images in `media/` and `extras/`, fonts in `fonts/`, with root `icon.png` and `fanart.jpg` used by `addon.xml`.

## Build, Test, and Development Commands

There is no package-manager build step. Validate changes with local tools and Kodi:

```powershell
git status --short
git diff --check
Get-ChildItem 1080i,colors,shortcuts -Recurse -Filter *.xml | % { [xml](Get-Content $_.FullName -Raw) | Out-Null }
```

`git diff --check` catches whitespace errors. The XML parse command catches malformed XML in tracked skin/config XML files. For runtime testing, install or symlink this folder into Kodi's `addons` directory, enable Arctic Fuse 3, then exercise the affected window, dialog, widget, or setting in Kodi.

## Coding Style & Naming Conventions

Use UTF-8 XML with LF line endings; `.gitattributes` normalizes text files. Indent XML and JSON with 4 spaces, matching existing files. Preserve Kodi naming patterns: standard window files such as `Home.xml`, grouped includes such as `Includes_Widgets.xml`, custom windows/dialogs such as `Custom_1145_OSD_InfoPanel.xml`, and generated integration files such as `script-skinvariables-*.xml`. Keep include, variable, property, and setting names consistent with nearby `Action_*`, `Hub_*`, `$VAR[...]`, and `Skin.SetString(...)` conventions.

## Testing Guidelines

No automated test suite is defined. Treat Kodi runtime verification as required for UI behavior changes. Test the smallest affected surface first, then check adjacent navigation/focus paths, visibility conditions, and aspect ratios declared in `addon.xml`. For localization edits, verify the changed `strings.po` loads in Kodi and does not break English fallback labels.

## Commit & Pull Request Guidelines

Recent history uses concise imperative subjects, often with emoji codes for category commits, for example `:symbols: Update strings.po French (#239)`, `:bookmark: Version bump`, `:sparkles: Add viewtype grouping`, and `:zap: Update episodes plotline`. Keep commits focused and reference issue/PR numbers when applicable.

For Primez repository publishing, any commit pushed to the tracked `primez` branch must bump the root `addon.xml` version in the same commit. Kodi auto-update consumes the generated repository version, not the Git SHA, and the central `kodi.addons` publish guard rejects webhook publishes whose source version does not increase.

Pull requests should describe the user-visible change, list tested Kodi areas, mention required dependency/version changes in `addon.xml`, and include screenshots or screen recordings for visual UI changes.

## Security & Configuration Tips

Do not commit local Kodi profile data, generated cache files, or private tokens. The release dispatch workflow depends on repository secrets; do not rename or expose those values.

## Primez Publish Rules

The tracked branch is `primez`: every push to it is published to the Primez Kodi repository. Each push must bump the root `addon.xml` version and add a `<news>` entry on top whose first line names the new version (match the existing format). Kodi auto-update follows the repository version, not the Git SHA.

`.githooks/pre-push` enforces this before the push leaves the machine (version above the branch tip, news entry, and the `tests` in `.primez-publish.json` passing on the pushed commit); enable it with `git config core.hooksPath .githooks` (Claude Code sessions do this automatically). `.github/workflows/publish-check.yml` runs the same check on GitHub, and the `kodi.addons` publish refuses commits that fail it. `.githooks/publish_check.py` is a copy of `primez-x/kodi.addons` `tools/publish_check.py`; change it there and re-copy it. Keep `.primez-publish.json` tests in sync with how this repository's tests are run.

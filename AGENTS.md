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

Run `python3 -m unittest discover -s tests` for the automated test suite. Treat Kodi runtime verification as required for UI behavior changes. Test the smallest affected surface first, then check adjacent navigation/focus paths, visibility conditions, and aspect ratios declared in `addon.xml`. For localization edits, verify the changed `strings.po` loads in Kodi and does not break English fallback labels.

## Commit & Pull Request Guidelines

Recent history uses concise imperative subjects, often with emoji codes for category commits, for example `:symbols: Update strings.po French (#239)`, `:bookmark: Version bump`, `:sparkles: Add viewtype grouping`, and `:zap: Update episodes plotline`. Keep commits focused and reference issue/PR numbers when applicable.

Pull requests should describe the user-visible change, list tested Kodi areas, mention required dependency/version changes in `addon.xml`, and include screenshots or screen recordings for visual UI changes.

## Security & Configuration Tips

Do not commit local Kodi profile data, generated cache files, or private tokens. The release dispatch workflow depends on repository secrets; do not rename or expose those values.

## Primez Publish Rules

Pushes to tracked branch `primez` run the Primez publish check. Kodi auto-update follows the add-on version, not the Git SHA. Read [VERSIONING.md](https://github.com/primez-x/kodi.addons/blob/main/VERSIONING.md) for release levels and non-release cases.

A change to a shipped file that a user or another add-on can notice needs a release. Raise exactly one version component by 1 from the branch tip. Reset every component to the right to 0, and keep the same component count. Add a `<news>` entry at the top. Name the new version in the first line, using the add-on's existing format.

Changing the version in `addon.xml` always makes a release. A push that changes only non-shipped files needs no version bump or news entry. Add `No-Release: <reason>` to the tip commit message for a change to a shipped file without an effect.

Adopting an upstream version is the only allowed version jump. Add `Version-Jump: <reason>` to the tip commit message. Keep the adopted version higher than the current version. Run every command in `.primez-publish.json` on every push, including non-release pushes.

`.githooks/pre-push` runs the publish check before each push leaves the machine. Enable the local hook with `git config core.hooksPath .githooks` (Claude Code sessions do this automatically). CI runs the same check through `.github/workflows/publish-check.yml`. `.githooks/publish_check.py` copies the master file `primez-x/kodi.addons/tools/publish_check.py`. Update the master file in `primez-x/kodi.addons`, then copy the file to this add-on's `.githooks/publish_check.py`.

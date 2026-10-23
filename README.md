# Subtitle Profiles for Kodi 21 Omega

Subtitle Profiles is a Kodi service and script add-on for reusable subtitle appearance profiles and persistent per-file/per-directory assignments.

## Features

- Unlimited named profiles with create, duplicate, rename, edit, restore, and delete operations.
- Non-destructive working copies: editing a profile never updates it until **Save Changes to Existing Profile** is confirmed.
- Exact-file, directory-only, recursive-directory, and global-default rules.
- Linked profiles with property-level local overrides, or detached snapshots.
- Automatic playback restoration through `xbmc.Player.onAVStarted` / `onAVChange`.
- Live editing of every subtitle property exposed by the current Kodi build.
- Deterministic vertical offset stored in pixels and converted to Kodi's vertical-margin percentage for the current display height.
- Export/import and SQLite backup.
- Optional reversible PellucidRemix OSD patch. The core add-on works with any skin.

## Device verified

- CoreELEC 21.3 Omega nightly (`20251102`)
- Kodi bundled Python 3.11.9
- `skin.pellucidRemix` 3.1.0 by LucanUK, GUI ABI 5.17.0
- Ugoos AM6+

## Installation

1. Install `dist/script.subtitle.profiles-0.1.0.zip` using **Add-ons → Install from zip file**.
2. The background service starts at Kodi login.
3. Launch **Subtitle Profiles** from Program add-ons when using another skin.
4. For Pellucid integration, apply the supplied reversible patch as documented below.

No Apple fonts are bundled. The built-in **Apple TV** profile chooses the first installed match from SF Pro, Helvetica Neue, Nimbus Sans, Inter, then Kodi Default. Its initial values are editable.

## PellucidRemix integration

The verified skin directory is:

`/storage/.kodi/addons/skin.pellucidRemix/1080i`

Apply on CoreELEC:

```sh
python3 patch_pellucid.py /storage/.kodi/addons/skin.pellucidRemix/1080i
kodi-send --action=ReloadSkin
```

The tool creates timestamped backups beside each XML file it changes and refuses to patch unexpected files. The OSD **Subtitles** button keeps opening Kodi's native subtitle menu. **Subtitle profiles** appears as the last item in its left-hand settings list; selecting it closes the native dialog before entering the profile editor.

Restore:

```sh
python3 patch_pellucid.py /storage/.kodi/addons/skin.pellucidRemix/1080i/DialogSettings.xml \
  --restore /path/to/DialogSettings.xml.subtitle-profiles-backup-TIMESTAMP
kodi-send --action=ReloadSkin
```

If migrating from the older direct-button integration, the apply command also restores the native action in `VideoOSD.xml` and backs that file up separately.

## Normal use

- **Select Profile** applies a profile immediately and, when a stable path exists, remembers it for the current file by default.
- **Edit Current Style** edits a live working copy. Focus a value and use **Left / Right** to change it inline; OK opens no numeric keyboard. Choose **Cancel and Revert** to restore its pre-edit state.
- **Use for This Directory** stores profile overrides without creating a new profile.
- Removing a file rule makes it inherit the nearest applicable directory rule or global default.
- **Original Subtitle Settings** keeps Kodi's native subtitle settings accessible.

Application data is stored in:

`special://profile/addon_data/script.subtitle.profiles/profiles.db`

## Development and tests

```sh
PYTHONPATH=addon/script.subtitle.profiles/resources/lib \
python3 -m unittest discover -s tests -p 'test_*.py' -v

python3 tools/build.py
```

See [architecture](docs/ARCHITECTURE.md), [compatibility](docs/COMPATIBILITY.md), and [uninstallation](docs/ROLLBACK.md).

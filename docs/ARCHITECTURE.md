# Architecture and storage

## Components

- `service.py`: event-driven playback observer. It resolves and reapplies a complete effective style on every video transition, preventing the previous video's style from leaking.
- `default.py`: remote-friendly native Kodi dialog UI.
- `storage.py`: versioned SQLite schema, transactions, linked profiles, overrides, snapshots, export/import, and backups.
- `pathing.py`: local/SMB/NFS normalization, directory-boundary matching, and credential removal.
- `kodi_runtime.py`: capability probing and JSON-RPC setting application.

## Rule precedence

1. Exact file rule.
2. Most specific directory-only rule for the file's direct directory.
3. Most specific recursive parent directory rule.
4. Global default profile.

`/Movies/` never matches `/Movies2/`. URL username/password, query, and fragment data are removed before a network path is stored.

## Data model

`presets` stores named reusable property JSON and immutable original values for restoration.

`assignments` stores a normalized path, scope, recursive flag, optional linked preset ID, property overrides, or an independent snapshot.

`app_settings` stores schema version and global default profile ID.

Deleting a user profile detaches linked assignments into effective snapshots before deletion. Built-in profiles cannot be deleted but can be restored.

## Vertical positioning

Kodi's `SubtitleShiftUp/Down` actions modify a temporary pixel position inside the current player. Replaying incremental actions is not deterministic because the initial player position is not exposed through supported Python or JSON-RPC APIs.

Subtitle Profiles stores `vertical_offset_px` and combines it with the profile's `subtitles.marginvertical` every time a rule is applied:

`effective margin % = base margin % + offset px × 100 / screen height`

Positive values move bottom-aligned text up; negative values move it down. The computed margin is clamped to Kodi's 0–50% supported range. No incremental offset is accumulated.

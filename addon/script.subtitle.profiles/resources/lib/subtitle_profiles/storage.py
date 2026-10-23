from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional

from .model import APPLE_TV_TEMPLATE, merge_properties
from .pathing import directory_matches, normalize_path


SCHEMA_VERSION = 1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _load(value: Optional[str], fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


@dataclass(frozen=True)
class Preset:
    id: int
    name: str
    properties: Dict[str, Any]
    original_properties: Dict[str, Any]
    builtin: bool


@dataclass(frozen=True)
class Assignment:
    id: int
    scope: str
    path: str
    recursive: bool
    preset_id: Optional[int]
    overrides: Dict[str, Any]
    snapshot: Optional[Dict[str, Any]]
    updated_at: str


@dataclass(frozen=True)
class Resolution:
    properties: Dict[str, Any]
    preset: Optional[Preset]
    assignment: Optional[Assignment]
    source: str
    overrides_count: int


class Storage:
    def __init__(self, database_path: str):
        self.database_path = database_path
        os.makedirs(os.path.dirname(database_path), exist_ok=True)
        self._migrate()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _migrate(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS presets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    properties TEXT NOT NULL,
                    original_properties TEXT NOT NULL,
                    builtin INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS assignments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope TEXT NOT NULL CHECK(scope IN ('file', 'directory')),
                    normalized_path TEXT NOT NULL,
                    recursive INTEGER NOT NULL DEFAULT 0,
                    preset_id INTEGER REFERENCES presets(id) ON DELETE SET NULL,
                    overrides TEXT NOT NULL DEFAULT '{}',
                    snapshot TEXT,
                    updated_at TEXT NOT NULL,
                    UNIQUE(scope, normalized_path)
                );
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            db.execute(
                "INSERT OR REPLACE INTO app_settings(key, value) VALUES('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )

    def initialize_defaults(self, kodi_default: Dict[str, Any], apple_font: str) -> None:
        apple = dict(APPLE_TV_TEMPLATE)
        apple["font"] = apple_font
        with self.connect() as db:
            count = db.execute("SELECT COUNT(*) FROM presets").fetchone()[0]
            if count:
                return
            now = _now()
            apple_id = db.execute(
                "INSERT INTO presets(name, properties, original_properties, builtin, created_at, updated_at) VALUES(?,?,?,?,?,?)",
                ("Apple TV", _dump(apple), _dump(apple), 1, now, now),
            ).lastrowid
            db.execute(
                "INSERT INTO presets(name, properties, original_properties, builtin, created_at, updated_at) VALUES(?,?,?,?,?,?)",
                ("Kodi Default", _dump(kodi_default), _dump(kodi_default), 1, now, now),
            )
            db.execute(
                "INSERT OR REPLACE INTO app_settings(key, value) VALUES('default_preset_id', ?)",
                (str(apple_id),),
            )

    @staticmethod
    def _preset(row: sqlite3.Row | None) -> Optional[Preset]:
        if row is None:
            return None
        return Preset(
            id=row["id"],
            name=row["name"],
            properties=_load(row["properties"], {}),
            original_properties=_load(row["original_properties"], {}),
            builtin=bool(row["builtin"]),
        )

    @staticmethod
    def _assignment(row: sqlite3.Row | None) -> Optional[Assignment]:
        if row is None:
            return None
        return Assignment(
            id=row["id"],
            scope=row["scope"],
            path=row["normalized_path"],
            recursive=bool(row["recursive"]),
            preset_id=row["preset_id"],
            overrides=_load(row["overrides"], {}),
            snapshot=_load(row["snapshot"], None),
            updated_at=row["updated_at"],
        )

    def list_presets(self) -> List[Preset]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM presets ORDER BY name COLLATE NOCASE").fetchall()
        return [self._preset(row) for row in rows if row is not None]

    def get_preset(self, preset_id: int | None) -> Optional[Preset]:
        if preset_id is None:
            return None
        with self.connect() as db:
            row = db.execute("SELECT * FROM presets WHERE id = ?", (preset_id,)).fetchone()
        return self._preset(row)

    def create_preset(self, name: str, properties: Dict[str, Any], builtin: bool = False) -> Preset:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Profile name cannot be empty")
        now = _now()
        with self.connect() as db:
            preset_id = db.execute(
                "INSERT INTO presets(name, properties, original_properties, builtin, created_at, updated_at) VALUES(?,?,?,?,?,?)",
                (clean_name, _dump(properties), _dump(properties), int(builtin), now, now),
            ).lastrowid
        return self.get_preset(preset_id)

    def update_preset(self, preset_id: int, properties: Dict[str, Any]) -> Preset:
        with self.connect() as db:
            cursor = db.execute(
                "UPDATE presets SET properties = ?, updated_at = ? WHERE id = ?",
                (_dump(properties), _now(), preset_id),
            )
            if cursor.rowcount != 1:
                raise KeyError("Profile does not exist")
        return self.get_preset(preset_id)

    def rename_preset(self, preset_id: int, name: str) -> Preset:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Profile name cannot be empty")
        with self.connect() as db:
            db.execute("UPDATE presets SET name = ?, updated_at = ? WHERE id = ?", (clean_name, _now(), preset_id))
        return self.get_preset(preset_id)

    def restore_preset(self, preset_id: int) -> Preset:
        preset = self.get_preset(preset_id)
        if not preset:
            raise KeyError("Profile does not exist")
        return self.update_preset(preset_id, preset.original_properties)

    def delete_preset(self, preset_id: int) -> None:
        preset = self.get_preset(preset_id)
        if not preset:
            return
        if preset.builtin:
            raise ValueError("Built-in profiles can be restored but not deleted")
        with self.connect() as db:
            rows = db.execute("SELECT * FROM assignments WHERE preset_id = ?", (preset_id,)).fetchall()
            for row in rows:
                assignment = self._assignment(row)
                snapshot = merge_properties(preset.properties, assignment.overrides)
                db.execute(
                    "UPDATE assignments SET preset_id = NULL, overrides = '{}', snapshot = ?, updated_at = ? WHERE id = ?",
                    (_dump(snapshot), _now(), assignment.id),
                )
            db.execute("DELETE FROM presets WHERE id = ?", (preset_id,))

    def set_default_preset(self, preset_id: int) -> None:
        if not self.get_preset(preset_id):
            raise KeyError("Profile does not exist")
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO app_settings(key, value) VALUES('default_preset_id', ?)",
                (str(preset_id),),
            )

    def get_default_preset(self) -> Optional[Preset]:
        with self.connect() as db:
            row = db.execute("SELECT value FROM app_settings WHERE key = 'default_preset_id'").fetchone()
        return self.get_preset(int(row[0])) if row and str(row[0]).isdigit() else None

    def set_assignment(
        self,
        scope: str,
        path: str,
        recursive: bool = False,
        preset_id: int | None = None,
        overrides: Dict[str, Any] | None = None,
        snapshot: Dict[str, Any] | None = None,
    ) -> Assignment:
        if scope not in {"file", "directory"}:
            raise ValueError("Invalid assignment scope")
        normalized = normalize_path(path, directory=scope == "directory")
        if not normalized:
            raise ValueError("Assignment path cannot be empty")
        if preset_id is None and snapshot is None:
            raise ValueError("An assignment needs a profile or snapshot")
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO assignments(scope, normalized_path, recursive, preset_id, overrides, snapshot, updated_at)
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(scope, normalized_path) DO UPDATE SET
                  recursive=excluded.recursive,
                  preset_id=excluded.preset_id,
                  overrides=excluded.overrides,
                  snapshot=excluded.snapshot,
                  updated_at=excluded.updated_at
                """,
                (scope, normalized, int(recursive), preset_id, _dump(overrides or {}), _dump(snapshot) if snapshot else None, _now()),
            )
            row = db.execute(
                "SELECT * FROM assignments WHERE scope = ? AND normalized_path = ?",
                (scope, normalized),
            ).fetchone()
        return self._assignment(row)

    def list_assignments(self) -> List[Assignment]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM assignments ORDER BY normalized_path COLLATE NOCASE").fetchall()
        return [self._assignment(row) for row in rows if row is not None]

    def get_assignment(self, assignment_id: int) -> Optional[Assignment]:
        with self.connect() as db:
            row = db.execute("SELECT * FROM assignments WHERE id = ?", (assignment_id,)).fetchone()
        return self._assignment(row)

    def remove_assignment(self, assignment_id: int) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM assignments WHERE id = ?", (assignment_id,))

    def effective_assignment_properties(self, assignment: Assignment) -> tuple[Dict[str, Any], Optional[Preset]]:
        preset = self.get_preset(assignment.preset_id)
        if preset:
            return merge_properties(preset.properties, assignment.overrides), preset
        return dict(assignment.snapshot or {}), None

    def resolve(self, media_path: str) -> Resolution:
        normalized = normalize_path(media_path)
        assignments = self.list_assignments()
        exact = next((item for item in assignments if item.scope == "file" and item.path == normalized), None)
        winner = exact
        source = "File Rule" if exact else ""
        if winner is None:
            candidates = [
                item
                for item in assignments
                if item.scope == "directory" and directory_matches(normalized, item.path, item.recursive)
            ]
            if candidates:
                winner = max(candidates, key=lambda item: len(item.path))
                source = "Recursive Directory Rule" if winner.recursive else "Directory Rule"
        if winner:
            properties, preset = self.effective_assignment_properties(winner)
            return Resolution(properties, preset, winner, source, len(winner.overrides))

        preset = self.get_default_preset()
        if preset:
            return Resolution(dict(preset.properties), preset, None, "Global Default", 0)
        return Resolution({}, None, None, "No Profile", 0)

    def export_data(self, output_path: str) -> None:
        payload = {
            "format": 1,
            "exported_at": _now(),
            "presets": [
                {
                    "name": item.name,
                    "properties": item.properties,
                    "original_properties": item.original_properties,
                    "builtin": item.builtin,
                }
                for item in self.list_presets()
            ],
            "assignments": [
                {
                    "scope": item.scope,
                    "path": item.path,
                    "recursive": item.recursive,
                    "preset_name": self.get_preset(item.preset_id).name if self.get_preset(item.preset_id) else None,
                    "overrides": item.overrides,
                    "snapshot": item.snapshot,
                }
                for item in self.list_assignments()
            ],
            "default_preset": self.get_default_preset().name if self.get_default_preset() else None,
        }
        temporary = output_path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output_path)

    def import_data(self, input_path: str) -> None:
        with open(input_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if payload.get("format") != 1:
            raise ValueError("Unsupported export format")
        name_to_id = {}
        with self.connect() as db:
            for item in payload.get("presets", []):
                now = _now()
                db.execute(
                    """
                    INSERT INTO presets(name, properties, original_properties, builtin, created_at, updated_at)
                    VALUES(?,?,?,?,?,?)
                    ON CONFLICT(name) DO UPDATE SET properties=excluded.properties, updated_at=excluded.updated_at
                    """,
                    (
                        item["name"], _dump(item.get("properties", {})),
                        _dump(item.get("original_properties", item.get("properties", {}))),
                        int(item.get("builtin", False)), now, now,
                    ),
                )
            for row in db.execute("SELECT id, name FROM presets"):
                name_to_id[row["name"]] = row["id"]
        for item in payload.get("assignments", []):
            self.set_assignment(
                item["scope"], item["path"], bool(item.get("recursive")),
                name_to_id.get(item.get("preset_name")), item.get("overrides"), item.get("snapshot"),
            )
        default_name = payload.get("default_preset")
        if default_name in name_to_id:
            self.set_default_preset(name_to_id[default_name])

    def backup(self, output_path: str) -> None:
        with self.connect() as source:
            destination = sqlite3.connect(output_path)
            try:
                source.backup(destination)
            finally:
                destination.close()

    def restore_backup(self, input_path: str) -> None:
        if not os.path.isfile(input_path):
            raise ValueError("Backup does not exist")
        check = sqlite3.connect(input_path)
        try:
            result = check.execute("PRAGMA integrity_check").fetchone()[0]
            if result != "ok":
                raise ValueError("Backup database failed its integrity check")
        finally:
            check.close()
        temporary = self.database_path + ".restore"
        source = sqlite3.connect(input_path)
        destination = sqlite3.connect(temporary)
        try:
            source.backup(destination)
        finally:
            source.close()
            destination.close()
        os.replace(temporary, self.database_path)
        self._migrate()

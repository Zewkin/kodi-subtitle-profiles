from __future__ import annotations

import json
import os
import sqlite3
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

import xbmcgui

from .kodi_runtime import KodiRuntime
from .model import KODI_SETTING_IDS, merge_properties, property_diff
from .pathing import safe_path_label
from .storage import Assignment, Preset, Resolution


BACKGROUND_TYPES = [("None", 0), ("Shadow", 1), ("Box", 2), ("Square box", 3)]
FONT_STYLES = [("Regular", 0), ("Bold", 1), ("Italic", 2), ("Bold italic", 3)]
ALIGNMENTS = [
    ("Manual", 0), ("Bottom of video", 1), ("Bottom of screen", 2),
    ("Top of video", 3), ("Top of screen", 4),
]
OVERRIDE_STYLES = [("Disabled", 0), ("Positions", 1), ("Styles", 2), ("Styles and positions", 3)]
STYLE_FIELDS = [
    ("font", "Font"), ("font_size", "Size"), ("font_style", "Style"),
    ("text_color", "Text color"), ("text_opacity", "Text opacity"),
    ("background_type", "Background type"), ("background_color", "Background color"),
    ("background_opacity", "Background opacity"), ("border_size", "Border size"),
    ("border_color", "Border color"), ("shadow_color", "Shadow color"),
    ("shadow_opacity", "Shadow opacity"), ("shadow_size", "Shadow size"),
    ("blur", "Blur"), ("line_spacing", "Line spacing"), ("alignment", "Alignment"),
    ("margin_vertical", "Base vertical margin (%)"),
    ("vertical_offset_px", "Vertical offset (+ up / - down)"),
    ("override_fonts", "Override embedded fonts"),
    ("override_styles", "Override embedded styles"),
]
NUMERIC_FIELDS = {
    "font_size": (12, 74, 2),
    "text_opacity": (0, 100, 1),
    "background_opacity": (0, 100, 1),
    "border_size": (0, 100, 1),
    "shadow_opacity": (0, 100, 1),
    "shadow_size": (0, 100, 1),
    "blur": (0, 100, 1),
    "line_spacing": (0, 100, 1),
    "margin_vertical": (0.0, 50.0, 0.05),
    "vertical_offset_px": (-500, 500, 1),
}


class StyleEditorDialog(xbmcgui.WindowXMLDialog):
    ACTION_LEFT = 1
    ACTION_RIGHT = 2
    ACTION_PREVIOUS_MENU = 10
    ACTION_NAV_BACK = 92

    def configure(self, runtime: KodiRuntime, properties: Dict[str, Any], fields: List[Tuple[str, str]], live: bool) -> None:
        self.runtime = runtime
        self.result = deepcopy(properties)
        self.original = deepcopy(properties)
        self.fields = fields
        self.live = live
        self.accepted = False
        self.list_control = None

    def onInit(self) -> None:
        self.list_control = self.getControl(50)
        self.list_control.reset()
        for name, label in self.fields:
            self.list_control.addItem(xbmcgui.ListItem(label=label, label2=SubtitleProfilesApp.format_value(name, self.result.get(name))))
        self.list_control.addItem(xbmcgui.ListItem(label="Keep modified working copy"))
        self.list_control.addItem(xbmcgui.ListItem(label="Cancel and revert"))
        self.setFocus(self.list_control)

    def onAction(self, action) -> None:
        action_id = action.getId()
        if action_id in (self.ACTION_PREVIOUS_MENU, self.ACTION_NAV_BACK):
            self._cancel()
            return
        if action_id not in (self.ACTION_LEFT, self.ACTION_RIGHT) or self.list_control is None:
            return
        selected = self.list_control.getSelectedPosition()
        if selected < 0 or selected >= len(self.fields):
            return
        name, _ = self.fields[selected]
        if self._step_value(name, -1 if action_id == self.ACTION_LEFT else 1):
            item = self.list_control.getListItem(selected)
            item.setLabel2(SubtitleProfilesApp.format_value(name, self.result.get(name)))
            self._apply_live()

    def onClick(self, control_id: int) -> None:
        if control_id != 50 or self.list_control is None:
            return
        selected = self.list_control.getSelectedPosition()
        if selected == len(self.fields):
            self.accepted = True
            self.close()
        elif selected == len(self.fields) + 1:
            self._cancel()
        # Pressing OK on a value intentionally opens nothing. Values are
        # changed inline with Left/Right, like Kodi's native settings menus.

    def _step_value(self, name: str, direction: int) -> bool:
        current = self.result.get(name)
        if name in NUMERIC_FIELDS:
            minimum, maximum, step = NUMERIC_FIELDS[name]
            value = max(minimum, min(maximum, current + direction * step))
            if isinstance(step, float):
                value = round(value, 2)
            else:
                value = int(value)
            if value == current:
                return False
            self.result[name] = value
            return True
        options = {
            "font": self.runtime.font_options(),
            "background_type": [value for _, value in BACKGROUND_TYPES],
            "font_style": [value for _, value in FONT_STYLES],
            "alignment": [value for _, value in ALIGNMENTS],
            "override_styles": [value for _, value in OVERRIDE_STYLES],
            "override_fonts": [False, True],
        }.get(name)
        if not options:
            return False
        try:
            index = options.index(current)
        except ValueError:
            index = 0
        self.result[name] = options[(index + direction) % len(options)]
        return True

    def _apply_live(self) -> None:
        if not self.live:
            return
        failures = self.runtime.apply_style(self.result)
        if failures:
            self.runtime.notify("Kodi rejected: " + ", ".join(sorted(failures)))

    def _cancel(self) -> None:
        if self.live:
            self.runtime.apply_style(self.original)
        self.result = deepcopy(self.original)
        self.accepted = False
        self.close()


class SubtitleProfilesApp:
    def __init__(self):
        self.runtime = KodiRuntime()
        self.dialog = xbmcgui.Dialog()
        self.media_path = self.runtime.current_media_path()
        self.resolution = self.runtime.storage.resolve(self.media_path)
        self.base_preset = self.resolution.preset
        self.working = deepcopy(self.resolution.properties or self.runtime.capture_style())
        self.original_working = deepcopy(self.working)

    @property
    def modified(self) -> bool:
        reference = self.base_preset.properties if self.base_preset else self.original_working
        return self.working != reference

    def active_name(self) -> str:
        name = self.base_preset.name if self.base_preset else "Custom style"
        return name + (" (Modified)" if self.modified else "")

    def run(self) -> None:
        home = xbmcgui.Window(10000)
        home.setProperty("SubtitleProfiles.DialogOpen", "true")
        try:
            self._run_menu()
        finally:
            home.clearProperty("SubtitleProfiles.DialogOpen")

    def _run_menu(self) -> None:
        while True:
            assigned = self.resolution.source or "Apply once"
            items = [
                f"Active: {self.active_name()}",
                f"Assigned by: {assigned}",
                "Select Profile  ·  use for this file",
                "Edit Current Style",
                "Save as New Profile",
                "Save Changes to Existing Profile",
                "Apply Once",
                "Use for This File",
                "Use for This Directory",
                "Use for Directory and Subdirectories",
                "Set Profile as Global Default",
                "Manage Profiles",
                "Manage Assignments",
                "Export / Import / Backup",
                "Original Subtitle Settings",
            ]
            choice = self.dialog.select("Subtitle profiles", items, preselect=2)
            if choice < 0:
                return
            try:
                if choice in (0, 1):
                    self.show_status()
                elif choice == 2:
                    self.select_profile(default_file_assignment=True)
                elif choice == 3:
                    self.edit_working()
                elif choice == 4:
                    self.save_as_new()
                elif choice == 5:
                    self.save_existing()
                elif choice == 6:
                    self.runtime.apply_style(self.working)
                    self.runtime.notify("Applied for this playback only")
                elif choice == 7:
                    self.assign_working("file", False)
                elif choice == 8:
                    self.assign_working("directory", False)
                elif choice == 9:
                    self.assign_working("directory", True)
                elif choice == 10:
                    self.set_global_default()
                elif choice == 11:
                    self.manage_presets()
                elif choice == 12:
                    self.manage_assignments()
                elif choice == 13:
                    self.data_tools()
                elif choice == 14:
                    self.runtime.open_original_settings()
                    return
            except (ValueError, KeyError, sqlite3.IntegrityError, OSError) as exc:
                self.dialog.ok("Subtitle Profiles", str(exc))

    def show_status(self) -> None:
        assignment = self.resolution.assignment
        lines = [
            "Active Profile: " + self.active_name(),
            "Source: " + self.resolution.source,
            "Local Overrides: " + str(self.resolution.overrides_count),
        ]
        if assignment:
            lines.insert(2, "Assigned To: " + safe_path_label(assignment.path))
        if not self.media_path:
            lines.append("")
            lines.append("No video is currently playing. Path assignments are unavailable.")
        elif not self.runtime.path_is_assignable(self.media_path):
            lines.append("")
            lines.append("This stream has no stable local, SMB, or NFS path. Use Apply Once or the global default.")
        self.dialog.textviewer("Subtitle profile status", "\n".join(lines))

    def choose_preset(self, heading: str = "Select subtitle profile") -> Optional[Preset]:
        presets = self.runtime.storage.list_presets()
        labels = [("✓ " if self.base_preset and item.id == self.base_preset.id else "  ") + item.name for item in presets]
        selected = self.dialog.select(heading, labels)
        return presets[selected] if selected >= 0 else None

    def select_profile(self, default_file_assignment: bool) -> None:
        preset = self.choose_preset()
        if not preset:
            return
        previous = deepcopy(self.working)
        self.base_preset = preset
        self.working = deepcopy(preset.properties)
        failures = self.runtime.apply_style(self.working)
        if failures:
            self.dialog.ok("Subtitle Profiles", "Some properties are unsupported on this Kodi build:\n" + "\n".join(sorted(failures)))
        if default_file_assignment and self.media_path and self.runtime.path_is_assignable(self.media_path):
            self.runtime.storage.set_assignment("file", self.media_path, preset_id=preset.id)
            self.refresh_resolution()
            self.runtime.notify("Using %s for this file" % preset.name)
        else:
            self.original_working = previous
            self.runtime.notify("Applied once: " + preset.name)

    def edit_working(self) -> None:
        previous = deepcopy(self.working)
        edited, accepted = self.edit_properties(self.working, live=True)
        if accepted:
            self.working = edited
        else:
            self.working = previous
            self.runtime.apply_style(previous)

    def edit_properties(self, properties: Dict[str, Any], live: bool) -> Tuple[Dict[str, Any], bool]:
        supported = set(self.runtime.supported_properties())
        visible = [
            item for item in STYLE_FIELDS
            if item[0] in supported
            or (item[0] == "vertical_offset_px" and "margin_vertical" in supported)
        ]
        editor = StyleEditorDialog(
            "StyleEditor.xml",
            self.runtime.addon.getAddonInfo("path"),
            "Default",
            "1080i",
        )
        editor.configure(self.runtime, properties, visible, live)
        editor.doModal()
        result, accepted = deepcopy(editor.result), editor.accepted
        del editor
        return result, accepted

    @staticmethod
    def format_value(name: str, value: Any) -> str:
        maps = {
            "background_type": dict((value, label) for label, value in BACKGROUND_TYPES),
            "font_style": dict((value, label) for label, value in FONT_STYLES),
            "alignment": dict((value, label) for label, value in ALIGNMENTS),
            "override_styles": dict((value, label) for label, value in OVERRIDE_STYLES),
        }
        if name in maps:
            return maps[name].get(value, str(value))
        if isinstance(value, bool):
            return "On" if value else "Off"
        if name.endswith("opacity"):
            return f"{value}%"
        if name.endswith("color"):
            return str(value or "FFFFFFFF")
        return str(value)

    def prompt_property(self, name: str, label: str, current: Any) -> Tuple[bool, Any]:
        if name == "font":
            values = self.runtime.font_options()
            selected = self.dialog.select(label, values, preselect=values.index(current) if current in values else -1)
            return (selected >= 0, values[selected] if selected >= 0 else current)
        option_maps = {
            "background_type": BACKGROUND_TYPES,
            "font_style": FONT_STYLES,
            "alignment": ALIGNMENTS,
            "override_styles": OVERRIDE_STYLES,
        }
        if name in option_maps:
            options = option_maps[name]
            values = [value for _, value in options]
            selected = self.dialog.select(label, [text for text, _ in options], preselect=values.index(current) if current in values else -1)
            return (selected >= 0, values[selected] if selected >= 0 else current)
        if name in {"override_fonts"}:
            selected = self.dialog.select(label, ["Off", "On"], preselect=1 if current else 0)
            return (selected >= 0, bool(selected) if selected >= 0 else current)
        if name.endswith("color"):
            value = self.dialog.input(label + " (AARRGGBB)", defaultt=str(current or "FFFFFFFF"), type=xbmcgui.INPUT_ALPHANUM)
            value = value.strip().upper().lstrip("#")
            if len(value) == 8 and all(char in "0123456789ABCDEF" for char in value):
                return True, value
            if value:
                self.runtime.notify("Color must be eight hexadecimal characters")
            return False, current
        value = self.dialog.input(label, defaultt=str(current if current is not None else "0"), type=xbmcgui.INPUT_ALPHANUM)
        if value == "":
            return False, current
        try:
            if name == "margin_vertical":
                return True, max(0.0, min(50.0, round(float(value), 2)))
            limits = {
                "font_size": (12, 74), "text_opacity": (0, 100), "background_opacity": (0, 100),
                "border_size": (0, 100), "shadow_opacity": (0, 100), "shadow_size": (0, 100),
                "blur": (0, 100), "line_spacing": (0, 100), "vertical_offset_px": (-500, 500),
            }
            minimum, maximum = limits.get(name, (-10000, 10000))
            return True, max(minimum, min(maximum, int(value)))
        except ValueError:
            self.runtime.notify("Enter a valid number")
            return False, current

    def save_as_new(self) -> None:
        name = self.dialog.input("New profile name", type=xbmcgui.INPUT_ALPHANUM).strip()
        if not name:
            return
        preset = self.runtime.storage.create_preset(name, self.working)
        self.base_preset = preset
        self.original_working = deepcopy(self.working)
        self.runtime.notify("Saved profile: " + preset.name)
        if self.media_path and self.dialog.yesno("Subtitle Profiles", "Use the new profile for this file?", nolabel="No", yeslabel="Yes"):
            self.runtime.storage.set_assignment("file", self.media_path, preset_id=preset.id)
            self.refresh_resolution()

    def save_existing(self) -> None:
        if not self.base_preset:
            self.dialog.ok("Subtitle Profiles", "This style is an independent snapshot. Save it as a new profile first.")
            return
        if not self.modified:
            self.runtime.notify("No changes to save")
            return
        if not self.dialog.yesno(
            "Update Profile",
            "All linked files and directories will inherit these changes. Update '%s'?" % self.base_preset.name,
            nolabel="Cancel", yeslabel="Update",
        ):
            return
        self.base_preset = self.runtime.storage.update_preset(self.base_preset.id, self.working)
        self.original_working = deepcopy(self.working)
        self.runtime.notify("Updated profile: " + self.base_preset.name)

    def assignment_payload(self) -> Tuple[Optional[int], Dict[str, Any], Optional[Dict[str, Any]]]:
        if self.base_preset:
            return self.base_preset.id, property_diff(self.base_preset.properties, self.working), None
        return None, {}, deepcopy(self.working)

    def assign_working(self, scope: str, recursive: bool) -> None:
        if not self.media_path:
            raise ValueError("Start video playback before creating a path assignment")
        if not self.runtime.path_is_assignable(self.media_path):
            raise ValueError("This stream does not expose a stable local, SMB, or NFS path")
        path = self.media_path if scope == "file" else self.runtime.current_directory()
        preset_id, overrides, snapshot = self.assignment_payload()
        self.runtime.storage.set_assignment(scope, path, recursive, preset_id, overrides, snapshot)
        self.runtime.apply_style(self.working)
        self.refresh_resolution()
        scope_name = "file" if scope == "file" else ("directory tree" if recursive else "directory")
        self.runtime.notify("Saved for this " + scope_name)

    def set_global_default(self) -> None:
        preset = self.choose_preset("Set global default")
        if preset:
            self.runtime.storage.set_default_preset(preset.id)
            self.runtime.notify("Global default: " + preset.name)

    def manage_presets(self) -> None:
        while True:
            presets = self.runtime.storage.list_presets()
            selected = self.dialog.select("Manage profiles", [item.name for item in presets])
            if selected < 0:
                return
            preset = presets[selected]
            actions = ["Use as Working Copy", "Edit Profile", "Duplicate", "Rename", "Restore Original Values", "Delete"]
            action = self.dialog.select(preset.name, actions)
            if action < 0:
                continue
            if action == 0:
                self.base_preset = preset
                self.working = deepcopy(preset.properties)
                self.runtime.apply_style(self.working)
                return
            if action == 1:
                edited, accepted = self.edit_properties(preset.properties, live=False)
                if accepted and edited != preset.properties and self.dialog.yesno("Update Profile", "Save these changes to '%s'?" % preset.name):
                    self.runtime.storage.update_preset(preset.id, edited)
            elif action == 2:
                name = self.dialog.input("Duplicate name", defaultt=preset.name + " Copy", type=xbmcgui.INPUT_ALPHANUM)
                if name.strip():
                    self.runtime.storage.create_preset(name, preset.properties)
            elif action == 3:
                name = self.dialog.input("Profile name", defaultt=preset.name, type=xbmcgui.INPUT_ALPHANUM)
                if name.strip():
                    self.runtime.storage.rename_preset(preset.id, name)
            elif action == 4 and self.dialog.yesno("Restore Profile", "Restore the original values of '%s'?" % preset.name):
                self.runtime.storage.restore_preset(preset.id)
            elif action == 5 and self.dialog.yesno("Delete Profile", "Assignments will become independent snapshots. Delete '%s'?" % preset.name):
                self.runtime.storage.delete_preset(preset.id)

    def manage_assignments(self) -> None:
        while True:
            assignments = self.runtime.storage.list_assignments()
            if not assignments:
                self.dialog.ok("Saved Assignments", "No file or directory assignments exist.")
                return
            labels = []
            for item in assignments:
                _, preset = self.runtime.storage.effective_assignment_properties(item)
                name = preset.name if preset else "Custom snapshot"
                if item.overrides:
                    name += " (Customized)"
                suffix = " [recursive]" if item.recursive else ""
                labels.append(safe_path_label(item.path) + "\n  " + name + suffix)
            selected = self.dialog.select("Saved assignments", labels)
            if selected < 0:
                return
            assignment = assignments[selected]
            action = self.dialog.select(
                "Assignment",
                ["View Details", "Switch Profile", "Edit Local Overrides", "Change Scope", "Detach as Snapshot", "Remove Assignment"],
            )
            if action == 0:
                self.assignment_details(assignment)
            elif action == 1:
                preset = self.choose_preset("Switch assigned profile")
                if preset:
                    self.runtime.storage.set_assignment(assignment.scope, assignment.path, assignment.recursive, preset.id)
            elif action == 2:
                effective, preset = self.runtime.storage.effective_assignment_properties(assignment)
                edited, accepted = self.edit_properties(effective, live=False)
                if accepted:
                    overrides = property_diff(preset.properties, edited) if preset else {}
                    snapshot = None if preset else edited
                    self.runtime.storage.set_assignment(assignment.scope, assignment.path, assignment.recursive, preset.id if preset else None, overrides, snapshot)
            elif action == 3:
                scopes = [("Current file", "file", False), ("Directory only", "directory", False), ("Directory and subdirectories", "directory", True)]
                selected_scope = self.dialog.select("Change scope", [item[0] for item in scopes])
                if selected_scope >= 0:
                    _, scope, recursive = scopes[selected_scope]
                    path = assignment.path
                    if scope != assignment.scope:
                        if assignment.scope == "file" and scope == "directory":
                            from .pathing import directory_for
                            path = directory_for(path)
                        elif assignment.scope == "directory" and scope == "file":
                            self.dialog.ok("Change Scope", "A directory rule cannot be converted to a file without a specific media filename.")
                            continue
                    self.runtime.storage.set_assignment(
                        scope, path, recursive, assignment.preset_id,
                        assignment.overrides, assignment.snapshot,
                    )
                    if path != assignment.path or scope != assignment.scope:
                        self.runtime.storage.remove_assignment(assignment.id)
            elif action == 4:
                effective, _ = self.runtime.storage.effective_assignment_properties(assignment)
                self.runtime.storage.set_assignment(assignment.scope, assignment.path, assignment.recursive, snapshot=effective)
            elif action == 5 and self.dialog.yesno("Remove Assignment", "The path will inherit its nearest parent rule or global default. Remove it?"):
                self.runtime.storage.remove_assignment(assignment.id)
                if self.media_path:
                    self.refresh_resolution()
                    self.runtime.apply_resolution(self.resolution)

    def assignment_details(self, assignment: Assignment) -> None:
        effective, preset = self.runtime.storage.effective_assignment_properties(assignment)
        text = [
            "Path: " + safe_path_label(assignment.path),
            "Scope: " + assignment.scope,
            "Recursive: " + ("Yes" if assignment.recursive else "No"),
            "Profile: " + (preset.name if preset else "Independent snapshot"),
            "Local overrides: " + str(len(assignment.overrides)),
            "",
            json.dumps(effective, ensure_ascii=False, indent=2, sort_keys=True),
        ]
        self.dialog.textviewer("Assignment details", "\n".join(text))

    def data_tools(self) -> None:
        action = self.dialog.select(
            "Data tools",
            ["Export Profiles and Assignments", "Import Export File", "Create Database Backup", "Restore Database Backup"],
        )
        if action == 0:
            self.runtime.storage.export_data(self.runtime.export_path())
            self.dialog.ok("Export Complete", self.runtime.export_path())
        elif action == 1:
            path = self.runtime.export_path()
            if not os.path.exists(path):
                raise ValueError("Export file does not exist: " + path)
            if self.dialog.yesno("Import Data", "Merge profiles and assignments from the export file?"):
                self.runtime.storage.import_data(path)
                self.runtime.notify("Import complete")
        elif action == 2:
            self.runtime.storage.backup(self.runtime.backup_path())
            self.dialog.ok("Backup Complete", self.runtime.backup_path())
        elif action == 3 and self.dialog.yesno("Restore Backup", "Replace all current profiles and assignments with the database backup?"):
            self.runtime.storage.restore_backup(self.runtime.backup_path())
            self.refresh_resolution()
            self.runtime.notify("Backup restored")

    def refresh_resolution(self) -> None:
        self.resolution = self.runtime.storage.resolve(self.media_path)
        self.base_preset = self.resolution.preset
        self.working = deepcopy(self.resolution.properties)
        self.original_working = deepcopy(self.working)
        self.runtime.publish_resolution(self.resolution)

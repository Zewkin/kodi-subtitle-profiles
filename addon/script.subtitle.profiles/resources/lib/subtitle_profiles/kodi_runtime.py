from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

from .model import KODI_SETTING_IDS, choose_apple_font, effective_kodi_values
from .pathing import directory_for, is_stable_media_path, normalize_path, safe_path_label
from .storage import Resolution, Storage


ADDON_ID = "script.subtitle.profiles"
PROPERTY_PREFIX = "SubtitleProfiles."


def json_rpc(method: str, params: Optional[Dict[str, Any]] = None, request_id: Any = 1) -> Dict[str, Any]:
    request = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        request["params"] = params
    try:
        return json.loads(xbmc.executeJSONRPC(json.dumps(request)))
    except (TypeError, ValueError):
        return {"error": {"message": "Invalid JSON-RPC response"}}


class KodiRuntime:
    def __init__(self):
        self.addon = xbmcaddon.Addon(ADDON_ID)
        profile = xbmcvfs.translatePath(self.addon.getAddonInfo("profile"))
        os.makedirs(profile, exist_ok=True)
        self.profile_path = profile
        self.storage = Storage(os.path.join(profile, "profiles.db"))
        self._capabilities: Optional[Dict[str, Dict[str, Any]]] = None
        self._bootstrap()

    def _bootstrap(self) -> None:
        current = self.capture_style()
        fonts = self.font_options()
        self.storage.initialize_defaults(current, choose_apple_font(fonts))

    def log(self, message: str, level: int = xbmc.LOGINFO) -> None:
        xbmc.log("[Subtitle Profiles] " + message, level)

    def notify(self, message: str, milliseconds: int = 2500) -> None:
        xbmcgui.Dialog().notification("Subtitle Profiles", message, time=milliseconds, sound=False)

    def get_setting(self, setting_id: str) -> tuple[bool, Any]:
        response = json_rpc("Settings.GetSettingValue", {"setting": setting_id}, setting_id)
        result = response.get("result", {})
        return ("value" in result, result.get("value"))

    def capabilities(self, refresh: bool = False) -> Dict[str, Dict[str, Any]]:
        if self._capabilities is not None and not refresh:
            return self._capabilities
        response = json_rpc(
            "Settings.GetSettings",
            {"filter": {"section": "player", "category": "subtitles"}, "level": "expert"},
        )
        details = {item["id"]: item for item in response.get("result", {}).get("settings", [])}
        for setting_id in KODI_SETTING_IDS.values():
            ok, value = self.get_setting(setting_id)
            if ok and setting_id not in details:
                details[setting_id] = {"id": setting_id, "value": value, "options": None}
        self._capabilities = details
        return details

    def supported_properties(self) -> List[str]:
        capabilities = self.capabilities()
        return [name for name, setting_id in KODI_SETTING_IDS.items() if setting_id in capabilities]

    def font_options(self) -> List[str]:
        item = self.capabilities().get(KODI_SETTING_IDS["font"], {})
        options = item.get("options") or []
        values = [entry.get("value") for entry in options if entry.get("value")]
        if not values:
            ok, current = self.get_setting(KODI_SETTING_IDS["font"])
            values = [current] if ok else ["DEFAULT"]
        return values

    def screen_height(self) -> int:
        for label in ("System.ScreenHeight", "Window.Height"):
            try:
                value = int(float(xbmc.getInfoLabel(label) or 0))
                if value > 0:
                    return value
            except (TypeError, ValueError):
                pass
        return 1080

    def capture_style(self) -> Dict[str, Any]:
        captured: Dict[str, Any] = {}
        for name, setting_id in KODI_SETTING_IDS.items():
            ok, value = self.get_setting(setting_id)
            if ok:
                captured[name] = value
        captured["vertical_offset_px"] = 0
        return captured

    def apply_style(self, properties: Dict[str, Any]) -> Dict[str, str]:
        supported = self.capabilities()
        requested = effective_kodi_values(properties, self.screen_height())
        failures: Dict[str, str] = {}
        requests = []
        for setting_id, value in requested.items():
            if setting_id not in supported:
                # Profiles are portable across Kodi versions and may contain
                # properties that this particular build does not expose.
                # Skipping one is not a rejection by Kodi.
                continue
            ok, current = self.get_setting(setting_id)
            if ok and current == value:
                continue
            requests.append(
                {
                    "jsonrpc": "2.0",
                    "id": setting_id,
                    "method": "Settings.SetSettingValue",
                    "params": {"setting": setting_id, "value": value},
                }
            )
        if requests:
            try:
                responses = json.loads(xbmc.executeJSONRPC(json.dumps(requests)))
            except (TypeError, ValueError):
                responses = []
            response_by_id = {item.get("id"): item for item in responses if isinstance(item, dict)}
            for request in requests:
                response = response_by_id.get(request["id"], {})
                if response.get("result") is not True:
                    failures[request["id"]] = response.get("error", {}).get("message", "rejected")
        return failures

    def current_media_path(self) -> str:
        player = xbmc.Player()
        try:
            if player.isPlayingVideo():
                return player.getPlayingFile()
        except RuntimeError:
            pass
        return ""

    def current_resolution(self) -> Resolution:
        return self.storage.resolve(self.current_media_path())

    def apply_resolution(
        self,
        resolution: Resolution,
        notify: bool = False,
        ignore_unsupported: bool = False,
    ) -> Dict[str, str]:
        failures = self.apply_style(resolution.properties)
        if ignore_unsupported:
            failures = {setting_id: reason for setting_id, reason in failures.items() if reason != "unsupported"}
        self.publish_resolution(resolution)
        if notify and not failures:
            name = resolution.preset.name if resolution.preset else "Custom style"
            self.notify("Applied: " + name)
        return failures

    def publish_resolution(self, resolution: Resolution) -> None:
        window = xbmcgui.Window(10000)
        name = resolution.preset.name if resolution.preset else ("Custom style" if resolution.properties else "None")
        if resolution.overrides_count:
            name += " (Customized)"
        window.setProperty(PROPERTY_PREFIX + "ActiveName", name)
        window.setProperty(PROPERTY_PREFIX + "Source", resolution.source)
        window.setProperty(PROPERTY_PREFIX + "Overrides", str(resolution.overrides_count))
        if resolution.assignment:
            window.setProperty(PROPERTY_PREFIX + "AssignedTo", safe_path_label(resolution.assignment.path))
        else:
            window.clearProperty(PROPERTY_PREFIX + "AssignedTo")

    def path_is_assignable(self, path: str) -> bool:
        return is_stable_media_path(path)

    def current_directory(self) -> str:
        return directory_for(self.current_media_path())

    def safe_current_label(self) -> str:
        return safe_path_label(normalize_path(self.current_media_path()))

    def open_original_settings(self) -> None:
        xbmc.executebuiltin("ActivateWindow(osdsubtitlesettings)")

    def export_path(self) -> str:
        return os.path.join(self.profile_path, "subtitle-profiles-export.json")

    def backup_path(self) -> str:
        return os.path.join(self.profile_path, "profiles-backup.db")

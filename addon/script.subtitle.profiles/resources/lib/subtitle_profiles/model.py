from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable


KODI_SETTING_IDS = {
    "font": "subtitles.fontname",
    "font_size": "subtitles.fontsize",
    "font_style": "subtitles.style",
    "text_color": "subtitles.colorpick",
    "text_opacity": "subtitles.opacity",
    "background_type": "subtitles.backgroundtype",
    "background_color": "subtitles.bgcolorpick",
    "background_opacity": "subtitles.bgopacity",
    "border_size": "subtitles.bordersize",
    "border_color": "subtitles.bordercolorpick",
    "shadow_color": "subtitles.shadowcolor",
    "shadow_opacity": "subtitles.shadowopacity",
    "shadow_size": "subtitles.shadowsize",
    "blur": "subtitles.blur",
    "line_spacing": "subtitles.linespacing",
    "alignment": "subtitles.align",
    "margin_vertical": "subtitles.marginvertical",
    "override_fonts": "subtitles.overridefonts",
    "override_styles": "subtitles.overridestyles",
}

CUSTOM_PROPERTIES = {"vertical_offset_px"}

APPLE_TV_TEMPLATE: Dict[str, Any] = {
    "font": "DEFAULT",
    "font_size": 36,
    "font_style": 0,
    "text_color": "FFFFFFFF",
    "text_opacity": 50,
    "background_type": 2,
    "background_color": "FF000000",
    "background_opacity": 50,
    "border_size": 0,
    "border_color": "FF000000",
    "shadow_color": "FF000000",
    "shadow_opacity": 0,
    "shadow_size": 0,
    "blur": 0,
    "line_spacing": 12,
    "alignment": 2,
    "margin_vertical": 4.95,
    "vertical_offset_px": 0,
    "override_fonts": True,
    "override_styles": 3,
}

FONT_PREFERENCE = (
    "SF Pro Medium",
    "SF Pro Display",
    "SF Pro",
    "Helvetica Neue",
    "Nimbus Sans",
    "Inter",
    "DEFAULT",
)


def merge_properties(base: Dict[str, Any], overrides: Dict[str, Any] | None) -> Dict[str, Any]:
    merged = deepcopy(base)
    if overrides:
        merged.update(deepcopy(overrides))
    return merged


def property_diff(base: Dict[str, Any], modified: Dict[str, Any]) -> Dict[str, Any]:
    return {key: deepcopy(value) for key, value in modified.items() if base.get(key) != value}


def filtered_properties(properties: Dict[str, Any], supported: Iterable[str]) -> Dict[str, Any]:
    allowed = set(supported) | CUSTOM_PROPERTIES
    return {key: deepcopy(value) for key, value in properties.items() if key in allowed}


def choose_apple_font(available_fonts: Iterable[str]) -> str:
    fonts = list(available_fonts)
    lowered = {font.casefold(): font for font in fonts}
    for preferred in FONT_PREFERENCE:
        exact = lowered.get(preferred.casefold())
        if exact:
            return exact
        for font in fonts:
            if preferred != "DEFAULT" and preferred.casefold() in font.casefold():
                return font
    return "DEFAULT"


def effective_kodi_values(properties: Dict[str, Any], screen_height: int = 1080) -> Dict[str, Any]:
    values = {}
    for property_name, setting_id in KODI_SETTING_IDS.items():
        if property_name in properties:
            values[setting_id] = properties[property_name]

    if "margin_vertical" in properties:
        height = max(int(screen_height or 1080), 1)
        offset = float(properties.get("vertical_offset_px", 0))
        margin = float(properties["margin_vertical"]) + (offset * 100.0 / height)
        values[KODI_SETTING_IDS["margin_vertical"]] = round(max(0.0, min(50.0, margin)), 2)
    return values

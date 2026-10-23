# Compatibility matrix

| Feature / format | Status | Notes |
|---|---|---|
| SRT and other plain text subtitles | Supported | Kodi/libass applies the selected profile. |
| ASS/SSA | Supported with caveat | Embedded styles are preserved unless override fonts/styles is enabled. |
| WebVTT | Supported with caveat | Kodi 21 supports WebVTT; override behavior follows Kodi's renderer. |
| PGS, VobSub, SUP | Not styleable | Bitmap subtitles cannot use font, color, background, border, or line-spacing profiles. Track selection and visibility remain untouched. |
| TTF fonts | Supported | Place in `special://profile/media/Fonts`, then restart Kodi. |
| OTF fonts | Supported on Kodi 20+ | Restart Kodi after adding/removing fonts. |
| TTC collections | Not exposed by Kodi's subtitle font picker | Extract a licensed face to TTF/OTF first. |
| Live color/opacity/background changes | Supported by JSON-RPC on tested Kodi 21.3 | The add-on reports rejected settings. |
| Live font discovery | Requires Kodi restart | Kodi rebuilds the font list at startup. |
| Vertical offset | Supported through deterministic margin conversion | Pixel value is converted using current screen height. |
| Rounded background corners | Not implemented | Kodi 21 exposes Box and Square Box, not border radius. |
| Plugin/PVR/HTTP transient URLs | Apply once/global only | Automatic file/directory assignment requires a stable local, SMB, or NFS path. |

The add-on probes every known subtitle setting with `Settings.GetSettingValue`. Unsupported settings are omitted from the editor and skipped during application while retaining their values in the profile, so a profile remains portable to a Kodi build that supports more settings. Only values actually rejected by Kodi are reported as failures.

The tested CoreELEC 21.3 Omega nightly does not expose `subtitles.linespacing` through JSON-RPC, even though newer Kodi sources define it. Line spacing is therefore retained in profiles but not applied or shown in the editor on that build.

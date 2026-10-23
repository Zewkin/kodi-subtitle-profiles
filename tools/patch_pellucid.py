#!/usr/bin/env python3
"""Apply or restore the verified PellucidRemix subtitle-menu integration."""

import argparse
import os
import shutil
import time


ORIGINAL_OSD_ACTION = "<onclick>ActivateWindow(osdsubtitlesettings)</onclick>"
LEGACY_OSD_ACTION = "<onclick>RunScript(script.subtitle.profiles)</onclick>"
ORIGINAL_OSD_HIDE = """            <animation type="Conditional" condition="Window.IsActive(osdsubtitlesettings) | Window.IsActive(seekbar) | Window.IsActive(osdvideosettings) | Window.IsActive(osdaudiosettings) | window.isactive(PVROSDChannels) | window.isactive(subtitlesearch)">"""
PATCHED_OSD_HIDE = """            <animation type="Conditional" condition="Window.IsActive(osdsubtitlesettings) | Window.IsActive(seekbar) | Window.IsActive(osdvideosettings) | Window.IsActive(osdaudiosettings) | window.isactive(PVROSDChannels) | window.isactive(subtitlesearch) | !String.IsEmpty(Window(Home).Property(SubtitleProfiles.DialogOpen))">"""
DIALOG_MARKER = "<!-- Subtitle Profiles menu item -->"
DIALOG_ANCHOR = """            </control>
            <control type="button" id="7">"""
GROUP_NAVIGATION = """                <onup>5</onup>
                <ondown>5</ondown>"""
PATCHED_GROUP_NAVIGATION = """                <onup>5</onup>
                <ondown condition="Window.IsActive(osdsubtitlesettings)">40</ondown>
                <ondown>5</ondown>"""
WRAPPED_GROUP_NAVIGATION = """                <onup condition="Window.IsActive(osdsubtitlesettings)">40</onup>
                <onup>5</onup>
                <ondown condition="Window.IsActive(osdsubtitlesettings)">40</ondown>
                <ondown>5</ondown>"""
DIALOG_ITEM = """            <!-- Subtitle Profiles menu item -->
            <control type="button" id="40">
                <visible>Window.IsActive(osdsubtitlesettings)</visible>
                <posx>0</posx>
                <posy>738</posy>
                <width>12-col</width>
                <height>2-row</height>
                <label>Subtitle profiles</label>
                <textoffsetx>24</textoffsetx>
                <onup>5</onup>
                <ondown>5</ondown>
                <onright>9000</onright>
                <onclick>Dialog.Close(osdsubtitlesettings,true)</onclick>
                <onclick>RunScript(script.subtitle.profiles)</onclick>
            </control>
"""


def write_with_backup(target: str, content: str, stamp: str) -> str:
    backup = target + ".subtitle-profiles-backup-" + stamp
    shutil.copy2(target, backup)
    temporary = target + ".subtitle-profiles.tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, target)
    return backup


def apply(target: str) -> str:
    skin_dir = target if os.path.isdir(target) else os.path.dirname(target)
    video_osd = os.path.join(skin_dir, "VideoOSD.xml")
    dialog_settings = os.path.join(skin_dir, "DialogSettings.xml")
    with open(video_osd, "r", encoding="utf-8") as handle:
        video_content = handle.read()
    with open(dialog_settings, "r", encoding="utf-8") as handle:
        dialog_content = handle.read()

    if video_content.count(LEGACY_OSD_ACTION) > 1 or video_content.count(ORIGINAL_OSD_ACTION) != 1:
        if video_content.count(LEGACY_OSD_ACTION) != 1:
            raise RuntimeError("Unexpected VideoOSD subtitle action; refusing to patch")
        video_content = video_content.replace(LEGACY_OSD_ACTION, ORIGINAL_OSD_ACTION, 1)
    if PATCHED_OSD_HIDE not in video_content:
        if video_content.count(ORIGINAL_OSD_HIDE) != 1:
            raise RuntimeError("Unexpected VideoOSD visibility condition; refusing to patch")
        video_content = video_content.replace(ORIGINAL_OSD_HIDE, PATCHED_OSD_HIDE, 1)

    new_item_present = DIALOG_ITEM in dialog_content
    if DIALOG_MARKER in dialog_content and not new_item_present:
        marker_start = dialog_content.index(DIALOG_MARKER)
        item_start = dialog_content.rfind("\n", 0, marker_start) + 1
        if dialog_content.startswith("            <!--", item_start):
            closing = "            </control>\n"
        elif dialog_content.startswith("                    <!--", item_start):
            closing = "                    </item>\n"
        else:
            closing = ""
        item_end = dialog_content.find(closing, marker_start) if closing else -1
        if item_start < 0 or item_end < 0:
            raise RuntimeError("Unexpected existing Subtitle Profiles menu item; refusing to patch")
        item_end += len(closing)
        dialog_content = dialog_content[:item_start] + dialog_content[item_end:]
    if WRAPPED_GROUP_NAVIGATION not in dialog_content:
        if PATCHED_GROUP_NAVIGATION in dialog_content:
            dialog_content = dialog_content.replace(PATCHED_GROUP_NAVIGATION, WRAPPED_GROUP_NAVIGATION, 1)
        elif dialog_content.count(GROUP_NAVIGATION) == 1:
            dialog_content = dialog_content.replace(GROUP_NAVIGATION, WRAPPED_GROUP_NAVIGATION, 1)
        else:
            raise RuntimeError("Unexpected settings-list navigation; refusing to patch")
    if not new_item_present:
        if dialog_content.count(DIALOG_ANCHOR) != 1:
            raise RuntimeError("Unexpected DialogSettings content; refusing to patch")
        dialog_content = dialog_content.replace(DIALOG_ANCHOR, "            </control>\n" + DIALOG_ITEM + "            <control type=\"button\" id=\"7\">", 1)
    dialog_content = dialog_content.replace("<height>768</height>", "<height>852</height>", 2)

    stamp = time.strftime("%Y%m%d-%H%M%S")
    backups = []
    with open(video_osd, "r", encoding="utf-8") as handle:
        if handle.read() != video_content:
            backups.append(write_with_backup(video_osd, video_content, stamp))
    with open(dialog_settings, "r", encoding="utf-8") as handle:
        if handle.read() != dialog_content:
            backups.append(write_with_backup(dialog_settings, dialog_content, stamp))
    return "\n".join(backups) if backups else "already patched"


def restore(target: str, backup: str) -> str:
    if not os.path.isfile(backup):
        raise RuntimeError("Backup does not exist: " + backup)
    shutil.copy2(backup, target)
    return target


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", help="Path to Pellucid 1080i directory or VideoOSD.xml")
    parser.add_argument("--restore", metavar="BACKUP")
    args = parser.parse_args()
    result = restore(args.target, args.restore) if args.restore else apply(args.target)
    print(result)


if __name__ == "__main__":
    main()

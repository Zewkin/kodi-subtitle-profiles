# Uninstallation and rollback

## Remove only the OSD integration

Restore the timestamped `DialogSettings.xml.subtitle-profiles-backup-*` file using `tools/patch_pellucid.py --restore`, then run `kodi-send --action=ReloadSkin`. If the installation was migrated from the older direct-button integration, restore the pre-integration `VideoOSD.xml` backup as well.

## Remove the add-on and keep data

Uninstall **Subtitle Profiles** in Kodi and leave its profile directory when asked. Kodi subtitle appearance remains at the last applied values; use Kodi's original subtitle settings to change them.

## Remove all add-on data

After uninstalling, remove only:

`special://profile/addon_data/script.subtitle.profiles/`

This deletes profiles and assignments but does not touch the media library, subtitle tracks, or unrelated Kodi settings.

## Restore the pre-install database

The UI's **Create Database Backup** writes `profiles-backup.db` in the add-on profile directory. Stop Kodi before replacing `profiles.db` with a backup.

from __future__ import annotations

import threading
import time

import xbmc
import xbmcgui

from .kodi_runtime import KodiRuntime


class PlaybackObserver(xbmc.Player):
    def __init__(self, wake_event: threading.Event):
        super().__init__()
        self.wake_event = wake_event

    def onAVStarted(self):
        self.wake_event.set()

    def onAVChange(self):
        if self.isPlayingVideo():
            self.wake_event.set()


def run_service() -> None:
    monitor = xbmc.Monitor()
    wake_event = threading.Event()
    observer = PlaybackObserver(wake_event)
    runtime = KodiRuntime()
    home = xbmcgui.Window(10000)
    home.setProperty("SubtitleProfiles.ServiceRunning", "true")
    runtime.log("Service started")
    last_path = ""
    was_playing = False
    stopped_since = None

    if observer.isPlayingVideo():
        wake_event.set()

    while not monitor.abortRequested():
        # waitForAbort is also the supported yield point through which Kodi
        # dispatches Python player callbacks to this interpreter.
        if monitor.waitForAbort(0.25):
            break

        # Some CoreELEC/Kodi builds do not consistently deliver Player
        # callbacks to long-running Python services. Polling is deliberately
        # kept as a fallback so playback start and file changes are still
        # detected without repeatedly applying a profile.
        playing = observer.isPlayingVideo()
        polled_path = runtime.current_media_path() if playing else ""
        now = time.monotonic()

        if not playing:
            wake_event.clear()
            if was_playing or stopped_since is None:
                stopped_since = now
            elif now - stopped_since >= 2.0:
                # A sustained stop marks the end of the playback session.
                # A brief false state during a skin reload must not do this.
                last_path = ""
            was_playing = False
            continue

        stopped_since = None
        was_playing = True

        # Live edits own subtitle settings while the add-on UI is open.
        # Discard noisy AV-change callbacks instead of overwriting the
        # working copy with its saved preset.
        if home.getProperty("SubtitleProfiles.DialogOpen"):
            wake_event.clear()
            if polled_path:
                # The service may have been restarted while the editor was
                # already open. Treat its current path as handled so closing
                # the editor cannot immediately overwrite the working copy.
                last_path = polled_path
            continue

        if polled_path and polled_path != last_path:
            wake_event.set()

        if wake_event.is_set():
            wake_event.clear()
            if monitor.waitForAbort(0.35):
                break
            if home.getProperty("SubtitleProfiles.DialogOpen"):
                continue
            path = runtime.current_media_path()
            # onAVChange is also emitted for subtitle/UI changes on some
            # CoreELEC builds. A profile is applied at most once per path in
            # a continuous playback session.
            if not path or path == last_path:
                continue
            resolution = runtime.storage.resolve(path)
            notifications = runtime.addon.getSetting("notifications").strip().lower() not in ("", "false", "0", "no")
            failures = runtime.apply_resolution(
                resolution,
                notify=notifications,
                ignore_unsupported=True,
            )
            if failures:
                runtime.log("Some subtitle settings were not applied: " + ", ".join(sorted(failures)), xbmc.LOGWARNING)
            else:
                name = resolution.preset.name if resolution.preset else "Custom style"
                runtime.log("Applied %s from %s" % (name, resolution.source))
            last_path = path
    home.clearProperty("SubtitleProfiles.ServiceRunning")
    runtime.log("Service stopped")

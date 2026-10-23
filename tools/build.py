#!/usr/bin/env python3

import os
import zipfile


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ADDON_ROOT = os.path.join(ROOT, "addon", "script.subtitle.profiles")
DIST = os.path.join(ROOT, "dist")
VERSION = "0.1.0"


def build() -> str:
    os.makedirs(DIST, exist_ok=True)
    output = os.path.join(DIST, f"script.subtitle.profiles-{VERSION}.zip")
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for directory, names, files in os.walk(ADDON_ROOT):
            names[:] = sorted(name for name in names if name != "__pycache__")
            for filename in sorted(files):
                if filename.endswith((".pyc", ".pyo")):
                    continue
                path = os.path.join(directory, filename)
                relative = os.path.relpath(path, os.path.dirname(ADDON_ROOT))
                archive.write(path, relative)
    return output


if __name__ == "__main__":
    print(build())

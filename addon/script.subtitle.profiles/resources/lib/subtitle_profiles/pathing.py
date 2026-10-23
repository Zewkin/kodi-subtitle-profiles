from __future__ import annotations

import posixpath
import re
from urllib.parse import SplitResult, urlsplit, urlunsplit


STABLE_SCHEMES = {"", "file", "smb", "nfs"}
UNSTABLE_SCHEMES = {"plugin", "pvr", "http", "https", "rtmp", "rtsp", "upnp"}


def _clean_netloc(parts: SplitResult) -> str:
    host_port = parts.netloc.rsplit("@", 1)[-1]
    return host_port.casefold()


def normalize_path(path: str, directory: bool = False) -> str:
    raw = (path or "").strip().replace("\\", "/")
    if not raw:
        return ""

    parts = urlsplit(raw)
    scheme = parts.scheme.casefold()
    if scheme:
        normalized_path = posixpath.normpath("/" + parts.path.lstrip("/"))
        if parts.path.endswith("/") and normalized_path != "/":
            normalized_path += "/"
        normalized = urlunsplit((scheme, _clean_netloc(parts), normalized_path, "", ""))
    else:
        prefix = "/" if raw.startswith("/") else ""
        normalized = prefix + posixpath.normpath(raw).lstrip("/")

    if directory:
        return normalized.rstrip("/") + "/"
    return normalized.rstrip("/") if normalized != "/" else normalized


def directory_for(path: str) -> str:
    normalized = normalize_path(path)
    if not normalized:
        return ""
    if "://" in normalized:
        parts = urlsplit(normalized)
        parent = posixpath.dirname(parts.path)
        return normalize_path(urlunsplit((parts.scheme, parts.netloc, parent, "", "")), directory=True)
    return normalize_path(posixpath.dirname(normalized), directory=True)


def is_stable_media_path(path: str) -> bool:
    raw = (path or "").strip()
    if not raw:
        return False
    scheme = urlsplit(raw).scheme.casefold()
    if scheme in UNSTABLE_SCHEMES:
        return False
    return scheme in STABLE_SCHEMES


def directory_matches(file_path: str, directory_path: str, recursive: bool) -> bool:
    file_directory = directory_for(file_path)
    candidate = normalize_path(directory_path, directory=True)
    if not file_directory or not candidate:
        return False
    if recursive:
        return file_directory.startswith(candidate)
    return file_directory == candidate


def safe_path_label(path: str) -> str:
    """Return a credential-free path suitable for UI; never use the original URL."""
    normalized = normalize_path(path)
    return re.sub(r"([?&](?:password|pass|token)=)[^&]+", r"\1***", normalized, flags=re.I)

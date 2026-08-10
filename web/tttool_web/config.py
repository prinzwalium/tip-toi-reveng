"""Configuration for the tttool web GUI, all driven by environment variables."""

import os
from pathlib import Path


def _bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


class Config:
    #: Where all projects live. One sub directory per project.
    DATA_DIR = Path(os.environ.get("TTTOOL_WEB_DATA", "/data")).resolve()

    #: The tttool binary. Looked up in $PATH if it is not an absolute path.
    TTTOOL_BIN = os.environ.get("TTTOOL_BIN", "tttool")

    #: Hard limit for a single tttool run, in seconds.
    RUN_TIMEOUT = _int("TTTOOL_WEB_TIMEOUT", 300)

    #: Maximum size of an upload request, in megabytes.
    MAX_UPLOAD_MB = _int("TTTOOL_WEB_MAX_UPLOAD_MB", 512)

    #: How much of stdout/stderr we hand to the browser, in bytes.
    MAX_OUTPUT_BYTES = _int("TTTOOL_WEB_MAX_OUTPUT_BYTES", 512 * 1024)

    #: Optional HTTP basic auth. Both must be set for auth to be enabled.
    AUTH_USER = os.environ.get("TTTOOL_WEB_USER", "")
    AUTH_PASSWORD = os.environ.get("TTTOOL_WEB_PASSWORD", "")

    #: Stamped into the image at build time: the branch or tag it was built
    #: from and the commit. Empty when running straight from a checkout.
    BUILD_REF = os.environ.get("TTTOOL_WEB_BUILD_REF", "")
    BUILD_SHA = os.environ.get("TTTOOL_WEB_BUILD_SHA", "")[:7]

    #: Allow deleting projects and files through the UI.
    ALLOW_DELETE = _bool("TTTOOL_WEB_ALLOW_DELETE", True)

    #: ffmpeg is used for the "convert to Tiptoi audio" helper.
    FFMPEG_BIN = os.environ.get("FFMPEG_BIN", "ffmpeg")

    #: Files copied into a project created with "start from the example book".
    EXAMPLES_DIR = Path(os.environ.get("TTTOOL_WEB_EXAMPLES", "/app/examples"))

    @property
    def examples_available(self) -> bool:
        return self.EXAMPLES_DIR.is_dir()

    @property
    def auth_enabled(self) -> bool:
        return bool(self.AUTH_USER and self.AUTH_PASSWORD)

    @property
    def build(self) -> str:
        """Human readable build id, e.g. "beta (a1b2c3d)" or "" for a checkout."""
        if self.BUILD_REF and self.BUILD_SHA:
            return f"{self.BUILD_REF} ({self.BUILD_SHA})"
        return self.BUILD_REF or self.BUILD_SHA


config = Config()

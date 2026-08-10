"""Project (workspace) handling.

A project is a plain directory below ``config.DATA_DIR``.  Everything the user
uploads or tttool produces lives in there, so a project can simply be zipped up
and taken elsewhere.
"""

import re
import shutil
import tempfile
import time
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .config import config

PROJECT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

#: Files we never show, offer for download or pack into an archive.
HIDDEN_NAMES = {".", "..", ".git"}

TEXT_SUFFIXES = {".yaml", ".yml", ".txt", ".md", ".csv", ".json", ".svg", ".log", ".semantic"}
IMAGE_SUFFIXES = {".png", ".svg", ".jpg", ".jpeg", ".gif"}
AUDIO_SUFFIXES = {".ogg", ".wav", ".mp3", ".flac", ".m4a", ".aac", ".opus"}


class ProjectError(Exception):
    """Anything the user did wrong; the message is shown in the UI."""


def sanitize_filename(name: str) -> str:
    """Turn an arbitrary (browser supplied) file name into a safe basename."""
    name = unicodedata.normalize("NFC", name or "")
    # Browsers may send a full path (IE) or a relative one (directory upload).
    name = name.replace("\\", "/").split("/")[-1]
    name = "".join(ch for ch in name if ch.isprintable() and ch not in '<>:"|?*')
    name = name.strip().strip(".")
    if not name:
        raise ProjectError("Invalid file name")
    return name[:120]


def slug(title: str, fallback: str = "buch") -> str:
    """A project directory name derived from a title the user typed."""
    slugged = re.sub(r"[^A-Za-z0-9]+", "-", title or "").strip("-").lower()
    return slugged[:48] or fallback


def unique_name(title: str) -> str:
    """A slug of ``title`` that no project uses yet."""
    taken = {entry["name"] for entry in list_projects()}
    base = slug(title)
    name, suffix = base, 2
    while name in taken:
        name, suffix = f"{base}-{suffix}", suffix + 1
    return name


def sanitize_relpath(relpath: str) -> str:
    """Sanitize a user supplied *relative* path (may contain sub directories)."""
    relpath = (relpath or "").replace("\\", "/")
    parts = [sanitize_filename(p) for p in relpath.split("/") if p not in ("", ".")]
    if not parts:
        raise ProjectError("Empty path")
    return "/".join(parts)


@dataclass(frozen=True)
class FileEntry:
    relpath: str
    size: int
    mtime: float
    is_dir: bool

    @property
    def name(self) -> str:
        return self.relpath.rsplit("/", 1)[-1]

    @property
    def suffix(self) -> str:
        return Path(self.relpath).suffix.lower()

    @property
    def kind(self) -> str:
        if self.is_dir:
            return "dir"
        suffix = self.suffix
        if suffix in IMAGE_SUFFIXES:
            return "image"
        if suffix in AUDIO_SUFFIXES:
            return "audio"
        if suffix in TEXT_SUFFIXES:
            return "text"
        if suffix == ".gme":
            return "gme"
        if suffix == ".pdf":
            return "pdf"
        return "binary"

    @property
    def editable(self) -> bool:
        return self.kind == "text" and self.size <= 2 * 1024 * 1024

    @property
    def mtime_str(self) -> str:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(self.mtime))

    @property
    def size_str(self) -> str:
        return human_size(self.size)


def human_size(size: int) -> str:
    step = 1024.0
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < step or unit == "GiB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= step
    return f"{value:.1f} GiB"


class Project:
    def __init__(self, name: str):
        if not PROJECT_NAME_RE.match(name or ""):
            raise ProjectError(
                "Project names may only contain letters, digits, '.', '_' and '-' "
                "(max 64 characters, starting with a letter or digit)."
            )
        self.name = name
        self.path = (config.DATA_DIR / name).resolve()
        if self.path.parent != config.DATA_DIR:
            raise ProjectError("Invalid project name")

    # -- lifecycle ---------------------------------------------------------

    @property
    def exists(self) -> bool:
        return self.path.is_dir()

    def require(self) -> "Project":
        if not self.exists:
            raise ProjectError(f"No such project: {self.name}")
        return self

    def create(self) -> "Project":
        if self.exists:
            raise ProjectError(f"Project {self.name} already exists")
        self.path.mkdir(parents=True)
        return self

    def delete(self) -> None:
        self.require()
        shutil.rmtree(self.path)

    # -- paths -------------------------------------------------------------

    def resolve(self, relpath: str, must_exist: bool = True) -> Path:
        """Resolve a relative path inside the project, refusing to escape it."""
        rel = sanitize_relpath(relpath)
        candidate = (self.path / rel).resolve()
        if candidate != self.path and self.path not in candidate.parents:
            raise ProjectError("Path outside of the project")
        if must_exist and not candidate.exists():
            raise ProjectError(f"No such file: {rel}")
        return candidate

    def relpath_of(self, path: Path) -> str:
        return path.resolve().relative_to(self.path).as_posix()

    # -- contents ----------------------------------------------------------

    def files(self, limit: int = 5000) -> list[FileEntry]:
        entries: list[FileEntry] = []
        for path in sorted(self.path.rglob("*"), key=lambda p: p.as_posix().lower()):
            if any(part in HIDDEN_NAMES or part.startswith(".") for part in path.relative_to(self.path).parts):
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            entries.append(
                FileEntry(
                    relpath=self.relpath_of(path),
                    size=0 if path.is_dir() else stat.st_size,
                    mtime=stat.st_mtime,
                    is_dir=path.is_dir(),
                )
            )
            if len(entries) >= limit:
                break
        return entries

    def snapshot(self) -> dict[str, tuple[float, int]]:
        """Cheap fingerprint of the project, used to report what a run changed."""
        return {e.relpath: (e.mtime, e.size) for e in self.files() if not e.is_dir}

    def total_size(self) -> int:
        return sum(e.size for e in self.files())

    def save_upload(self, filename: str, stream, subdir: str = "") -> str:
        name = sanitize_filename(filename)
        target_dir = self.path if not subdir.strip() else self.resolve(subdir, must_exist=False)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / name
        # Do not let an upload clobber a directory.
        if target.is_dir():
            raise ProjectError(f"{name} is a directory")
        if hasattr(stream, "save"):  # a werkzeug FileStorage
            stream.save(target)
        else:
            target.write_bytes(stream.read())
        return self.relpath_of(target)

    def write_text(self, relpath: str, content: str) -> str:
        target = self.resolve(relpath, must_exist=False)
        if target.is_dir():
            raise ProjectError("Cannot write to a directory")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return self.relpath_of(target)

    def read_text(self, relpath: str) -> str:
        path = self.resolve(relpath)
        if path.is_dir():
            raise ProjectError("Cannot read a directory")
        return path.read_text(encoding="utf-8", errors="replace")

    def delete_file(self, relpath: str) -> None:
        path = self.resolve(relpath)
        if path == self.path:
            raise ProjectError("Refusing to delete the project root")
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()

    def archive(self) -> tempfile.SpooledTemporaryFile:
        # Spooled: small projects stay in memory, big ones end up on disk.
        buffer = tempfile.SpooledTemporaryFile(max_size=32 * 1024 * 1024)
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for entry in self.files():
                if entry.is_dir:
                    continue
                zf.write(self.path / entry.relpath, f"{self.name}/{entry.relpath}")
        buffer.seek(0)
        return buffer


def list_projects() -> list[dict]:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    projects = []
    for path in sorted(config.DATA_DIR.iterdir(), key=lambda p: p.name.lower()):
        if not path.is_dir() or path.name.startswith("."):
            continue
        try:
            project = Project(path.name)
        except ProjectError:
            continue
        files = [e for e in project.files() if not e.is_dir]
        projects.append(
            {
                "name": project.name,
                "files": len(files),
                "size": human_size(sum(e.size for e in files)),
                "mtime": time.strftime("%Y-%m-%d %H:%M", time.localtime(path.stat().st_mtime)),
            }
        )
    return projects

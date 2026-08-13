"""Export and import a whole book as a single file.

A book is a directory of pictures, sounds and a JSON model, which makes it
awkward to hand to someone else. Export packs exactly the parts that *are* the
book — the model, the page pictures, the sounds, and the code assignment — into
one file; import unpacks it into a new book on this server.

Everything tttool generates (the GME file, the print PDFs, the YAML) is left
out: it is rebuilt from the parts in seconds, and it is the largest thing in the
directory.

Nothing from the archive is ever written to a path that came out of the
archive. Both the model and every file name are rebuilt from the book itself,
so a hand-crafted archive can at worst produce a nonsensical book, never a file
outside its own project.
"""

import io
import json
import zipfile
from dataclasses import asdict
from pathlib import Path

from . import __version__
from .book import PAPER_SIZES, Book
from .bookbuild import YAML_FILE
from .config import config
from .i18n import t
from .pictures import make_preview
from .projects import Project, ProjectError, unique_name

#: The extension of an exported book. It is a ZIP file underneath, but the name
#: says what it is, and “open with” on a desktop should not offer an unpacker.
EXPORT_SUFFIX = ".tiptoi"

#: What import accepts. People rename things, and a ZIP really is a ZIP.
IMPORT_SUFFIXES = (EXPORT_SUFFIX, ".zip")

#: Marks our archives, so an unrelated ZIP is rejected with a clear message.
MANIFEST_NAME = "tiptoi-buch.json"
MANIFEST_FORMAT = "tttool-web-book"
MANIFEST_VERSION = 1

#: Where tttool remembers which OID code it gave each area. Carried along so a
#: page printed before the export still works with the re-imported book.
CODES_FILE = f"{Path(YAML_FILE).stem}.codes.yaml"

PICTURE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif")
SOUND_SUFFIXES = (".ogg", ".wav", ".mp3")

#: Ceilings for a hostile archive: a small ZIP can unpack to a full disk.
MAX_MEMBERS = 4000
MAX_TOTAL_BYTES = config.MAX_UPLOAD_MB * 4 * 1024 * 1024


def export_name(project: Project) -> str:
    return f"{project.name}{EXPORT_SUFFIX}"


def export_book(project: Project, book: Book, stream) -> None:
    """Write the book to ``stream`` as one archive."""
    manifest = {
        "format": MANIFEST_FORMAT,
        "version": MANIFEST_VERSION,
        "app": __version__,
        "title": book.title,
        "book": book.to_dict(),
    }
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            MANIFEST_NAME, json.dumps(manifest, indent=2, ensure_ascii=False)
        )
        for relpath in _media_paths(book):
            source = project.path / relpath
            if source.is_file():
                archive.write(source, relpath)
        codes = project.path / CODES_FILE
        if codes.is_file():
            archive.write(codes, CODES_FILE)


def _media_paths(book: Book) -> list[str]:
    paths = [page.image for page in book.pages if page.image]
    paths += [sound.file for sound in book.sounds if sound.file]
    return list(dict.fromkeys(paths))


def import_book(upload, title: str = "") -> Project:
    """Create a new book from an uploaded archive; returns the new project."""
    filename = getattr(upload, "filename", "") or ""
    if not filename.lower().endswith(IMPORT_SUFFIXES):
        raise ProjectError(
            t("This is not an exported book (expected a {suffix} file).", suffix=EXPORT_SUFFIX)
        )
    try:
        archive = zipfile.ZipFile(upload)
    except (zipfile.BadZipFile, OSError):
        raise ProjectError(t("This file is damaged and cannot be opened.")) from None

    with archive:
        _check_size(archive)
        book, title = _read_manifest(archive, title)
        project = _create_project(title)
        try:
            _write_media(archive, project, book)
            _copy_codes(archive, project)
            book.save(project)
        except Exception:
            # A half written book is worse than none: it would show up in the
            # list and fail to open.
            project.delete()
            raise
    return project


def _check_size(archive: zipfile.ZipFile) -> None:
    infos = archive.infolist()
    if len(infos) > MAX_MEMBERS:
        raise ProjectError(t("This file contains far too many parts to be a book."))
    if sum(info.file_size for info in infos) > MAX_TOTAL_BYTES:
        raise ProjectError(t("This book is too large for this server."))


def _read_manifest(archive: zipfile.ZipFile, title: str) -> tuple[Book, str]:
    try:
        raw = archive.read(MANIFEST_NAME)
    except KeyError:
        raise ProjectError(t("This file is not an exported book.")) from None
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ProjectError(t("This file is damaged and cannot be opened.")) from None
    if not isinstance(manifest, dict) or manifest.get("format") != MANIFEST_FORMAT:
        raise ProjectError(t("This file is not an exported book."))
    if not isinstance(manifest.get("version"), int) or manifest["version"] > MANIFEST_VERSION:
        raise ProjectError(
            t("This book was exported by a newer version. Please update this server first.")
        )

    data = manifest.get("book")
    if not isinstance(data, dict):
        raise ProjectError(t("This file is damaged and cannot be opened."))
    # from_dict is the same validation new books and browser saves go through:
    # unknown behaviours, dangling sound ids and impossible geometry are all
    # cleaned up there.
    book = Book.from_dict(data)
    if book.paper not in PAPER_SIZES:
        book.paper = Book().paper
    book.title = (title or book.title or str(manifest.get("title") or "")).strip()[:80]
    if not book.title:
        book.title = t("Imported book")
    return book, book.title


def _create_project(title: str) -> Project:
    project = Project(unique_name(title)).create()
    (project.path / "sounds").mkdir(exist_ok=True)
    (project.path / "seiten").mkdir(exist_ok=True)
    return project


def _write_media(archive: zipfile.ZipFile, project: Project, book: Book) -> None:
    """Copy the pictures and sounds across, renaming them to our own scheme."""
    members = {info.filename: info for info in archive.infolist() if not info.is_dir()}

    for page in book.pages:
        page.image = _extract(
            archive, members, project, page.image, "seiten", page.id, PICTURE_SUFFIXES
        )
        # The preview is derived, so it is neither exported nor trusted: the
        # path in the manifest means nothing here. Make a fresh one.
        page.preview = make_preview(project, page.image)
    for sound in book.sounds:
        sound.file = _extract(
            archive, members, project, sound.file, "sounds", sound.id, SOUND_SUFFIXES
        )
    # A sound whose file did not survive would leave silent areas behind that
    # still look like they play something.
    lost = {sound.id for sound in book.sounds if not sound.file}
    if lost:
        book.sounds = [sound for sound in book.sounds if sound.id not in lost]
        for page in book.pages:
            for area in page.areas:
                if area.sound_id in lost:
                    area.sound_id = ""
                area.sound_ids = [s for s in area.sound_ids if s not in lost]


def _extract(
    archive: zipfile.ZipFile,
    members: dict,
    project: Project,
    stored: str,
    subdir: str,
    basename: str,
    allowed: tuple[str, ...],
) -> str:
    """Copy one member out, under a name we choose. Returns the new path."""
    info = members.get(stored)
    if info is None:
        return ""
    suffix = Path(stored).suffix.lower()
    if suffix not in allowed:
        return ""
    relpath = f"{subdir}/{basename}{suffix}"
    target = project.resolve(relpath, must_exist=False)
    target.parent.mkdir(parents=True, exist_ok=True)
    with archive.open(info) as source, open(target, "wb") as out:
        _copy_limited(source, out, info.file_size)
    return project.relpath_of(target)


def _copy_limited(source, out, expected: int) -> None:
    """Copy at most what the directory promised, so a lying header cannot fill the disk."""
    remaining = min(expected, MAX_TOTAL_BYTES)
    while remaining > 0:
        chunk = source.read(min(64 * 1024, remaining))
        if not chunk:
            break
        out.write(chunk)
        remaining -= len(chunk)


def _copy_codes(archive: zipfile.ZipFile, project: Project) -> None:
    try:
        info = archive.getinfo(CODES_FILE)
    except KeyError:
        return
    if info.file_size > 1024 * 1024:
        return
    with archive.open(info) as source:
        text = source.read(1024 * 1024).decode("utf-8", errors="replace")
    (project.path / CODES_FILE).write_text(text, encoding="utf-8")


def is_book_archive(filename: str) -> bool:
    return bool(filename) and filename.lower().endswith(IMPORT_SUFFIXES)


# ----------------------------------------------------------------- everything


#: A backup is the same idea one level up: an archive of book archives.
BACKUP_MANIFEST = "tiptoi-sicherung.json"
BACKUP_FORMAT = "tttool-web-backup"
BACKUP_DIR = "buecher"


def backup_name() -> str:
    from datetime import date

    return f"tiptoi-sicherung-{date.today().isoformat()}{EXPORT_SUFFIX}"


def export_all(books: list[tuple[Project, Book]], stream) -> int:
    """Write every book to ``stream`` as one archive; returns how many."""
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        names = []
        for project, book in books:
            member = f"{BACKUP_DIR}/{project.name}{EXPORT_SUFFIX}"
            # Each book is packed exactly as “pass this one on” packs it, so a
            # backup can be opened with an unzip program and a single book
            # pulled out of it by hand.
            buffer = io.BytesIO()
            export_book(project, book, buffer)
            archive.writestr(member, buffer.getvalue())
            names.append({"name": project.name, "title": book.title, "file": member})
        archive.writestr(
            BACKUP_MANIFEST,
            json.dumps(
                {
                    "format": BACKUP_FORMAT,
                    "version": MANIFEST_VERSION,
                    "app": __version__,
                    "books": names,
                },
                indent=2,
                ensure_ascii=False,
            ),
        )
    return len(books)


def looks_like_backup(upload) -> bool:
    """True for an archive holding several books rather than one."""
    try:
        position = upload.tell()
    except (AttributeError, OSError):
        position = None
    try:
        with zipfile.ZipFile(upload) as archive:
            return BACKUP_MANIFEST in archive.namelist()
    except (zipfile.BadZipFile, OSError):
        return False
    finally:
        if position is not None:
            upload.seek(position)


def import_backup(upload) -> list[Project]:
    """Add every book of a backup; returns the projects that were created."""
    try:
        archive = zipfile.ZipFile(upload)
    except (zipfile.BadZipFile, OSError):
        raise ProjectError(t("This file is damaged and cannot be opened.")) from None

    restored: list[Project] = []
    with archive:
        _check_size(archive)
        members = [
            info
            for info in archive.infolist()
            if not info.is_dir()
            and info.filename.startswith(f"{BACKUP_DIR}/")
            and info.filename.lower().endswith(IMPORT_SUFFIXES)
        ]
        if not members:
            raise ProjectError(t("This backup contains no books."))
        for info in members:
            with archive.open(info) as member:
                # import_book wants something with a name to check; the inner
                # archives are ordinary book files.
                restored.append(import_book(_Named(io.BytesIO(member.read()), info.filename)))
    return restored


class _Named:
    """An in-memory file that answers to ``.filename``, like an upload."""

    def __init__(self, stream, filename: str):
        self._stream = stream
        self.filename = Path(filename).name

    def __getattr__(self, item):
        return getattr(self._stream, item)


__all__ = [
    "EXPORT_SUFFIX",
    "IMPORT_SUFFIXES",
    "export_book",
    "export_name",
    "import_book",
    "is_book_archive",
]

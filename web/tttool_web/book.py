"""The book: pages with a picture, and areas on them that play a sound.

This is the model the editor works on. It is stored as ``book.json`` inside the
project directory and is the source of truth — the YAML file tttool consumes is
generated from it, never the other way round.

All positions and sizes are in millimetres on the printed page, measured from
its top left corner, so that what the editor shows and what is printed cannot
drift apart.
"""

import json
import re
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from .i18n import t
from .projects import Project, ProjectError, sanitize_filename

BOOK_FILE = "book.json"
#: 1 = one sound file per area; 2 = a sound library the areas point into.
FORMAT_VERSION = 2

#: Paper sizes offered in the interface, in millimetres.
PAPER_SIZES: dict[str, tuple[int, int]] = {
    "a4-portrait": (210, 297),
    "a4-landscape": (297, 210),
    "a5-portrait": (148, 210),
    "a5-landscape": (210, 148),
}
DEFAULT_PAPER = "a4-landscape"

#: The pen needs a bit of surface to read a code reliably.
MIN_AREA_MM = 10.0
#: Size and margin of the power-on field that every page carries.
POWER_FIELD_MM = 20.0
POWER_FIELD_MARGIN_MM = 8.0

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif")
ID_RE = re.compile(r"^[a-z][a-z0-9]{0,15}$")
#: Sound paths as written by version 1 of the format: sounds/<area>.ogg
LEGACY_SOUND_RE = re.compile(r"^sounds/[A-Za-z0-9._-]{1,64}\.(ogg|wav|mp3)$")


def _next_id(prefix: str, taken: set[str]) -> str:
    n = 1
    while f"{prefix}{n}" in taken:
        n += 1
    return f"{prefix}{n}"


@dataclass
class Sound:
    """One recording in the book's sound library, usable by several areas."""

    id: str
    name: str = ""
    #: Path inside the project; always the converted Ogg the pen can play.
    file: str = ""
    #: "upload", "record" or "speak" — only used to explain it in the interface.
    source: str = "upload"
    #: For spoken sounds: what was said, so it can be edited and spoken again.
    text: str = ""
    language: str = ""


@dataclass
class Area:
    id: str
    name: str = ""
    x: float = 0.0
    y: float = 0.0
    w: float = 20.0
    h: float = 20.0
    #: "rect" or "poly"; a polygon keeps its corners in ``points``, and x/y/w/h
    #: stay its bounding box so that every check works on both kinds.
    kind: str = "rect"
    points: list[list[float]] = field(default_factory=list)
    #: Which sound of the library plays here; empty while the area is silent.
    sound_id: str = ""

    @property
    def is_polygon(self) -> bool:
        return self.kind == "poly" and len(self.points) >= 3

    def clamp(self, page_w: float, page_h: float) -> None:
        if self.kind == "poly" and self.points:
            self.points = [
                [
                    round(max(0.0, min(float(px), page_w)), 2),
                    round(max(0.0, min(float(py), page_h)), 2),
                ]
                for px, py in self.points
            ]
            if len(self.points) >= 3:
                xs = [p[0] for p in self.points]
                ys = [p[1] for p in self.points]
                self.x, self.y = min(xs), min(ys)
                self.w, self.h = max(max(xs) - self.x, 1.0), max(max(ys) - self.y, 1.0)
                return
            # Too few corners left to be a shape; fall back to its box.
            self.kind, self.points = "rect", []
        self.w = max(1.0, min(round(self.w, 2), page_w))
        self.h = max(1.0, min(round(self.h, 2), page_h))
        self.x = max(0.0, min(round(self.x, 2), page_w - self.w))
        self.y = max(0.0, min(round(self.y, 2), page_h - self.h))

    def move_to(self, x: float, y: float) -> None:
        """Move the whole shape so that its bounding box starts at (x, y)."""
        dx, dy = x - self.x, y - self.y
        self.points = [[px + dx, py + dy] for px, py in self.points]
        self.x, self.y = x, y

    def overlaps(self, other: "Area") -> bool:
        return not (
            self.x + self.w <= other.x
            or other.x + other.w <= self.x
            or self.y + self.h <= other.y
            or other.y + other.h <= self.y
        )


@dataclass
class Page:
    id: str
    name: str = ""
    #: Path of the page picture inside the project, empty while none is set.
    image: str = ""
    areas: list[Area] = field(default_factory=list)

    def area(self, area_id: str) -> Area:
        for area in self.areas:
            if area.id == area_id:
                return area
        raise ProjectError(f"No such area: {area_id}")


@dataclass
class Book:
    title: str = "Mein Buch"
    product_id: int = 42
    paper: str = DEFAULT_PAPER
    pages: list[Page] = field(default_factory=list)
    sounds: list[Sound] = field(default_factory=list)
    version: int = FORMAT_VERSION

    # -- geometry ---------------------------------------------------------

    @property
    def page_size(self) -> tuple[int, int]:
        return PAPER_SIZES.get(self.paper, PAPER_SIZES[DEFAULT_PAPER])

    @property
    def power_field(self) -> tuple[float, float, float, float]:
        """Where the power-on field sits on every page: (x, y, w, h) in mm."""
        _, page_h = self.page_size
        return (
            POWER_FIELD_MARGIN_MM,
            page_h - POWER_FIELD_MARGIN_MM - POWER_FIELD_MM,
            POWER_FIELD_MM,
            POWER_FIELD_MM,
        )

    # -- lookups ----------------------------------------------------------

    def page(self, page_id: str) -> Page:
        for page in self.pages:
            if page.id == page_id:
                return page
        raise ProjectError(f"No such page: {page_id}")

    def sound(self, sound_id: str) -> Sound:
        for sound in self.sounds:
            if sound.id == sound_id:
                return sound
        raise ProjectError(t("This sound is not in the library any more."))

    def add_sound(self, **kwargs) -> Sound:
        sound = Sound(id=_next_id("t", {s.id for s in self.sounds}), **kwargs)
        self.sounds.append(sound)
        return sound

    def sound_usage(self) -> dict[str, int]:
        """How many areas play each sound — shown before deleting one."""
        usage = {sound.id: 0 for sound in self.sounds}
        for page in self.pages:
            for area in page.areas:
                if area.sound_id in usage:
                    usage[area.sound_id] += 1
        return usage

    def area(self, area_id: str) -> tuple[Page, Area]:
        for page in self.pages:
            for area in page.areas:
                if area.id == area_id:
                    return page, area
        raise ProjectError(t("This area no longer exists."))

    def script_name(self, page: Page, area: Area) -> str:
        """The name this area gets in the YAML file, stable over renames."""
        return f"{page.id}_{area.id}"

    def add_page(self, name: str = "") -> Page:
        page = Page(id=_next_id("s", {p.id for p in self.pages}))
        page.name = name or f"Seite {len(self.pages) + 1}"
        self.pages.append(page)
        return page

    def add_area(self, page: Page, **kwargs) -> Area:
        taken = {a.id for p in self.pages for a in p.areas}
        area = Area(id=_next_id("a", taken), **kwargs)
        area.clamp(*self.page_size)
        page.areas.append(area)
        return area

    # -- rearranging ------------------------------------------------------

    def duplicate_area(self, page: Page, area: Area) -> Area:
        page_w, page_h = self.page_size
        copy = replace(area, id=_next_id("a", {a.id for p in self.pages for a in p.areas}))
        copy.points = [list(point) for point in area.points]
        copy.name = f"{area.name} (2)" if area.name else ""
        # Offset a little so the copy is visible on top of the original.
        copy.move_to(min(area.x + 5, max(0.0, page_w - area.w)),
                     min(area.y + 5, max(0.0, page_h - area.h)))
        copy.clamp(page_w, page_h)
        page.areas.append(copy)
        return copy

    def duplicate_page(self, page: Page) -> Page:
        copy = Page(id=_next_id("s", {p.id for p in self.pages}),
                    name=f"{page.name or page.id} (2)", image=page.image)
        taken = {a.id for p in self.pages for a in p.areas}
        for area in page.areas:
            # The sound comes along: one sound of the library can play in as
            # many places as you like.
            new = replace(area, id=_next_id("a", taken))
            new.points = [list(point) for point in area.points]
            taken.add(new.id)
            copy.areas.append(new)
        self.pages.insert(self.pages.index(page) + 1, copy)
        return copy

    def remove_page(self, page_id: str) -> None:
        if len(self.pages) <= 1:
            raise ProjectError(t("A book needs at least one page."))
        self.pages = [p for p in self.pages if p.id != page_id]

    def move_page(self, page_id: str, delta: int) -> None:
        page = self.page(page_id)
        index = self.pages.index(page)
        target = max(0, min(len(self.pages) - 1, index + delta))
        self.pages.insert(target, self.pages.pop(index))

    # -- persistence ------------------------------------------------------

    @classmethod
    def from_dict(cls, data: dict) -> "Book":
        if not isinstance(data, dict):
            raise ProjectError("The book file is damaged")
        book = cls(
            title=str(data.get("title") or "Mein Buch")[:80],
            product_id=int(data.get("product_id") or 42),
            paper=data.get("paper") if data.get("paper") in PAPER_SIZES else DEFAULT_PAPER,
        )
        if not 1 <= book.product_id <= 999:
            raise ProjectError(t("The product number must be between 1 and 999"))
        page_w, page_h = book.page_size
        #: Areas of books written before the library existed, {area id: (path, name)}.
        legacy: dict[str, tuple[str, str]] = {}
        for raw_page in data.get("pages") or []:
            page = Page(
                id=str(raw_page.get("id") or ""),
                name=str(raw_page.get("name") or "")[:80],
                image=str(raw_page.get("image") or ""),
            )
            if not ID_RE.match(page.id):
                page.id = _next_id("s", {p.id for p in book.pages})
            for raw_area in raw_page.get("areas") or []:
                points = raw_area.get("points") or []
                legacy_sound = str(raw_area.get("sound") or "")
                area = Area(
                    id=str(raw_area.get("id") or ""),
                    name=str(raw_area.get("name") or "")[:80],
                    x=float(raw_area.get("x") or 0),
                    y=float(raw_area.get("y") or 0),
                    w=float(raw_area.get("w") or 20),
                    h=float(raw_area.get("h") or 20),
                    kind="poly" if raw_area.get("kind") == "poly" else "rect",
                    points=[
                        [float(p[0]), float(p[1])]
                        for p in points[:200]
                        if isinstance(p, (list, tuple)) and len(p) == 2
                    ],
                    sound_id=str(raw_area.get("sound_id") or ""),
                )
                if not ID_RE.match(area.id):
                    area.id = _next_id("a", {a.id for p in book.pages for a in p.areas})
                area.clamp(page_w, page_h)
                # Only a path this program wrote itself may be adopted; the
                # field also arrives from the browser, which must not be able
                # to point a sound anywhere it likes.
                if legacy_sound and LEGACY_SOUND_RE.match(legacy_sound):
                    legacy[area.id] = (legacy_sound, str(raw_area.get("sound_name") or ""))
                page.areas.append(area)
            book.pages.append(page)

        for raw_sound in data.get("sounds") or []:
            sound = Sound(
                id=str(raw_sound.get("id") or ""),
                name=str(raw_sound.get("name") or "")[:120],
                file=str(raw_sound.get("file") or ""),
                source=str(raw_sound.get("source") or "upload")[:16],
                text=str(raw_sound.get("text") or "")[:500],
                language=str(raw_sound.get("language") or "")[:16],
            )
            if ID_RE.match(sound.id) and sound.file:
                book.sounds.append(sound)

        # Books written before the library existed carried the file on the area.
        for page in book.pages:
            for area in page.areas:
                if area.id not in legacy:
                    continue
                path, name = legacy[area.id]
                existing = next((s for s in book.sounds if s.file == path), None)
                if existing is None:
                    existing = Sound(
                        id=_next_id("t", {s.id for s in book.sounds}),
                        name=name or Path(path).stem,
                        file=path,
                    )
                    book.sounds.append(existing)
                area.sound_id = existing.id

        known = {s.id for s in book.sounds}
        for page in book.pages:
            for area in page.areas:
                if area.sound_id not in known:
                    area.sound_id = ""

        if not book.pages:
            book.add_page()
        return book

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def load(cls, project: Project) -> "Book":
        path = project.path / BOOK_FILE
        if not path.is_file():
            raise ProjectError("This project is not a book")
        try:
            return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError as exc:
            raise ProjectError(f"The book file is damaged: {exc}") from None

    def save(self, project: Project) -> None:
        path = project.path / BOOK_FILE
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def is_book(project: Project) -> bool:
        return (project.path / BOOK_FILE).is_file()

    # -- checks -----------------------------------------------------------

    #: Below this average brightness (0–255) the dots drown in the artwork.
    DARK_LIMIT = 110

    def dark_area_hints(self, project: Project) -> list[str]:
        """Warn about areas whose artwork is too dark for the pen to read."""
        try:
            from PIL import Image
        except ImportError:
            return []

        hints: list[str] = []
        page_w, page_h = self.page_size
        for page in self.pages:
            if not page.image:
                continue
            path = project.path / page.image
            if not path.is_file():
                continue
            try:
                with Image.open(path) as picture:
                    grey = picture.convert("L")
                    image_w, image_h = grey.size
                    ox, oy, fitted_w, fitted_h = fitted_image_rect(
                        page_w, page_h, image_w, image_h
                    )
                    if fitted_w <= 0 or fitted_h <= 0:
                        continue
                    for area in page.areas:
                        if not area.sound_id:
                            continue
                        left = (area.x - ox) / fitted_w * image_w
                        top = (area.y - oy) / fitted_h * image_h
                        right = (area.x + area.w - ox) / fitted_w * image_w
                        bottom = (area.y + area.h - oy) / fitted_h * image_h
                        box = (
                            int(max(0, min(left, image_w - 1))),
                            int(max(0, min(top, image_h - 1))),
                            int(max(1, min(right, image_w))),
                            int(max(1, min(bottom, image_h))),
                        )
                        if box[2] <= box[0] or box[3] <= box[1]:
                            continue
                        # One byte per pixel in "L" mode, so this is the mean.
                        pixels = grey.crop(box).resize((16, 16)).tobytes()
                        brightness = sum(pixels) / len(pixels)
                        if brightness < self.DARK_LIMIT:
                            hints.append(
                                t("“{name}” on “{label}” sits on a dark part of the picture — "
                                  "the pen may not read the dots there.",
                                  name=area.name or t("Unnamed area"),
                                  label=page.name or page.id)
                            )
            except OSError:
                continue
        return hints

    def check(self) -> tuple[list[str], list[str]]:
        """Return (problems, hints) in plain language, ready to show."""
        problems: list[str] = []
        hints: list[str] = []
        px, py, pw, ph = self.power_field
        power = Area(id="power", x=px, y=py, w=pw, h=ph)

        for page in self.pages:
            label = page.name or page.id
            if not page.image:
                hints.append(
                    t("“{label}” has no picture yet — the codes will be printed on a blank page.",
                      label=label)
                )
            if not [a for a in page.areas if a.sound_id]:
                problems.append(t("“{label}” has no area with a sound yet.", label=label))
            for area in page.areas:
                name = area.name or t("Unnamed area")
                if not area.sound_id:
                    hints.append(
                        t("“{name}” on “{label}” has no sound and is left out.",
                          name=name, label=label)
                    )
                if area.w < MIN_AREA_MM or area.h < MIN_AREA_MM:
                    hints.append(
                        t("“{name}” on “{label}” is smaller than {size} mm — "
                          "the pen may not read it reliably.",
                          name=name, label=label, size=f"{MIN_AREA_MM:.0f}")
                    )
                if area.overlaps(power):
                    hints.append(
                        t("“{name}” on “{label}” lies on the power-on field and will not work there.",
                          name=name, label=label)
                    )
            for i, area in enumerate(page.areas):
                for other in page.areas[i + 1 :]:
                    if area.overlaps(other):
                        hints.append(
                            t("“{first}” and “{second}” on “{label}” overlap; "
                              "the pen will react to only one of them.",
                              first=area.name or area.id, second=other.name or other.id, label=label)
                        )
                        break
        return problems, hints


def fitted_image_rect(
    page_w: float, page_h: float, image_w: int, image_h: int
) -> tuple[float, float, float, float]:
    """Where a picture lands on the page, in mm.

    The same “contain and centre” fit is used by the editor, the printed page
    and the check for artwork that is too dark, so the three cannot disagree.
    """
    if image_w <= 0 or image_h <= 0:
        return 0.0, 0.0, page_w, page_h
    scale = min(page_w / image_w, page_h / image_h)
    width, height = image_w * scale, image_h * scale
    return (page_w - width) / 2, (page_h - height) / 2, width, height


def store_upload(project: Project, subdir: str, basename: str, upload) -> tuple[str, str]:
    """Save an upload as <subdir>/<basename><ext>; returns (path, original name)."""
    original = sanitize_filename(upload.filename)
    suffix = Path(original).suffix.lower()
    target_dir = project.path / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    # One file per area/page: drop older versions with a different extension.
    for existing in target_dir.glob(f"{basename}.*"):
        existing.unlink()
    target = target_dir / f"{basename}{suffix}"
    upload.save(target)
    return project.relpath_of(target), original

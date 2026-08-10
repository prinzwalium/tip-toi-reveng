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
from dataclasses import dataclass, field, asdict
from pathlib import Path

from .i18n import t
from .projects import Project, ProjectError, sanitize_filename

BOOK_FILE = "book.json"
FORMAT_VERSION = 1

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


def _next_id(prefix: str, taken: set[str]) -> str:
    n = 1
    while f"{prefix}{n}" in taken:
        n += 1
    return f"{prefix}{n}"


@dataclass
class Area:
    id: str
    name: str = ""
    x: float = 0.0
    y: float = 0.0
    w: float = 20.0
    h: float = 20.0
    #: Path of the sound inside the project, empty while none is assigned.
    sound: str = ""
    #: What the user called the file they uploaded, for display only.
    sound_name: str = ""

    def clamp(self, page_w: float, page_h: float) -> None:
        self.w = max(1.0, min(round(self.w, 2), page_w))
        self.h = max(1.0, min(round(self.h, 2), page_h))
        self.x = max(0.0, min(round(self.x, 2), page_w - self.w))
        self.y = max(0.0, min(round(self.y, 2), page_h - self.h))

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
            raise ProjectError("The product number must be between 1 and 999")
        page_w, page_h = book.page_size
        for raw_page in data.get("pages") or []:
            page = Page(
                id=str(raw_page.get("id") or ""),
                name=str(raw_page.get("name") or "")[:80],
                image=str(raw_page.get("image") or ""),
            )
            if not ID_RE.match(page.id):
                page.id = _next_id("s", {p.id for p in book.pages})
            for raw_area in raw_page.get("areas") or []:
                area = Area(
                    id=str(raw_area.get("id") or ""),
                    name=str(raw_area.get("name") or "")[:80],
                    x=float(raw_area.get("x") or 0),
                    y=float(raw_area.get("y") or 0),
                    w=float(raw_area.get("w") or 20),
                    h=float(raw_area.get("h") or 20),
                    sound=str(raw_area.get("sound") or ""),
                    sound_name=str(raw_area.get("sound_name") or "")[:120],
                )
                if not ID_RE.match(area.id):
                    area.id = _next_id("a", {a.id for p in book.pages for a in p.areas})
                area.clamp(page_w, page_h)
                page.areas.append(area)
            book.pages.append(page)
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
            if not [a for a in page.areas if a.sound]:
                problems.append(t("“{label}” has no area with a sound yet.", label=label))
            for area in page.areas:
                name = area.name or t("Unnamed area")
                if not area.sound:
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

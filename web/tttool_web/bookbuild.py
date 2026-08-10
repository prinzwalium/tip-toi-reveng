"""Turning a book into the two things a user needs: a file for the pen and a
printable PDF.

The steps are:

1. write ``book.yaml`` from the model,
2. ``tttool assemble`` it into ``book.gme``; tttool assigns an OID code to every
   area and remembers it in ``book.codes.yaml``, so codes stay stable and
   already printed pages keep working,
3. ``tttool oid-codes --image-format svg`` to get each code as a tileable SVG
   pattern,
4. compose one SVG per page: the picture, each area filled with its pattern,
   and the power-on field,
5. render those to PDF at their true physical size and bind them into one file.
"""

import base64
import mimetypes
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

from .book import Book, Page
from .config import config
from .i18n import t
from .projects import Project
from .runner import run

#: tttool draws its patterns on a grid of 48 units per millimetre. The page has
#: to use the same unit or the dots come out at the wrong size.
UNITS_PER_MM = 48

PRINT_DIR = "druck"
YAML_FILE = "book.yaml"
GME_FILE = "buch.gme"
FONT = "DejaVu Sans, sans-serif"


@dataclass
class BuildResult:
    ok: bool
    gme: str = ""
    pdf: str = ""
    pages: list[str] = None
    codes: list[tuple[str, str, int]] = None  # (page, area, code)
    problems: list[str] = None
    hints: list[str] = None
    log: str = ""

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "gme": self.gme,
            "pdf": self.pdf,
            "pages": self.pages or [],
            "codes": [{"page": p, "area": a, "code": c} for p, a, c in (self.codes or [])],
            "problems": self.problems or [],
            "hints": self.hints or [],
            "log": self.log,
        }


# ---------------------------------------------------------------- the YAML


def write_yaml(project: Project, book: Book) -> str:
    """Generate the tttool source. The book is the original, this is derived."""
    lines = [
        "# Written by the tttool web GUI from book.json — do not edit by hand,",
        "# the next build overwrites it.",
        f"product-id: {book.product_id}",
        f"comment: {_yaml_string(book.title)}",
        'media-path: "sounds/%s"',
        "scripts:",
    ]
    for page in book.pages:
        for area in page.areas:
            if not area.sound:
                continue
            stem = Path(area.sound).stem
            lines.append(f"  {book.script_name(page, area)}: P({stem})")
    text = "\n".join(lines) + "\n"
    return project.write_text(YAML_FILE, text)


def _yaml_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


# ------------------------------------------------------------ the patterns


def _read_patterns(directory: Path) -> dict[str, str]:
    """{script name: <pattern> element} from the files tttool just wrote."""
    patterns: dict[str, str] = {}
    for path in directory.glob("oid-*.svg"):
        match = re.search(r"<pattern.*?</pattern>", path.read_text(encoding="utf-8"), re.S)
        if not match:
            continue
        # oid-<product>-<name>.svg
        name = path.stem.split("-", 2)[-1]
        # tttool's own ids may start with a digit, which no XML name may do.
        patterns[name] = re.sub(r'id="[^"]*"', f'id="oid-{name}"', match.group(0), count=1)
    return patterns


def _codes_from_yaml(project: Project, book: Book) -> dict[str, int]:
    """The code tttool assigned to each script name, from book.codes.yaml."""
    path = project.path / f"{Path(YAML_FILE).stem}.codes.yaml"
    if not path.is_file():
        return {}
    codes: dict[str, int] = {}
    inside = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("scriptcodes:"):
            inside = True
            continue
        if inside:
            match = re.match(r"\s+([A-Za-z0-9_]+):\s*(\d+)\s*$", line)
            if match:
                codes[match.group(1)] = int(match.group(2))
            elif line.strip() and not line.startswith(" "):
                inside = False
    return codes


# --------------------------------------------------------------- the pages


def compose_page_svg(project: Project, book: Book, page: Page, patterns: dict[str, str]) -> str:
    """One printable page: picture, painted areas, power-on field."""
    page_w, page_h = book.page_size
    u = UNITS_PER_MM

    used = {
        book.script_name(page, area): area
        for area in page.areas
        if area.sound and book.script_name(page, area) in patterns
    }
    defs = "".join(patterns[name] for name in used)
    if "START" in patterns:
        defs += patterns["START"]

    body: list[str] = []
    if page.image:
        image_path = project.path / page.image
        if image_path.is_file():
            mime = mimetypes.guess_type(image_path.name)[0] or "image/png"
            data = base64.b64encode(image_path.read_bytes()).decode()
            body.append(
                f'<image x="0" y="0" width="{page_w * u}" height="{page_h * u}" '
                f'preserveAspectRatio="xMidYMid meet" '
                f'xlink:href="data:{mime};base64,{data}"/>'
            )

    for name, area in used.items():
        body.append(
            f'<rect x="{area.x * u:.1f}" y="{area.y * u:.1f}" '
            f'width="{area.w * u:.1f}" height="{area.h * u:.1f}" fill="url(#oid-{name})"/>'
        )

    # The power-on field, on every page — without it the pen stays silent.
    px, py, pw, ph = book.power_field
    if "START" in patterns:
        body.append(
            f'<rect x="{px * u:.1f}" y="{py * u:.1f}" width="{pw * u:.1f}" height="{ph * u:.1f}" '
            f'fill="white"/>'
            f'<rect x="{px * u:.1f}" y="{py * u:.1f}" width="{pw * u:.1f}" height="{ph * u:.1f}" '
            f'fill="url(#oid-START)"/>'
            f'<rect x="{px * u:.1f}" y="{py * u:.1f}" width="{pw * u:.1f}" height="{ph * u:.1f}" '
            f'fill="none" stroke="black" stroke-width="{0.3 * u}"/>'
        )
        body.append(
            f'<text x="{px * u:.1f}" y="{(py - 1.5) * u:.1f}" font-family="{FONT}" '
            f'font-size="{3.2 * u}" fill="black">{escape(t("Tap here to switch on"))}</text>'
        )

    # A printed ruler mark: if this is not exactly 50 mm, the print was scaled.
    ruler_y = page_h - 4
    body.append(
        f'<g stroke="black" stroke-width="{0.25 * u}">'
        f'<line x1="{(page_w - 58) * u}" y1="{ruler_y * u}" x2="{(page_w - 8) * u}" y2="{ruler_y * u}"/>'
        f'<line x1="{(page_w - 58) * u}" y1="{(ruler_y - 1.5) * u}" x2="{(page_w - 58) * u}" y2="{(ruler_y + 1.5) * u}"/>'
        f'<line x1="{(page_w - 8) * u}" y1="{(ruler_y - 1.5) * u}" x2="{(page_w - 8) * u}" y2="{(ruler_y + 1.5) * u}"/>'
        f"</g>"
        f'<text x="{(page_w - 58) * u}" y="{(ruler_y - 2.5) * u}" font-family="{FONT}" '
        f'font-size="{2.8 * u}" fill="black">{escape(t("50 mm — check with a ruler"))}</text>'
    )

    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'version="1.1" width="{page_w}mm" height="{page_h}mm" '
        f'viewBox="0 0 {page_w * u} {page_h * u}">'
        f'<rect width="100%" height="100%" fill="white"/>'
        f"<defs>{defs}</defs>"
        f"{''.join(body)}"
        f"</svg>\n"
    )


def _svg_to_pdf(svg_path: Path, pdf_path: Path) -> None:
    import cairosvg  # imported here so the rest of the app runs without it

    cairosvg.svg2pdf(url=str(svg_path), write_to=str(pdf_path))


def _merge_pdfs(parts: list[Path], target: Path) -> None:
    from pypdf import PdfWriter

    writer = PdfWriter()
    for part in parts:
        writer.append(str(part))
    with target.open("wb") as handle:
        writer.write(handle)


# ----------------------------------------------------------------- driving


def build(project: Project, book: Book) -> BuildResult:
    problems, hints = book.check()
    if problems:
        return BuildResult(ok=False, problems=problems, hints=hints)

    log: list[str] = []
    write_yaml(project, book)

    assembled = run([config.TTTOOL_BIN, "assemble", YAML_FILE, GME_FILE], project.path)
    log.append(assembled["stdout"] + assembled["stderr"])
    if not assembled["ok"]:
        return BuildResult(
            ok=False,
            problems=[t("tttool could not build the file for the pen.")],
            hints=hints,
            log="\n".join(log),
        )

    print_dir = project.path / PRINT_DIR
    codes_dir = print_dir / "codes"
    shutil.rmtree(codes_dir, ignore_errors=True)
    codes_dir.mkdir(parents=True, exist_ok=True)

    drawn = run(
        [config.TTTOOL_BIN, "--image-format", "svg", "oid-codes", f"../../{YAML_FILE}"],
        codes_dir,
    )
    log.append(drawn["stdout"] + drawn["stderr"])
    if not drawn["ok"]:
        return BuildResult(
            ok=False,
            problems=[t("tttool could not draw the codes.")],
            hints=hints,
            log="\n".join(log),
        )

    patterns = _read_patterns(codes_dir)
    code_numbers = _codes_from_yaml(project, book)

    page_files: list[str] = []
    pdf_parts: list[Path] = []
    codes: list[tuple[str, str, int]] = []
    for index, page in enumerate(book.pages, start=1):
        svg = compose_page_svg(project, book, page, patterns)
        svg_path = print_dir / f"seite-{index}.svg"
        svg_path.write_text(svg, encoding="utf-8")
        pdf_path = print_dir / f"seite-{index}.pdf"
        try:
            _svg_to_pdf(svg_path, pdf_path)
        except Exception as exc:  # noqa: BLE001 - reported to the user as text
            return BuildResult(
                ok=False,
                problems=[t("The printable page could not be created: {error}", error=exc)],
                hints=hints,
                log="\n".join(log),
            )
        pdf_parts.append(pdf_path)
        page_files.append(project.relpath_of(pdf_path))
        for area in page.areas:
            name = book.script_name(page, area)
            if area.sound and name in code_numbers:
                codes.append((page.name or page.id, area.name or area.id, code_numbers[name]))

    book_pdf = print_dir / f"{_slug(book.title)}.pdf"
    _merge_pdfs(pdf_parts, book_pdf)

    return BuildResult(
        ok=True,
        gme=GME_FILE,
        pdf=project.relpath_of(book_pdf),
        pages=page_files,
        codes=codes,
        problems=[],
        hints=hints,
        log="\n".join(log),
    )


def _slug(title: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", title).strip("-").lower()
    return slug or "buch"


def converters_available() -> bool:
    try:
        import cairosvg  # noqa: F401
        import pypdf  # noqa: F401
    except ImportError:
        return False
    return True

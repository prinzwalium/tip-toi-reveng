"""Page pictures at two sizes: one to look at, one to print.

A scan of an A4 page at 300 dpi is 3508 × 2480 pixels — as a PNG easily twelve
megabytes. Handing that to the browser once per page turns a ten page book into
a hundred megabyte download, and embedding it in the print SVG produces a PDF
nobody can e-mail.

So each picture is kept three ways:

``original``
    exactly what was uploaded, never touched, so nothing is ever lost;
``preview``
    small enough to draw areas on comfortably — what the editor loads;
``print copy``
    the original at the resolution the page is actually printed at, encoded as
    JPEG, which is what ends up inside the PDF.

The dots the pen reads are vector patterns drawn on top; the picture underneath
is only for human eyes. Compressing it cannot make a book stop working.
"""

from pathlib import Path

from .projects import Project

#: Longest side of the preview, in pixels. Big enough that a photo still looks
#: like a photo at editor size, small enough to arrive instantly.
PREVIEW_MAX_PX = 1600

#: What the print copy is scaled to. Beyond this the printer cannot tell the
#: difference, and the file only gets larger.
PRINT_DPI = 300

#: JPEG quality of the print copy. At 300 dpi this is indistinguishable from
#: the original on paper.
PRINT_QUALITY = 88
PREVIEW_QUALITY = 82

PREVIEW_SUFFIX = "-vorschau.jpg"
PRINT_SUFFIX = "-druck.jpg"


def _pillow():
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - Pillow is in requirements
        return None
    return Image


def _flatten(image, Image):
    """JPEG has no transparency; put anything see-through on white."""
    if image.mode in ("RGBA", "LA", "P"):
        image = image.convert("RGBA")
        white = Image.new("RGBA", image.size, (255, 255, 255, 255))
        return Image.alpha_composite(white, image).convert("RGB")
    return image.convert("RGB") if image.mode != "RGB" else image


def make_preview(project: Project, relpath: str) -> str:
    """Write the editor's copy of ``relpath``; returns its path, or "" .

    Returns the original for pictures that are already small: a second file
    would cost a request and save nothing.
    """
    Image = _pillow()
    if not Image or not relpath:
        return ""
    source = project.path / relpath
    if not source.is_file():
        return ""
    target = source.with_name(Path(relpath).stem + PREVIEW_SUFFIX)
    try:
        with Image.open(source) as picture:
            if max(picture.size) <= PREVIEW_MAX_PX:
                return relpath
            picture = _flatten(picture, Image)
            picture.thumbnail((PREVIEW_MAX_PX, PREVIEW_MAX_PX), Image.LANCZOS)
            picture.save(target, "JPEG", quality=PREVIEW_QUALITY, optimize=True)
    except OSError:
        # A picture Pillow cannot read is still a picture the browser may
        # manage — fall back to the original rather than losing the page.
        return relpath
    return project.relpath_of(target)


def print_copy(project: Project, relpath: str, page_w_mm: float, page_h_mm: float) -> Path:
    """The file to embed in the printed page — the original if it is small."""
    source = project.path / relpath
    Image = _pillow()
    if not Image or not source.is_file():
        return source

    limit = (
        int(page_w_mm / 25.4 * PRINT_DPI),
        int(page_h_mm / 25.4 * PRINT_DPI),
    )
    target = source.with_name(Path(relpath).stem + PRINT_SUFFIX)
    try:
        with Image.open(source) as picture:
            fits = picture.width <= limit[0] and picture.height <= limit[1]
            # A small JPEG is already the best we can do; a small PNG of line
            # art may well be smaller than any JPEG of it.
            if fits and source.suffix.lower() in (".jpg", ".jpeg"):
                return source
            if fits and source.stat().st_size <= 2 * 1024 * 1024:
                return source
            picture = _flatten(picture, Image)
            picture.thumbnail(limit, Image.LANCZOS)
            picture.save(target, "JPEG", quality=PRINT_QUALITY, optimize=True)
    except OSError:
        return source
    # If the conversion made things worse, print the original.
    if target.stat().st_size >= source.stat().st_size:
        target.unlink(missing_ok=True)
        return source
    return target


def picture_pixels(path: Path) -> tuple[int, int] | None:
    """The size of a picture file, or None if it cannot be read."""
    Image = _pillow()
    if not Image:
        return None
    try:
        with Image.open(path) as picture:
            return picture.size
    except OSError:
        return None


def forget(project: Project, relpath: str) -> None:
    """Drop the derived copies of a picture that is being replaced."""
    if not relpath:
        return
    source = project.path / relpath
    for suffix in (PREVIEW_SUFFIX, PRINT_SUFFIX):
        source.with_name(Path(relpath).stem + suffix).unlink(missing_ok=True)


def is_derived(relpath: str) -> bool:
    return relpath.endswith((PREVIEW_SUFFIX, PRINT_SUFFIX))

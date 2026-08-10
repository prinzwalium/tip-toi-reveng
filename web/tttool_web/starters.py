"""What a new book starts out as.

A first-time user should reach something that works within minutes, so a new
book can come with a picture, areas and sounds already in place — a thing to
change rather than a blank page.
"""

from pathlib import Path

from .audio import speak, speech_engine
from .book import Book, fitted_image_rect
from .projects import Project

#: The starting points offered on the front page.
STARTERS = ("example", "quiz", "collect", "empty")

#: Placeholder picture: four circles the user draws over.
EXAMPLE_LABELS = ("Hund", "Katze", "Kuh", "Ente")
EXAMPLE_TEXTS = {
    "Hund": "Der Hund macht wau wau.",
    "Katze": "Die Katze macht miau.",
    "Kuh": "Die Kuh macht muh.",
    "Ente": "Die Ente macht quak.",
}
CIRCLE_COLOURS = ((255, 214, 165), (196, 226, 255), (203, 243, 210), (255, 205, 210))
#: Pixels per millimetre for the generated picture — enough to look sharp on
#: screen without making a huge file; it is a placeholder, not artwork.
PIXELS_PER_MM = 6


def _font(size: int):
    from PIL import ImageFont

    for candidate in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def draw_example_picture(target: Path, page_w: float, page_h: float) -> list[tuple[str, tuple]]:
    """Draw the placeholder page; returns the labels with their areas in mm."""
    from PIL import Image, ImageDraw

    width, height = int(page_w * PIXELS_PER_MM), int(page_h * PIXELS_PER_MM)
    picture = Image.new("RGB", (width, height), (252, 250, 246))
    draw = ImageDraw.Draw(picture)

    draw.text(
        (width * 0.06, height * 0.07),
        "Beispielseite",
        fill=(60, 60, 60),
        font=_font(int(height * 0.06)),
    )
    draw.text(
        (width * 0.06, height * 0.15),
        "Tippe die Kreise an – oder lade dein eigenes Bild hoch.",
        fill=(120, 120, 120),
        font=_font(int(height * 0.032)),
    )

    areas: list[tuple[str, tuple]] = []
    radius = min(width, height) * 0.13
    for index, label in enumerate(EXAMPLE_LABELS):
        centre_x = width * (0.2 + 0.2 * index)
        centre_y = height * 0.55
        draw.ellipse(
            [centre_x - radius, centre_y - radius, centre_x + radius, centre_y + radius],
            fill=CIRCLE_COLOURS[index % len(CIRCLE_COLOURS)],
            outline=(90, 90, 90),
            width=max(2, int(radius * 0.02)),
        )
        font = _font(int(radius * 0.34))
        box = draw.textbbox((0, 0), label, font=font)
        draw.text(
            (centre_x - (box[2] - box[0]) / 2, centre_y - (box[3] - box[1]) / 2),
            label,
            fill=(50, 50, 50),
            font=font,
        )
        areas.append(
            (
                label,
                (
                    (centre_x - radius) / PIXELS_PER_MM,
                    (centre_y - radius) / PIXELS_PER_MM,
                    2 * radius / PIXELS_PER_MM,
                    2 * radius / PIXELS_PER_MM,
                ),
            )
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    picture.save(target)
    return areas


def _spoken(project: Project, book: Book, name: str, text: str) -> str:
    """Add a spoken sound to the library; empty id if this box cannot speak."""
    if not speech_engine():
        return ""
    sound = book.add_sound(name=name, source="speak", text=text, language="de")
    sound.file = f"sounds/{sound.id}.ogg"
    try:
        speak(text, "de", project.path / sound.file)
    except Exception:  # noqa: BLE001 — a starter must never block book creation
        book.sounds.remove(sound)
        return ""
    return sound.id


def apply_starter(project: Project, book: Book, kind: str) -> None:
    """Fill a fresh book with something to look at and change."""
    if kind not in STARTERS or kind == "empty":
        return

    page = book.pages[0]
    page_w, page_h = book.page_size

    try:
        image_areas = draw_example_picture(project.path / "seiten" / f"{page.id}.png",
                                           page_w, page_h)
        page.image = f"seiten/{page.id}.png"
    except Exception:  # noqa: BLE001 — without Pillow the book simply starts blank
        image_areas = [
            (label, (20 + 60 * index, page_h / 2 - 20, 40, 40))
            for index, label in enumerate(EXAMPLE_LABELS)
        ]

    if kind == "example":
        for label, (x, y, w, h) in image_areas:
            area = book.add_area(page, name=label, x=x, y=y, w=w, h=h)
            area.sound_id = _spoken(project, book, label, EXAMPLE_TEXTS[label])
        return

    if kind == "quiz":
        group = book.add_group(kind="quiz", name="Quiz")
        group.right_sound_id = _spoken(project, book, "Richtig", "Richtig! Sehr gut.")
        group.wrong_sound_id = _spoken(project, book, "Falsch", "Das war leider falsch.")
        question = book.add_area(page, name="Frage", x=20, y=20, w=60, h=30)
        question.sound_id = _spoken(project, book, "Frage", "Welches Tier macht wau wau?")
        for index, (label, (x, y, w, h)) in enumerate(image_areas):
            area = book.add_area(page, name=label, x=x, y=y, w=w, h=h)
            area.behaviour = "answer"
            area.group = group.id
            area.correct = index == 0
        return

    if kind == "collect":
        group = book.add_group(kind="collect", name="Suchspiel")
        group.reward_sound_id = _spoken(project, book, "Geschafft", "Super, du hast alle gefunden!")
        for label, (x, y, w, h) in image_areas:
            area = book.add_area(page, name=label, x=x, y=y, w=w, h=h)
            area.behaviour = "collect"
            area.group = group.id
            area.sound_id = _spoken(project, book, label, EXAMPLE_TEXTS[label])

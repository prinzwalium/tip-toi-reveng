"""Tests for the book editor.

They run against a stub tttool and a stub ffmpeg, so the whole path from
"draw an area" to "printable PDF" is exercised without a Haskell toolchain or
an audio encoder. The PDF itself is produced by the real renderer.
"""

import io
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

TTTOOL_STUB = '''#!/usr/bin/env python3
"""Enough of tttool for the book pipeline: assemble and oid-codes."""
import re, sys
from pathlib import Path

COMMANDS = {"assemble", "oid-codes", "--help"}
argv = sys.argv[1:]
command = next((a for a in argv if a in COMMANDS), "")
args = argv[argv.index(command) :] if command else []

if command == "assemble":
    yaml_path, gme = Path(args[1]), Path(args[2])
    names = re.findall(r"^  (\\w+):", yaml_path.read_text(), re.M)
    gme.write_bytes(b"GME" + b"\\0" * 32)
    codes = "\\n".join(f"  {n}: {13447 + i}" for i, n in enumerate(names))
    yaml_path.with_suffix("").with_suffix(".codes.yaml").write_text(
        f"replay: 13445\\nscriptcodes:\\n{codes}\\nstop: 13446\\n"
    )
elif command == "oid-codes":
    yaml_path = Path(args[1])
    names = re.findall(r"^  (\\w+):", yaml_path.read_text(), re.M) + ["START"]
    for name in names:
        pattern = (
            f'<pattern width="48" height="48" id="{name}" patternUnits="userSpaceOnUse">'
            '<path d="M 43,43 h 2 v 2 h -2 Z" /></pattern>'
        )
        Path(f"oid-42-{name}.svg").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<svg xmlns="http://www.w3.org/2000/svg" width="30mm" height="30mm" '
            f'viewBox="0 0 1440 1440"><defs>{pattern}</defs></svg>'
        )
elif command == "--help" or not command:
    print("tttool-1.11 -- The swiss army knife for the Tiptoi hacker")
'''

PICO_STUB = """#!/bin/sh
# Stand-in for pico2wave: writes a file where --wave points.
prev=""; wave=""
for arg in "$@"; do
  [ "$prev" = "--wave" ] && wave="$arg"
  prev="$arg"
done
printf 'RIFFfake' > "$wave"
"""

FFMPEG_STUB = """#!/bin/sh
# Copies the input to the output; enough to test the upload path.
prev=""; input=""; last=""
for arg in "$@"; do
  [ "$prev" = "-i" ] && input="$arg"
  prev="$arg"; last="$arg"
done
cp "$input" "$last"
"""


@pytest.fixture()
def client(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    tttool = tmp_path / "tttool-stub"
    tttool.write_text(TTTOOL_STUB)
    tttool.chmod(0o755)
    ffmpeg = tmp_path / "ffmpeg-stub"
    ffmpeg.write_text(FFMPEG_STUB)
    ffmpeg.chmod(0o755)
    pico = tmp_path / "pico-stub"
    pico.write_text(PICO_STUB)
    pico.chmod(0o755)

    monkeypatch.setenv("TTTOOL_WEB_DATA", str(data))
    monkeypatch.setenv("TTTOOL_BIN", str(tttool))
    monkeypatch.setenv("FFMPEG_BIN", str(ffmpeg))
    monkeypatch.setenv("PICO_BIN", str(pico))
    monkeypatch.setenv("TTTOOL_WEB_LANG", "en")
    for module in [m for m in list(sys.modules) if m.startswith("tttool_web")]:
        del sys.modules[module]

    from tttool_web.app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as test_client:
        test_client.data_dir = data
        yield test_client


def make_book(client, title="Mein Buch", paper="a4-landscape"):
    response = client.post("/books", data={"title": title, "paper": paper})
    assert response.status_code == 302
    return response.headers["Location"].rstrip("/").split("/")[-1]


def put_areas(client, name, areas, paper="a4-landscape"):
    book = client.get(f"/b/{name}/data").get_json()
    book["pages"][0]["areas"] = areas
    return client.put(f"/b/{name}/data", json=book)


def add_sound(client, name, area_id, filename="bark.mp3"):
    """Put a sound in the library and let ``area_id`` play it."""
    added = client.post(
        f"/b/{name}/sounds/add",
        data={"sound": (io.BytesIO(b"audio"), filename)},
        content_type="multipart/form-data",
    ).get_json()
    assert added.get("ok"), added
    return client.post(
        f"/b/{name}/areas/{area_id}/sound", data={"sound_id": added["sound"]}
    )


# -- creating ---------------------------------------------------------------


def test_new_book_is_ready_to_edit(client):
    name = make_book(client, "Bauernhof Buch")
    assert name == "bauernhof-buch"
    book = json.loads((client.data_dir / name / "book.json").read_text())
    assert book["title"] == "Bauernhof Buch"
    assert len(book["pages"]) == 1
    assert client.get(f"/b/{name}").status_code == 200


def test_books_get_different_product_numbers(client):
    first = make_book(client, "Eins")
    second = make_book(client, "Zwei")
    ids = {
        json.loads((client.data_dir / n / "book.json").read_text())["product_id"]
        for n in (first, second)
    }
    assert len(ids) == 2


def test_book_needs_a_title(client):
    assert not (client.data_dir / "buch").exists()
    client.post("/books", data={"title": "  "}, follow_redirects=True)
    assert list(client.data_dir.iterdir()) == []


# -- editing ----------------------------------------------------------------


def test_areas_are_saved_and_clamped_to_the_page(client):
    name = make_book(client)
    response = put_areas(
        client,
        name,
        [{"id": "a1", "name": "Hund", "x": 500, "y": -20, "w": 40, "h": 30}],
    )
    assert response.status_code == 200
    area = json.loads((client.data_dir / name / "book.json").read_text())["pages"][0]["areas"][0]
    assert 0 <= area["x"] <= 297 - area["w"]
    assert area["y"] == 0


def test_browser_cannot_point_an_area_at_another_file(client):
    """Sound and picture paths come from the server, never from the client."""
    name = make_book(client)
    put_areas(client, name, [{"id": "a1", "name": "X", "x": 10, "y": 10, "w": 30, "h": 20,
                              "sound": "../../../etc/passwd", "sound_id": "../../etc/passwd"}])
    area = json.loads((client.data_dir / name / "book.json").read_text())["pages"][0]["areas"][0]
    assert area["sound_id"] == ""
    assert "sound" not in area


def test_sound_upload_lands_in_the_library_and_is_assigned(client):
    name = make_book(client)
    put_areas(client, name, [{"id": "a1", "name": "Hund", "x": 10, "y": 10, "w": 40, "h": 30}])
    result = add_sound(client, name, "a1").get_json()
    assert result["ok"]
    book = json.loads((client.data_dir / name / "book.json").read_text())
    assert len(book["sounds"]) == 1
    sound = book["sounds"][0]
    assert sound["name"] == "bark"
    assert sound["file"] == f"sounds/{sound['id']}.ogg"
    assert book["pages"][0]["areas"][0]["sound_id"] == sound["id"]
    assert (client.data_dir / name / sound["file"]).is_file()
    # only the converted file is kept
    assert list((client.data_dir / name / "sounds").iterdir()) == [
        client.data_dir / name / sound["file"]
    ]


def test_page_picture_upload(client):
    name = make_book(client)
    png = bytes.fromhex("89504e470d0a1a0a") + b"\0" * 64
    response = client.post(
        f"/b/{name}/pages/s1/image",
        data={"image": (io.BytesIO(png), "seite.png")},
        content_type="multipart/form-data",
    )
    assert response.get_json()["image"] == "seiten/s1.png"
    assert (client.data_dir / name / "seiten" / "s1.png").is_file()


def test_unknown_area_is_reported_as_json(client):
    name = make_book(client)
    response = add_sound(client, name, "nope")
    assert response.status_code == 400
    assert "error" in response.get_json()


# -- checks -----------------------------------------------------------------


def test_a_book_without_sounds_does_not_build(client):
    name = make_book(client)
    put_areas(client, name, [{"id": "a1", "name": "Stumm", "x": 10, "y": 10, "w": 40, "h": 30}])
    result = client.post(f"/b/{name}/build").get_json()
    assert result["ok"] is False
    assert any("no area with a sound" in p for p in result["problems"])


def test_small_areas_and_power_field_are_flagged(client):
    name = make_book(client)
    put_areas(
        client,
        name,
        [
            {"id": "a1", "name": "Winzig", "x": 100, "y": 100, "w": 5, "h": 5},
            {"id": "a2", "name": "Anschalter", "x": 8, "y": 182, "w": 20, "h": 20},
        ],
    )
    add_sound(client, name, "a1")
    add_sound(client, name, "a2")
    hints = client.post(f"/b/{name}/build").get_json()["hints"]
    assert any("smaller than" in h for h in hints)
    assert any("power-on field" in h for h in hints)


# -- building ---------------------------------------------------------------


@pytest.fixture()
def built(client):
    name = make_book(client, "Test Buch")
    put_areas(
        client,
        name,
        [
            {"id": "a1", "name": "Hund", "x": 20, "y": 20, "w": 40, "h": 30},
            {"id": "a2", "name": "Katze", "x": 90, "y": 60, "w": 35, "h": 25},
        ],
    )
    add_sound(client, name, "a1")
    add_sound(client, name, "a2")
    return name, client.post(f"/b/{name}/build").get_json()


def test_build_produces_both_files(client, built):
    name, result = built
    assert result["ok"], result
    assert result["gme"] == "buch.gme"
    assert result["pdf"].endswith(".pdf")
    assert (client.data_dir / name / "buch.gme").is_file()
    assert (client.data_dir / name / result["pdf"]).is_file()
    assert result["gme_url"] and result["pdf_url"]


def test_build_reports_the_code_of_every_area(client, built):
    _, result = built
    codes = {entry["area"]: entry["code"] for entry in result["codes"]}
    assert set(codes) == {"Hund", "Katze"}
    assert all(isinstance(code, int) for code in codes.values())


def test_generated_yaml_is_derived_from_the_book(client, built):
    name, _ = built
    yaml = (client.data_dir / name / "book.yaml").read_text()
    assert 'media-path: "sounds/%s"' in yaml
    assert 's1_a1: "P(t1)"' in yaml
    assert 's1_a2: "P(t2)"' in yaml


def test_printed_page_has_the_right_physical_size(client, built):
    """A wrongly sized page prints at the wrong scale and the pen goes deaf."""
    name, result = built
    data = (client.data_dir / name / result["pdf"]).read_bytes()
    box = re.search(rb"/MediaBox\s*\[([^\]]*)\]", data)
    assert box, "the PDF has no page size"
    numbers = [float(n) for n in box.group(1).split()]
    width_mm, height_mm = numbers[2] / 72 * 25.4, numbers[3] / 72 * 25.4
    assert abs(width_mm - 297) < 1
    assert abs(height_mm - 210) < 1


def test_page_svg_paints_each_area_with_its_own_pattern(client, built):
    name, _ = built
    svg = (client.data_dir / name / "druck" / "seite-1.svg").read_text()
    assert svg.count("<pattern") == 3  # two areas plus the power-on field
    assert 'fill="url(#oid-s1_a1)"' in svg
    assert 'fill="url(#oid-s1_a2)"' in svg
    assert 'fill="url(#oid-START)"' in svg
    # the page itself is measured in millimetres
    assert 'width="297mm"' in svg and 'height="210mm"' in svg


def test_codes_stay_the_same_when_the_book_is_built_again(client, built):
    """Reprinting must not invalidate pages that are already printed."""
    name, first = built
    second = client.post(f"/b/{name}/build").get_json()
    assert first["codes"] == second["codes"]


def test_build_offers_a_test_page(client, built):
    name, result = built
    assert result["test_pdf"].endswith("druckprobe.pdf")
    assert (client.data_dir / name / result["test_pdf"]).is_file()
    svg = (client.data_dir / name / "druck" / "druckprobe.svg").read_text()
    # every offered size, so the user can find their printer's limit
    for size in (8, 10, 12, 15, 20):
        assert f">{size} mm<" in svg
    assert "100%" in svg


# -- several pages ----------------------------------------------------------


def test_pages_can_be_added_duplicated_moved_and_deleted(client):
    name = make_book(client)
    put_areas(client, name, [{"id": "a1", "name": "Hund", "x": 10, "y": 10, "w": 40, "h": 30}])
    add_sound(client, name, "a1")

    added = client.post(f"/b/{name}/pages").get_json()
    assert len(added["book"]["pages"]) == 2

    duplicated = client.post(f"/b/{name}/pages/s1/duplicate").get_json()
    pages = duplicated["book"]["pages"]
    assert len(pages) == 3
    copy = pages[1]
    assert copy["image"] == pages[0]["image"]
    assert [a["name"] for a in copy["areas"]] == ["Hund"]
    assert copy["areas"][0]["sound_id"] == pages[0]["areas"][0]["sound_id"]
    assert copy["areas"][0]["id"] != "a1"

    moved = client.post(f"/b/{name}/pages/s1/move", data={"direction": "down"}).get_json()
    assert [p["id"] for p in moved["book"]["pages"]][0] != "s1"

    deleted = client.post(f"/b/{name}/pages/s1/delete").get_json()
    assert "s1" not in [p["id"] for p in deleted["book"]["pages"]]


def test_the_last_page_cannot_be_deleted(client):
    name = make_book(client)
    response = client.post(f"/b/{name}/pages/s1/delete")
    assert response.status_code == 400
    assert "at least one page" in response.get_json()["error"]


def test_every_page_gets_its_own_printed_sheet(client):
    name = make_book(client, "Zwei Seiten")
    put_areas(client, name, [{"id": "a1", "name": "Hund", "x": 10, "y": 10, "w": 40, "h": 30}])
    add_sound(client, name, "a1")
    client.post(f"/b/{name}/pages/s1/duplicate")
    book = client.get(f"/b/{name}/data").get_json()
    second = book["pages"][1]
    second["areas"][0]["name"] = "Katze"
    client.put(f"/b/{name}/data", json=book)

    result = client.post(f"/b/{name}/build").get_json()
    assert result["ok"], result
    assert len(result["pages"]) == 2
    assert {entry["area"] for entry in result["codes"]} == {"Hund", "Katze"}
    # two different codes, so the pen can tell the pages apart
    assert len({entry["code"] for entry in result["codes"]}) == 2

    from pypdf import PdfReader

    assert len(PdfReader(str(client.data_dir / name / result["pdf"])).pages) == 2


# -- free shapes ------------------------------------------------------------


def test_a_polygon_is_stored_with_its_bounding_box(client):
    name = make_book(client)
    put_areas(
        client,
        name,
        [{"id": "a1", "name": "See", "kind": "poly",
          "points": [[20, 30], [60, 25], [70, 60], [30, 70]]}],
    )
    area = json.loads((client.data_dir / name / "book.json").read_text())["pages"][0]["areas"][0]
    assert area["kind"] == "poly"
    assert area["x"] == 20 and area["y"] == 25
    assert area["w"] == 50 and area["h"] == 45


def test_a_polygon_is_printed_as_a_polygon(client):
    name = make_book(client)
    put_areas(
        client,
        name,
        [{"id": "a1", "name": "See", "kind": "poly",
          "points": [[20, 30], [60, 25], [70, 60], [30, 70]]}],
    )
    add_sound(client, name, "a1")
    result = client.post(f"/b/{name}/build").get_json()
    assert result["ok"], result
    svg = (client.data_dir / name / "druck" / "seite-1.svg").read_text()
    # The first corner sits at 20 mm / 30 mm, whatever the unit scale is.
    from tttool_web.bookbuild import UNITS_PER_MM

    first = f"{20 * UNITS_PER_MM:.1f},{30 * UNITS_PER_MM:.1f}"
    assert f'<polygon points="{first}' in svg
    assert 'fill="url(#oid-s1_a1)"' in svg


def test_a_polygon_with_too_few_corners_falls_back_to_a_rectangle(client):
    name = make_book(client)
    put_areas(client, name, [{"id": "a1", "kind": "poly", "points": [[10, 10], [20, 20]],
                              "x": 10, "y": 10, "w": 30, "h": 20}])
    area = json.loads((client.data_dir / name / "book.json").read_text())["pages"][0]["areas"][0]
    assert area["kind"] == "rect"


# -- duplicating areas ------------------------------------------------------


def test_duplicating_an_area_keeps_shape_and_sound(client):
    name = make_book(client)
    put_areas(client, name, [{"id": "a1", "name": "Hund", "x": 10, "y": 10, "w": 40, "h": 30}])
    add_sound(client, name, "a1")
    result = client.post(f"/b/{name}/areas/a1/duplicate").get_json()
    areas = result["book"]["pages"][0]["areas"]
    assert len(areas) == 2
    copy = areas[1]
    assert copy["w"] == 40 and copy["h"] == 30
    # the library makes sharing a sound the natural thing
    assert copy["sound_id"] == areas[0]["sound_id"]
    assert copy["id"] != "a1"


# -- dark artwork -----------------------------------------------------------


def test_dark_artwork_under_an_area_is_flagged(client):
    pytest.importorskip("PIL")
    from PIL import Image

    name = make_book(client)
    dark = Image.new("RGB", (600, 400), (12, 12, 14))
    buffer = io.BytesIO()
    dark.save(buffer, format="PNG")
    buffer.seek(0)
    client.post(
        f"/b/{name}/pages/s1/image",
        data={"image": (buffer, "dunkel.png")},
        content_type="multipart/form-data",
    )
    put_areas(client, name, [{"id": "a1", "name": "Nacht", "x": 60, "y": 40, "w": 40, "h": 30}])
    add_sound(client, name, "a1")
    hints = client.post(f"/b/{name}/build").get_json()["hints"]
    assert any("dark part" in hint for hint in hints)


# -- the sound library ------------------------------------------------------


def test_one_sound_can_be_used_by_several_areas(client):
    name = make_book(client)
    put_areas(
        client,
        name,
        [
            {"id": "a1", "name": "Hund", "x": 10, "y": 10, "w": 40, "h": 30},
            {"id": "a2", "name": "Zweiter Hund", "x": 80, "y": 10, "w": 40, "h": 30},
        ],
    )
    added = client.post(
        f"/b/{name}/sounds/add",
        data={"sound": (io.BytesIO(b"audio"), "wau.mp3")},
        content_type="multipart/form-data",
    ).get_json()
    for area in ("a1", "a2"):
        client.post(f"/b/{name}/areas/{area}/sound", data={"sound_id": added["sound"]})

    library = client.get(f"/b/{name}/sounds").get_json()
    assert len(library["sounds"]) == 1
    assert library["sounds"][0]["used"] == 2

    result = client.post(f"/b/{name}/build").get_json()
    assert result["ok"], result
    yaml = (client.data_dir / name / "book.yaml").read_text()
    assert yaml.count(f"P({added['sound']})") == 2
    # two areas, two codes, one sound file
    assert len(result["codes"]) == 2
    assert len(list((client.data_dir / name / "sounds").iterdir())) == 1


def test_deleting_a_sound_silences_the_areas_that_used_it(client):
    name = make_book(client)
    put_areas(client, name, [{"id": "a1", "name": "Hund", "x": 10, "y": 10, "w": 40, "h": 30}])
    add_sound(client, name, "a1")
    book = client.get(f"/b/{name}/data").get_json()
    sound_id = book["sounds"][0]["id"]

    result = client.post(f"/b/{name}/sounds/{sound_id}/delete").get_json()
    assert result["book"]["pages"][0]["areas"][0]["sound_id"] == ""
    assert result["sounds"] == []
    assert not (client.data_dir / name / "sounds" / f"{sound_id}.ogg").exists()


def test_a_sound_can_be_renamed(client):
    name = make_book(client)
    add_sound(client, name, "a1") if False else None
    added = client.post(
        f"/b/{name}/sounds/add",
        data={"sound": (io.BytesIO(b"audio"), "irgendwas.mp3")},
        content_type="multipart/form-data",
    ).get_json()
    result = client.post(
        f"/b/{name}/sounds/{added['sound']}/rename", data={"name": "Hund bellt"}
    ).get_json()
    assert result["sounds"][0]["name"] == "Hund bellt"


def test_assigning_an_unknown_sound_is_refused(client):
    name = make_book(client)
    put_areas(client, name, [{"id": "a1", "name": "Hund", "x": 10, "y": 10, "w": 40, "h": 30}])
    response = client.post(f"/b/{name}/areas/a1/sound", data={"sound_id": "nope"})
    assert response.status_code == 400


def test_a_book_from_the_previous_format_gains_a_library(client):
    """Books made with 1.1/1.2 keep working and get their sounds migrated."""
    name = make_book(client)
    old = {
        "title": "Alt", "product_id": 42, "paper": "a4-landscape", "version": 1,
        "pages": [{"id": "s1", "name": "Seite 1", "image": "", "areas": [
            {"id": "a1", "name": "Hund", "x": 10, "y": 10, "w": 40, "h": 30,
             "sound": "sounds/a1.ogg", "sound_name": "wau.mp3"},
            {"id": "a2", "name": "Auch Hund", "x": 80, "y": 10, "w": 40, "h": 30,
             "sound": "sounds/a1.ogg", "sound_name": "wau.mp3"},
        ]}],
    }
    (client.data_dir / name / "book.json").write_text(json.dumps(old))
    (client.data_dir / name / "sounds").mkdir(exist_ok=True)
    (client.data_dir / name / "sounds" / "a1.ogg").write_bytes(b"ogg")

    book = client.get(f"/b/{name}/data").get_json()
    assert book["version"] == 2
    assert len(book["sounds"]) == 1
    sound = book["sounds"][0]
    assert sound["file"] == "sounds/a1.ogg"
    # the old field held a file name; the library shows names
    assert sound["name"] == "wau"
    # both areas end up on the same library entry
    assert [a["sound_id"] for a in book["pages"][0]["areas"]] == [sound["id"], sound["id"]]


# -- spoken sounds ----------------------------------------------------------


def test_speaking_creates_a_sound_that_can_be_spoken_again(client, monkeypatch):
    name = make_book(client)
    result = client.post(
        f"/b/{name}/sounds/speak", data={"text": "Der Hund macht wau.", "language": "de"}
    ).get_json()
    assert result["ok"], result
    assert result["engine"] == "pico"
    sound = [s for s in result["sounds"] if s["id"] == result["sound"]][0]
    assert sound["source"] == "speak"
    assert sound["text"] == "Der Hund macht wau."
    assert sound["language"] == "de"
    assert (client.data_dir / name / sound["file"]).is_file()

    # Speaking again replaces the file, so every area follows along.
    again = client.post(
        f"/b/{name}/sounds/speak",
        data={"text": "Die Katze macht miau.", "language": "de", "sound_id": sound["id"]},
    ).get_json()
    assert len(again["sounds"]) == 1
    assert again["sounds"][0]["text"] == "Die Katze macht miau."


def test_speaking_needs_text(client):
    name = make_book(client)
    response = client.post(f"/b/{name}/sounds/speak", data={"text": "   ", "language": "de"})
    assert response.status_code == 400


def test_without_a_synthesizer_speaking_says_so(client, monkeypatch):
    monkeypatch.setenv("PICO_BIN", "definitely-not-installed")
    monkeypatch.setenv("ESPEAK_BIN", "definitely-not-installed-either")
    for module in [m for m in list(sys.modules) if m.startswith("tttool_web")]:
        del sys.modules[module]
    from tttool_web.app import create_app

    with create_app().test_client() as fresh:
        fresh.post("/books", data={"title": "Stumm"})
        assert fresh.get("/b/stumm/sounds").get_json()["can_speak"] is False
        response = fresh.post("/b/stumm/sounds/speak", data={"text": "Hallo"})
        assert response.status_code == 400
        assert "speech synthesizer" in response.get_json()["error"]


# -- what an area does ------------------------------------------------------


def library_sound(client, name, filename="ton.mp3"):
    return client.post(
        f"/b/{name}/sounds/add",
        data={"sound": (io.BytesIO(b"audio"), filename)},
        content_type="multipart/form-data",
    ).get_json()["sound"]


def script_for(client, name, area_id="a1"):
    """The generated script lines for one area, from the built YAML."""
    assert client.post(f"/b/{name}/build").get_json().get("ok") is not False
    yaml = (client.data_dir / name / "book.yaml").read_text()
    lines, collecting = [], False
    for line in yaml.splitlines():
        if line.startswith(f"  s1_{area_id}:"):
            rest = line.split(":", 1)[1].strip()
            if rest:
                return [rest.strip('"')]
            collecting = True
        elif collecting:
            if line.startswith("  - "):
                lines.append(line[4:].strip().strip('"'))
            else:
                break
    return lines


def test_random_plays_one_of_several(client):
    name = make_book(client)
    first, second = library_sound(client, name), library_sound(client, name)
    put_areas(client, name, [{"id": "a1", "name": "Vogel", "x": 10, "y": 10, "w": 40, "h": 30,
                              "behaviour": "random", "sound_ids": [first, second]}])
    assert script_for(client, name) == [f"P({first},{second})"]


def test_sequence_steps_through_and_starts_over(client):
    name = make_book(client)
    one, two, three = (library_sound(client, name) for _ in range(3))
    put_areas(client, name, [{"id": "a1", "name": "Geschichte", "x": 10, "y": 10, "w": 40, "h": 30,
                              "behaviour": "sequence", "sound_ids": [one, two, three]}])
    lines = script_for(client, name)
    assert lines == [
        f"$seqa1==0? $seqa1:=1 P({one})",
        f"$seqa1==1? $seqa1:=2 P({two})",
        f"$seqa1==2? $seqa1:=0 P({three})",
    ]


def test_quiz_answers_play_the_right_reaction(client):
    name = make_book(client)
    right, wrong, own = (library_sound(client, name) for _ in range(3))
    group = client.post(f"/b/{name}/groups", data={"kind": "quiz"}).get_json()["group"]
    client.post(f"/b/{name}/groups/{group}",
                data={"right_sound_id": right, "wrong_sound_id": wrong})
    put_areas(client, name, [
        {"id": "a1", "name": "Richtig", "x": 10, "y": 10, "w": 40, "h": 30,
         "behaviour": "answer", "group": group, "correct": True, "sound_id": own},
        {"id": "a2", "name": "Falsch", "x": 80, "y": 10, "w": 40, "h": 30,
         "behaviour": "answer", "group": group, "correct": False},
    ])
    assert script_for(client, name, "a1") == [f"P({own}) P({right})"]
    assert script_for(client, name, "a2") == [f"P({wrong})"]


def test_collecting_game_rewards_the_last_find(client):
    name = make_book(client)
    reward = library_sound(client, name)
    own = library_sound(client, name)
    group = client.post(f"/b/{name}/groups", data={"kind": "collect"}).get_json()["group"]
    client.post(f"/b/{name}/groups/{group}", data={"reward_sound_id": reward})
    put_areas(client, name, [
        {"id": "a1", "name": "Maus 1", "x": 10, "y": 10, "w": 40, "h": 30,
         "behaviour": "collect", "group": group, "sound_id": own},
        {"id": "a2", "name": "Maus 2", "x": 80, "y": 10, "w": 40, "h": 30,
         "behaviour": "collect", "group": group, "sound_id": own},
        {"id": "a3", "name": "Maus 3", "x": 150, "y": 10, "w": 40, "h": 30,
         "behaviour": "collect", "group": group, "sound_id": own},
    ])
    lines = script_for(client, name, "a1")
    # three mice: the tap that finds the third one plays the reward
    assert lines[0] == f"$gota1==0? $cnt{group}==2? $gota1:=1 $cnt{group}+=1 P({own}) P({reward})"
    assert lines[1] == f"$gota1==0? $gota1:=1 $cnt{group}+=1 P({own})"
    assert lines[2] == f"P({own})"


def test_a_hand_written_script_is_used_as_is(client):
    name = make_book(client)
    put_areas(client, name, [{"id": "a1", "name": "Selbst", "x": 10, "y": 10, "w": 40, "h": 30,
                              "behaviour": "advanced",
                              "script": "$mode==1? $mode:=2 P(t1)\n$mode:=1 P(t2)"}])
    assert script_for(client, name) == ["$mode==1? $mode:=2 P(t1)", "$mode:=1 P(t2)"]


def test_a_hand_written_script_cannot_break_out_of_the_yaml(client):
    name = make_book(client)
    sound = library_sound(client, name)
    put_areas(client, name, [{"id": "a1", "name": "Böse", "x": 10, "y": 10, "w": 40, "h": 30,
                              "behaviour": "advanced",
                              "script": f'P({sound})\nproduct-id: 999\nwelcome: "x'}])
    client.post(f"/b/{name}/build")
    yaml = (client.data_dir / name / "book.yaml").read_text()
    # The structure of the file is untouched: no second product id, no new
    # top-level key, and the injected text does not survive as a script line.
    top_level = [
        line.split(":")[0]
        for line in yaml.splitlines()
        if line and not line[0].isspace() and not line.startswith("#")
    ]
    assert top_level == ["product-id", "comment", "media-path", "scripts"]
    assert "999" not in yaml
    assert "welcome" not in yaml


def test_an_area_with_a_behaviour_but_no_sound_is_reported(client):
    name = make_book(client)
    put_areas(client, name, [{"id": "a1", "name": "Leer", "x": 10, "y": 10, "w": 40, "h": 30,
                              "behaviour": "random", "sound_ids": []}])
    result = client.post(f"/b/{name}/build").get_json()
    assert result["ok"] is False
    assert any("no area with a sound" in p for p in result["problems"])


def test_deleting_a_game_puts_its_areas_back_to_playing(client):
    name = make_book(client)
    sound = library_sound(client, name)
    group = client.post(f"/b/{name}/groups", data={"kind": "quiz"}).get_json()["group"]
    put_areas(client, name, [{"id": "a1", "name": "Antwort", "x": 10, "y": 10, "w": 40, "h": 30,
                              "behaviour": "answer", "group": group, "sound_id": sound}])
    result = client.post(f"/b/{name}/groups/{group}/delete").get_json()
    area = result["book"]["pages"][0]["areas"][0]
    assert area["group"] == ""
    assert area["behaviour"] == "play"


def test_saving_the_layout_cannot_delete_the_library(client):
    """A browser tab with a stale copy must not wipe sounds or games."""
    name = make_book(client)
    sound = library_sound(client, name)
    group = client.post(f"/b/{name}/groups", data={"kind": "quiz"}).get_json()["group"]
    put_areas(client, name, [{"id": "a1", "name": "Hund", "x": 10, "y": 10, "w": 40, "h": 30,
                              "sound_id": sound}])

    # …exactly what an autosave from a tab opened before the sound existed does
    client.put(f"/b/{name}/data", json={
        "title": "Mein Buch", "product_id": 42, "paper": "a4-landscape",
        "sounds": [], "groups": [],
        "pages": [{"id": "s1", "name": "Seite 1", "areas": [
            {"id": "a1", "name": "Hund", "x": 20, "y": 20, "w": 40, "h": 30,
             "sound_id": sound}]}],
    })

    book = client.get(f"/b/{name}/data").get_json()
    assert [s["id"] for s in book["sounds"]] == [sound]
    assert [g["id"] for g in book["groups"]] == [group]
    assert book["pages"][0]["areas"][0]["sound_id"] == sound
    assert book["pages"][0]["areas"][0]["x"] == 20  # the move itself was saved
    assert (client.data_dir / name / "sounds" / f"{sound}.ogg").is_file()


# -- starting points --------------------------------------------------------


def test_the_example_starter_is_ready_to_build(client):
    """A first book should work without the user adding anything."""
    pytest.importorskip("PIL")
    response = client.post("/books", data={"title": "Erstes Buch", "starter": "example"})
    name = response.headers["Location"].rstrip("/").split("/")[-1]

    book = client.get(f"/b/{name}/data").get_json()
    assert book["pages"][0]["image"] == "seiten/s1.png"
    assert (client.data_dir / name / "seiten" / "s1.png").is_file()
    assert [a["name"] for a in book["pages"][0]["areas"]] == ["Hund", "Katze", "Kuh", "Ente"]
    assert all(a["sound_id"] for a in book["pages"][0]["areas"])

    result = client.post(f"/b/{name}/build").get_json()
    assert result["ok"], result
    assert len(result["codes"]) == 4


def test_the_quiz_starter_comes_with_a_game(client):
    pytest.importorskip("PIL")
    response = client.post("/books", data={"title": "Quiz", "starter": "quiz"})
    name = response.headers["Location"].rstrip("/").split("/")[-1]
    book = client.get(f"/b/{name}/data").get_json()

    assert len(book["groups"]) == 1
    group = book["groups"][0]
    assert group["kind"] == "quiz"
    assert group["right_sound_id"] and group["wrong_sound_id"]
    answers = [a for a in book["pages"][0]["areas"] if a["behaviour"] == "answer"]
    assert len(answers) == 4
    assert sum(1 for a in answers if a["correct"]) == 1

    result = client.post(f"/b/{name}/build").get_json()
    assert result["ok"], result


def test_the_search_game_starter_rewards_the_last_find(client):
    pytest.importorskip("PIL")
    response = client.post("/books", data={"title": "Suchen", "starter": "collect"})
    name = response.headers["Location"].rstrip("/").split("/")[-1]
    book = client.get(f"/b/{name}/data").get_json()
    group = book["groups"][0]
    assert group["kind"] == "collect" and group["reward_sound_id"]

    client.post(f"/b/{name}/build")
    yaml = (client.data_dir / name / "book.yaml").read_text()
    # four animals: the tap that finds the fourth plays the reward
    assert f"$cnt{group['id']}==3?" in yaml
    assert yaml.count(f"P({group['reward_sound_id']})") == 4


def test_an_empty_book_stays_empty(client):
    response = client.post("/books", data={"title": "Leer", "starter": "empty"})
    name = response.headers["Location"].rstrip("/").split("/")[-1]
    book = client.get(f"/b/{name}/data").get_json()
    assert book["pages"][0]["areas"] == []
    assert book["pages"][0]["image"] == ""
    assert book["sounds"] == []


def test_the_pen_page_explains_the_way_to_the_pen(client):
    page = client.get("/hilfe/stift").data.decode()
    assert "100%" in page
    assert "tiptoi" in page
    assert "50 mm" in page


# -- passing a book on ------------------------------------------------------


def export(client, name):
    response = client.get(f"/b/{name}/export")
    assert response.status_code == 200
    return response.data


def import_archive(client, blob, filename="buch.tiptoi"):
    return client.post(
        "/books/import",
        data={"book": (io.BytesIO(blob), filename)},
        content_type="multipart/form-data",
    )


def test_an_exported_book_can_be_imported_again(client):
    pytest.importorskip("PIL")
    response = client.post("/books", data={"title": "Bauernhof", "starter": "example"})
    name = response.headers["Location"].rstrip("/").split("/")[-1]
    original = client.get(f"/b/{name}/data").get_json()

    imported = import_archive(client, export(client, name))
    assert imported.status_code == 302
    copy_name = imported.headers["Location"].rstrip("/").split("/")[-1]
    assert copy_name != name

    copy = client.get(f"/b/{copy_name}/data").get_json()
    assert copy["title"] == original["title"]
    assert copy["paper"] == original["paper"]
    assert len(copy["sounds"]) == len(original["sounds"])
    assert [a["name"] for a in copy["pages"][0]["areas"]] == [
        a["name"] for a in original["pages"][0]["areas"]
    ]
    # every picture and sound came across, and every area still plays one
    for sound in copy["sounds"]:
        assert (client.data_dir / copy_name / sound["file"]).is_file()
    assert (client.data_dir / copy_name / copy["pages"][0]["image"]).is_file()
    assert all(a["sound_id"] for a in copy["pages"][0]["areas"])

    # and the imported book builds, which is the only thing that really counts
    assert client.post(f"/b/{copy_name}/build").get_json()["ok"]


def test_an_imported_book_keeps_the_codes_of_the_original(client):
    """A page printed before the export has to keep working afterwards."""
    name = make_book(client, "Codes")
    book = client.get(f"/b/{name}/data").get_json()
    book["pages"][0]["areas"] = [{"id": "a1", "name": "Hund", "x": 10, "y": 10, "w": 30, "h": 30}]
    client.put(f"/b/{name}/data", json=book)
    add_sound(client, name, "a1")
    original = client.post(f"/b/{name}/build").get_json()

    copy_name = (
        import_archive(client, export(client, name))
        .headers["Location"]
        .rstrip("/")
        .split("/")[-1]
    )
    assert (client.data_dir / copy_name / "book.codes.yaml").is_file()
    assert client.post(f"/b/{copy_name}/build").get_json()["codes"] == original["codes"]


def test_import_rejects_anything_that_is_not_a_book(client):
    import zipfile

    plain = io.BytesIO()
    with zipfile.ZipFile(plain, "w") as archive:
        archive.writestr("holiday.jpg", b"not a book")
    assert import_archive(client, plain.getvalue()).status_code == 302
    assert list(client.data_dir.iterdir()) == []

    assert import_archive(client, b"this is not a zip at all").status_code == 302
    assert import_archive(client, b"x", filename="virus.exe").status_code == 302
    assert list(client.data_dir.iterdir()) == []


def test_import_cannot_write_outside_its_own_book(client):
    """File names in the archive are hostile input; ours are the ones used."""
    import zipfile

    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr(
            "tiptoi-buch.json",
            json.dumps(
                {
                    "format": "tttool-web-book",
                    "version": 1,
                    "book": {
                        "title": "Böse",
                        "pages": [{"id": "s1", "image": "../../../escape.png", "areas": []}],
                        "sounds": [{"id": "t1", "file": "../../../escape.ogg"}],
                    },
                }
            ),
        )
        archive.writestr("../../../escape.png", b"PNG")
        archive.writestr("../../../escape.ogg", b"OGG")

    response = import_archive(client, payload.getvalue())
    assert response.status_code == 302
    name = response.headers["Location"].rstrip("/").split("/")[-1]
    assert not (client.data_dir.parent / "escape.png").exists()
    assert not (client.data_dir / "escape.ogg").exists()

    # The contents still arrive — under the names *we* pick, inside the book.
    book = client.get(f"/b/{name}/data").get_json()
    assert book["pages"][0]["image"] == "seiten/s1.png"
    assert [s["file"] for s in book["sounds"]] == ["sounds/t1.ogg"]
    written = {
        p.relative_to(client.data_dir).as_posix()
        for p in client.data_dir.rglob("*")
        if p.is_file()
    }
    assert all(path.startswith(f"{name}/") for path in written), written


# -- language ---------------------------------------------------------------


def test_the_interface_language_can_be_switched(client):
    assert "Your Tiptoi books" in client.get("/").data.decode()

    client.post("/language", data={"lang": "de"})
    assert "Deine Tiptoi-Bücher" in client.get("/").data.decode()

    client.post("/language", data={"lang": "en"})
    assert "Your Tiptoi books" in client.get("/").data.decode()


def test_an_unknown_language_is_refused(client):
    client.post("/language", data={"lang": "../../etc"})
    assert "Your Tiptoi books" in client.get("/").data.decode()


def test_the_first_steps_page_walks_through_all_four_steps(client):
    page = client.get("/hilfe/erste-schritte").data.decode()
    for heading in ("1. Start a book", "2. Your picture, your areas", "3. Give each area a sound"):
        assert heading in page
    # and it points at the page that covers the last step in detail
    assert "/hilfe/stift" in page


def test_every_page_offers_the_language_switch_and_a_skip_link(client):
    name = make_book(client)
    for path in ("/", f"/b/{name}", "/hilfe/erste-schritte", "/hilfe/stift", "/help"):
        page = client.get(path).data.decode()
        assert 'href="#main"' in page, path
        assert 'action="/language"' in page, path
        assert 'id="main"' in page, path


# -- large books ------------------------------------------------------------


def big_picture(width=2400, height=1700):
    """A picture that does not compress away, like a real scan."""
    Image = pytest.importorskip("PIL.Image")
    import random

    random.seed(3)
    small = Image.frombytes(
        "RGB", (width // 8, height // 8),
        bytes(random.getrandbits(8) for _ in range((width // 8) * (height // 8) * 3)),
    )
    buffer = io.BytesIO()
    small.resize((width, height)).save(buffer, "PNG")
    return buffer.getvalue()


def upload_picture(client, name, page_id="s1", data=None, filename="seite.png"):
    return client.post(
        f"/b/{name}/pages/{page_id}/image",
        data={"image": (io.BytesIO(data if data is not None else big_picture()), filename)},
        content_type="multipart/form-data",
    ).get_json()


def test_the_editor_gets_a_small_copy_of_a_big_picture(client):
    """A 300 dpi scan must not be downloaded in full just to draw on it."""
    name = make_book(client)
    original = big_picture()
    result = upload_picture(client, name, data=original)

    assert result["preview"] and result["preview"] != result["image"]
    assert result["url"].endswith(result["preview"])
    preview = client.data_dir / name / result["preview"]
    assert preview.is_file()
    assert preview.stat().st_size < len(original) / 5

    from PIL import Image

    with Image.open(preview) as shown:
        assert max(shown.size) <= 1600
    # the original is kept untouched: it is what gets printed
    assert (client.data_dir / name / result["image"]).read_bytes() == original


def test_a_small_picture_needs_no_second_copy(client):
    name = make_book(client)
    result = upload_picture(client, name, data=big_picture(200, 150))
    assert result["preview"] == result["image"]
    assert not list((client.data_dir / name / "seiten").glob("*vorschau*"))


def test_replacing_a_picture_drops_the_old_copies(client):
    name = make_book(client)
    first = upload_picture(client, name)
    assert (client.data_dir / name / first["preview"]).is_file()
    second = upload_picture(client, name, data=big_picture(2000, 1400), filename="neu.jpg")
    assert second["image"] == "seiten/s1.jpg"
    # the .png and its derived copies are gone, only the new ones remain
    left = sorted(p.name for p in (client.data_dir / name / "seiten").iterdir())
    assert all(not n.endswith(".png") for n in left), left


def test_the_printed_pdf_stays_small(client):
    """The page picture goes into the PDF as JPEG, not as raw pixels."""
    name = make_book(client)
    upload_picture(client, name)
    put_areas(client, name, [{"id": "a1", "name": "Hund", "x": 20, "y": 20, "w": 40, "h": 30}])
    add_sound(client, name, "a1")

    result = client.post(f"/b/{name}/build").get_json()
    assert result["ok"], result
    pdf = (client.data_dir / name / result["pdf"]).read_bytes()

    # Raw pixels for this picture would be several megabytes; as JPEG it is
    # a fraction of that, at the same resolution.
    assert len(pdf) < 2_000_000, len(pdf)
    assert b"/DCTDecode" in pdf

    from pypdf import PdfReader

    page = PdfReader(io.BytesIO(pdf)).pages[0]
    assert abs(float(page.mediabox.width) / 72 * 25.4 - 297) < 1
    # The dots are tiling patterns and must have survived untouched: one for
    # the area, one for the power-on field.
    assert len(page["/Resources"]["/Pattern"]) == 2


def test_deleting_a_page_takes_its_picture_with_it(client):
    name = make_book(client)
    client.post(f"/b/{name}/pages")          # a second page, so the first may go
    upload_picture(client, name)
    seiten = client.data_dir / name / "seiten"
    assert list(seiten.iterdir())

    client.post(f"/b/{name}/pages/s1/delete")
    assert not list(seiten.iterdir())


def test_a_duplicated_page_keeps_the_shared_picture(client):
    """Both pages point at one file — deleting one must not blind the other."""
    name = make_book(client)
    upload_picture(client, name)
    copy = client.post(f"/b/{name}/pages/s1/duplicate").get_json()
    image = next(p["image"] for p in copy["book"]["pages"] if p["id"] == copy["page"])
    assert image

    client.post(f"/b/{name}/pages/s1/delete")
    assert (client.data_dir / name / image).is_file()


def test_a_shrinking_book_does_not_keep_old_printed_pages(client):
    name = make_book(client)
    client.post(f"/b/{name}/pages")
    book = client.get(f"/b/{name}/data").get_json()
    for page in book["pages"]:
        page["areas"] = [{"id": f"a{page['id']}", "name": "X", "x": 20, "y": 20, "w": 40, "h": 30}]
    client.put(f"/b/{name}/data", json=book)
    for page in book["pages"]:
        add_sound(client, name, f"a{page['id']}")
    assert client.post(f"/b/{name}/build").get_json()["ok"]
    druck = client.data_dir / name / "druck"
    assert sorted(p.name for p in druck.glob("seite-*.pdf")) == ["seite-1.pdf", "seite-2.pdf"]

    client.post(f"/b/{name}/pages/{book['pages'][1]['id']}/delete")
    assert client.post(f"/b/{name}/build").get_json()["ok"]
    assert sorted(p.name for p in druck.glob("seite-*.pdf")) == ["seite-1.pdf"]


# -- backup and restore -----------------------------------------------------


def test_everything_can_be_backed_up_and_put_back(client):
    pytest.importorskip("PIL")
    first = make_book(client, "Bauernhof")
    put_areas(client, first, [{"id": "a1", "name": "Hund", "x": 20, "y": 20, "w": 40, "h": 30}])
    add_sound(client, first, "a1")
    second = make_book(client, "Zoo")

    backup = client.get("/books/backup")
    assert backup.status_code == 200
    assert ".tiptoi" in backup.headers["Content-Disposition"]

    import zipfile

    with zipfile.ZipFile(io.BytesIO(backup.data)) as archive:
        names = archive.namelist()
    assert "tiptoi-sicherung.json" in names
    assert sorted(n for n in names if n.startswith("buecher/")) == [
        "buecher/bauernhof.tiptoi",
        "buecher/zoo.tiptoi",
    ]

    restored = import_archive(client, backup.data, "sicherung.tiptoi")
    assert restored.status_code == 302
    listed = client.get("/").data.decode()
    for name in ("bauernhof", "bauernhof-2", "zoo", "zoo-2"):
        assert name in listed, name

    copy = client.get("/b/bauernhof-2/data").get_json()
    assert [a["name"] for a in copy["pages"][0]["areas"]] == ["Hund"]
    assert (client.data_dir / "bauernhof-2" / copy["sounds"][0]["file"]).is_file()


def test_an_empty_server_says_there_is_nothing_to_back_up(client):
    assert client.get("/books/backup", follow_redirects=True).status_code == 200
    assert not list(client.data_dir.iterdir())


# -- books made by earlier versions -----------------------------------------


#: A book exactly as version 1.1 wrote it: no library, no behaviours, no
#: groups, no preview — the sound file hangs off the area.
BOOK_V1 = {
    "title": "Altes Buch",
    "product_id": 42,
    "paper": "a4-landscape",
    "pages": [
        {
            "id": "s1",
            "name": "Seite 1",
            "image": "seiten/s1.png",
            "areas": [
                {"id": "a1", "name": "Hund", "x": 20, "y": 20, "w": 40, "h": 30,
                 "sound": "sounds/a1.ogg", "sound_name": "wau.mp3"},
                {"id": "a2", "name": "Stumm", "x": 80, "y": 20, "w": 40, "h": 30},
            ],
        }
    ],
    "version": 1,
}


def test_a_book_from_an_earlier_version_still_opens_and_builds(client):
    name = make_book(client, "Altes Buch")
    project = client.data_dir / name
    (project / "sounds").mkdir(exist_ok=True)
    (project / "sounds" / "a1.ogg").write_bytes(b"OggS old")
    upload_picture(client, name)
    (project / "book.json").write_text(json.dumps(BOOK_V1), encoding="utf-8")

    assert client.get(f"/b/{name}").status_code == 200
    book = client.get(f"/b/{name}/data").get_json()

    # The area's own sound has become a library entry, still pointing at the
    # very same file, and the silent area is still silent.
    assert len(book["sounds"]) == 1
    sound = book["sounds"][0]
    assert sound["file"] == "sounds/a1.ogg"
    assert sound["name"] == "wau"
    areas = {a["name"]: a for a in book["pages"][0]["areas"]}
    assert areas["Hund"]["sound_id"] == sound["id"]
    assert areas["Hund"]["behaviour"] == "play"
    assert areas["Stumm"]["sound_id"] == ""

    assert client.post(f"/b/{name}/build").get_json()["ok"]


def test_an_old_book_without_a_preview_shows_its_original(client):
    """No preview in the file means the editor falls back to the picture."""
    name = make_book(client, "Ohne Vorschau")
    upload_picture(client, name)
    project = client.data_dir / name
    stored = json.loads((project / "book.json").read_text())
    del stored["pages"][0]["preview"]
    (project / "book.json").write_text(json.dumps(stored), encoding="utf-8")

    book = client.get(f"/b/{name}/data").get_json()
    assert book["pages"][0]["preview"] == ""
    assert book["pages"][0]["image"]
    assert client.get(f"/b/{name}").status_code == 200


def test_the_editor_lists_every_area_of_the_page(client):
    """The list is drawn in the browser, so check its plumbing is all there."""
    name = make_book(client)
    page = client.get(f"/b/{name}").data.decode()
    assert 'id="area-list"' in page
    assert 'id="area-count"' in page
    assert 'id="toast"' in page

    strings = json.loads(re.search(
        r'<script id="book-strings" type="application/json">(.*?)</script>', page, re.S
    ).group(1))
    for needed in ("too small", "Sound …", "Delete area", "“{name}” deleted.", "Undo",
                   "No areas yet — drag one onto the picture."):
        assert needed in strings, needed
    # deleting an area is undoable, so it no longer asks first
    assert "Delete this area?" not in strings


def test_the_dots_are_printed_at_the_pitch_the_pen_expects(client):
    """The one measurement that decides whether a printed page works at all.

    One cell of the OID grid is 1/25 inch — 2.88 pt, 1.016 mm — and tttool's
    own PDF output tiles at exactly that. A page that tiles at 1.000 mm looks
    perfect, measures 50 mm on the ruler, and no pen can read it.
    """
    name = make_book(client)
    put_areas(client, name, [{"id": "a1", "name": "Hund", "x": 20, "y": 20, "w": 40, "h": 30}])
    add_sound(client, name, "a1")
    result = client.post(f"/b/{name}/build").get_json()
    assert result["ok"], result

    from pypdf import PdfReader

    for relpath in (result["pages"][0], result["test_pdf"]):
        page = PdfReader(str(client.data_dir / name / relpath)).pages[0]
        patterns = page["/Resources"]["/Pattern"]
        assert patterns, relpath
        for _, ref in patterns.items():
            tile = ref.get_object()
            matrix = [float(v) for v in (tile.get("/Matrix") or [1, 0, 0, 1, 0, 0])]
            step = float(tile.get("/XStep")) * abs(matrix[0])
            assert abs(step - 2.88) < 0.005, f"{relpath}: {step} pt per cell, expected 2.88"


def test_the_page_scale_does_not_depend_on_our_constant(client):
    """The unit scale is read from tttool's pattern, not assumed."""
    from tttool_web.bookbuild import OID_CELL_MM, UNITS_PER_MM, _read_patterns

    # 48 units per 1/25 inch cell — a millimetre is 47.24 units, not 48.
    assert abs(UNITS_PER_MM - 1200 / 25.4) < 0.001
    assert abs(OID_CELL_MM - 1.016) < 0.0001

    name = make_book(client)
    put_areas(client, name, [{"id": "a1", "name": "Hund", "x": 20, "y": 20, "w": 40, "h": 30}])
    add_sound(client, name, "a1")
    client.post(f"/b/{name}/build")

    patterns, units = _read_patterns(client.data_dir / name / "druck" / "codes")
    assert patterns
    assert abs(units - UNITS_PER_MM) < 0.001

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

    monkeypatch.setenv("TTTOOL_WEB_DATA", str(data))
    monkeypatch.setenv("TTTOOL_BIN", str(tttool))
    monkeypatch.setenv("FFMPEG_BIN", str(ffmpeg))
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
    return client.post(
        f"/b/{name}/areas/{area_id}/sound",
        data={"sound": (io.BytesIO(b"audio"), filename)},
        content_type="multipart/form-data",
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
                              "sound": "../../../etc/passwd"}])
    area = json.loads((client.data_dir / name / "book.json").read_text())["pages"][0]["areas"][0]
    assert area["sound"] == ""


def test_sound_upload_is_converted_and_linked(client):
    name = make_book(client)
    put_areas(client, name, [{"id": "a1", "name": "Hund", "x": 10, "y": 10, "w": 40, "h": 30}])
    result = add_sound(client, name, "a1").get_json()
    assert result["ok"]
    assert result["sound"] == "sounds/a1.ogg"
    assert result["sound_name"] == "bark.mp3"
    assert (client.data_dir / name / "sounds" / "a1.ogg").is_file()
    # the upload itself is not kept
    assert not list((client.data_dir / name / "sounds").glob("*-original*"))


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
    assert "s1_a1: P(a1)" in yaml
    assert "s1_a2: P(a2)" in yaml


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

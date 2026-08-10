"""Tests for the web GUI.

They run against a stub "tttool" so that they work without a Haskell toolchain;
the real binary is exercised by the repository's own test suite.
"""

import io
import os
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

STUB = """#!/bin/sh
# Minimal tttool stand-in: enough to check argument passing and file creation.
echo "argv: $*"
case "$1" in
  --help) echo "tttool-1.11 -- The swiss army knife for the Tiptoi hacker" ;;
esac
for arg in "$@"; do
  case "$arg" in
    *.gme) [ -f "$arg" ] || echo "gme" > "$arg" ;;
  esac
done
for arg in "$@"; do
  case "$arg" in
    oid-codes|oid-code) echo "png" > oid-1234.png ;;
    fail) echo "boom" >&2; exit 3 ;;
  esac
done
exit 0
"""


FFMPEG_STUB = """#!/bin/sh
echo "ffmpeg $*"
echo ogg > "$(eval echo \\${$#})"
"""


@pytest.fixture()
def client(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    stub = tmp_path / "tttool-stub"
    stub.write_text(STUB)
    stub.chmod(0o755)
    ffmpeg = tmp_path / "ffmpeg-stub"
    ffmpeg.write_text(FFMPEG_STUB)
    ffmpeg.chmod(0o755)
    examples = tmp_path / "examples"
    (examples / "example").mkdir(parents=True)
    (examples / "example.yaml").write_text("product-id: 42\n")
    (examples / "example" / "hello.ogg").write_bytes(b"ogg")

    monkeypatch.setenv("TTTOOL_WEB_DATA", str(data))
    monkeypatch.setenv("TTTOOL_BIN", str(stub))
    monkeypatch.setenv("FFMPEG_BIN", str(ffmpeg))
    monkeypatch.setenv("TTTOOL_WEB_EXAMPLES", str(examples))
    # These tests assert on the source strings, not on a translation.
    monkeypatch.setenv("TTTOOL_WEB_LANG", "en")
    for module in [m for m in list(sys.modules) if m.startswith("tttool_web")]:
        del sys.modules[module]

    from tttool_web.app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as test_client:
        test_client.data_dir = data
        yield test_client


def make_project(client, name="book", **form):
    return client.post("/projects", data={"name": name, **form}, follow_redirects=True)


# -- projects ---------------------------------------------------------------


def test_index_empty(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"No books yet" in response.data


def test_create_project_with_template(client):
    response = make_project(client, start="template")
    assert response.status_code == 200
    assert (client.data_dir / "book" / "book.yaml").is_file()
    assert b"book.yaml" in response.data


def test_create_project_from_example(client):
    make_project(client, start="example")
    assert (client.data_dir / "book" / "example.yaml").is_file()
    assert (client.data_dir / "book" / "example" / "hello.ogg").is_file()


def test_create_empty_project(client):
    make_project(client, start="empty")
    assert list((client.data_dir / "book").iterdir()) == []


@pytest.mark.parametrize("name", ["../evil", "a/b", "", ".hidden", "x" * 65, "sp ace"])
def test_invalid_project_names_are_rejected(client, name):
    response = client.post("/projects", data={"name": name}, follow_redirects=True)
    assert response.status_code == 200
    assert list(client.data_dir.iterdir()) == []


def test_delete_project(client):
    make_project(client)
    client.post("/p/book/delete", follow_redirects=True)
    assert not (client.data_dir / "book").exists()


def test_unknown_project_is_404(client):
    assert client.get("/p/nope").status_code == 404


# -- files ------------------------------------------------------------------


def test_upload_and_download(client):
    make_project(client)
    data = {"files": (io.BytesIO(b"hello"), "greeting.ogg"), "subdir": "audio"}
    response = client.post("/p/book/upload", data=data, content_type="multipart/form-data",
                           follow_redirects=True)
    assert response.status_code == 200
    assert (client.data_dir / "book" / "audio" / "greeting.ogg").read_bytes() == b"hello"

    response = client.get("/p/book/download?path=audio/greeting.ogg")
    assert response.data == b"hello"


def test_upload_strips_paths(client):
    make_project(client)
    data = {"files": (io.BytesIO(b"x"), "../../etc/passwd")}
    client.post("/p/book/upload", data=data, content_type="multipart/form-data", follow_redirects=True)
    assert (client.data_dir / "book" / "passwd").is_file()
    assert not (client.data_dir.parent / "etc").exists()


@pytest.mark.parametrize("path", ["../../etc/passwd", "..%2f..%2fsecret", "/etc/passwd"])
def test_download_cannot_escape_the_project(client, path):
    make_project(client)
    (client.data_dir.parent / "secret").write_text("nope")
    response = client.get("/p/book/download", query_string={"path": path}, follow_redirects=True)
    assert b"nope" not in response.data


def test_edit_roundtrip(client):
    make_project(client, start="template")
    response = client.post(
        "/p/book/edit", data={"path": "book.yaml", "content": "product-id: 7\n"}, follow_redirects=True
    )
    assert response.status_code == 200
    assert (client.data_dir / "book" / "book.yaml").read_text() == "product-id: 7\n"


def test_delete_file(client):
    make_project(client, start="template")
    client.post("/p/book/files/delete", data={"path": "book.yaml"}, follow_redirects=True)
    assert not (client.data_dir / "book" / "book.yaml").exists()


def test_archive_contains_files(client):
    make_project(client, start="template")
    response = client.get("/p/book/archive")
    with zipfile.ZipFile(io.BytesIO(response.data)) as zf:
        assert "book/book.yaml" in zf.namelist()


# -- running tttool ---------------------------------------------------------


def test_run_assemble(client):
    make_project(client, start="template")
    response = client.post("/p/book/run", data={"command": "assemble", "yaml": "book.yaml", "out": "book.gme"})
    result = response.get_json()
    assert result["ok"], result
    assert "assemble book.yaml book.gme" in result["command"]
    assert result["files"]["created"] == ["book.gme"]


def test_run_rejects_unknown_command(client):
    make_project(client)
    response = client.post("/p/book/run", data={"command": "rm -rf /"})
    assert response.status_code == 400
    assert "Unknown command" in response.get_json()["error"]


def test_run_rejects_missing_input_file(client):
    make_project(client)
    response = client.post("/p/book/run", data={"command": "info", "gme": "nope.gme"})
    assert response.status_code == 400
    assert "No such file" in response.get_json()["error"]


def test_run_rejects_paths_outside_the_project(client):
    make_project(client)
    (client.data_dir.parent / "outside.gme").write_bytes(b"x")
    response = client.post("/p/book/run", data={"command": "info", "gme": "../../outside.gme"})
    assert response.status_code == 400


def test_run_rejects_bad_offset(client):
    make_project(client, start="template")
    (client.data_dir / "book" / "a.gme").write_bytes(b"x")
    response = client.post("/p/book/run", data={"command": "segment", "gme": "a.gme", "pos": "0x12; rm -rf /"})
    assert response.status_code == 400


def test_run_requires_required_parameters(client):
    make_project(client, start="template")
    response = client.post("/p/book/run", data={"command": "oid-code", "range": "", "dir": "codes"})
    assert response.status_code == 400
    assert "required" in response.get_json()["error"]


def test_arguments_are_not_shell_interpreted(client):
    """A file name with shell metacharacters is passed through verbatim."""
    make_project(client)
    (client.data_dir / "book" / "we;ird.gme").write_bytes(b"x")
    response = client.post("/p/book/run", data={"command": "info", "gme": "we;ird.gme"})
    result = response.get_json()
    assert result["ok"]
    assert "argv: info we;ird.gme" in result["stdout"]


def test_file_names_are_never_mistaken_for_options(client):
    make_project(client)
    (client.data_dir / "book" / "-x.gme").write_bytes(b"x")
    result = client.post("/p/book/run", data={"command": "info", "gme": "-x.gme"}).get_json()
    assert result["ok"]
    assert "argv: info ./-x.gme" in result["stdout"]


def test_language_cannot_smuggle_a_flag(client):
    make_project(client)
    (client.data_dir / "book" / "a.gme").write_bytes(b"x")
    response = client.post(
        "/p/book/run", data={"command": "set-language", "gme": "a.gme", "lang": "--empty"}
    )
    assert response.status_code == 400


def test_oid_codes_runs_in_the_output_directory(client):
    make_project(client, start="template")
    response = client.post(
        "/p/book/run",
        data={"command": "oid-codes", "yaml": "book.yaml", "dir": "codes",
              "dpi": "600", "pixel_size": "2", "code_dim": "30", "image_format": "png"},
    )
    result = response.get_json()
    assert result["ok"], result
    assert result["cwd"] == "codes"
    assert "--dpi 600" in result["command"]
    assert "--image-format png" in result["command"]
    assert "oid-codes ../book.yaml" in result["command"]
    assert (client.data_dir / "book" / "codes" / "oid-1234.png").is_file()
    assert "codes/oid-1234.png" in result["files"]["created"]


def test_failing_command_reports_stderr(client, monkeypatch):
    make_project(client, start="template")
    (client.data_dir / "book" / "a.gme").write_bytes(b"x")
    from tttool_web import commands

    monkeypatch.setitem(
        commands.COMMANDS_BY_ID,
        "info",
        commands.Command(
            id="info", label="info", group="Inspect", description="",
            params=commands.COMMANDS_BY_ID["info"].params,
            build=lambda v: ["fail", v["gme"]],
        ),
    )
    result = client.post("/p/book/run", data={"command": "info", "gme": "a.gme"}).get_json()
    assert not result["ok"]
    assert result["exit_code"] == 3
    assert "boom" in result["stderr"]


def test_invalid_dpi_is_rejected(client):
    make_project(client, start="template")
    response = client.post(
        "/p/book/run", data={"command": "oid-codes", "yaml": "book.yaml", "dir": "codes", "dpi": "99999"}
    )
    assert response.status_code == 400


# -- misc -------------------------------------------------------------------


def test_pages_render(client):
    make_project(client, start="template")
    for url in ["/", "/p/book", "/p/book?cmd=oid-table", "/p/book/files",
                "/p/book/edit?path=book.yaml", "/help"]:
        response = client.get(url)
        assert response.status_code == 200, url


def test_tooltips_are_rendered(client):
    make_project(client, start="example")
    page = client.get("/p/book").data.decode()
    # The command tabs carry their description …
    assert 'data-tip="Compile a YAML source file into a GME file for the pen."' in page
    # … the parameters their own explanation …
    assert "The number that ties a GME file to a book" in page
    # … and the file rows explain their actions.
    assert "Convert to mono Ogg Vorbis" in page
    assert page.count("data-tip=") > 50


def test_preview_serves_audio_inline(client):
    make_project(client, start="example")
    response = client.get("/p/book/raw?path=example/hello.ogg")
    assert response.status_code == 200
    assert response.mimetype == "audio/ogg"
    assert "attachment" not in response.headers.get("Content-Disposition", "")


def test_convert_audio(client):
    make_project(client)
    data = {"files": (io.BytesIO(b"mp3"), "song.mp3")}
    client.post("/p/book/upload", data=data, content_type="multipart/form-data", follow_redirects=True)
    result = client.post("/p/book/convert", data={"path": "song.mp3"}).get_json()
    assert result["ok"], result
    assert result["output"] == "song.ogg"
    assert "-ar 22050 -ac 1" in result["command"]


def test_cross_site_post_is_blocked(client):
    make_project(client, start="template")
    response = client.post(
        "/p/book/files/delete", data={"path": "book.yaml"}, headers={"Origin": "https://evil.example"}
    )
    assert response.status_code == 403
    assert (client.data_dir / "book" / "book.yaml").is_file()

    same_origin = client.post(
        "/p/book/files/delete",
        data={"path": "book.yaml"},
        headers={"Origin": "http://localhost"},
        follow_redirects=True,
    )
    assert same_origin.status_code == 200
    assert not (client.data_dir / "book" / "book.yaml").exists()


def test_healthz(client):
    payload = client.get("/healthz").get_json()
    assert payload["status"] == "ok"
    assert payload["tttool"] == "1.11"
    assert payload["version"]
    assert payload["build"] == {"ref": "", "commit": ""}


def test_build_stamp_is_reported(tmp_path, monkeypatch):
    """Beta testers report the build id, so it has to reach both UI and API."""
    monkeypatch.setenv("TTTOOL_WEB_DATA", str(tmp_path))
    monkeypatch.setenv("TTTOOL_WEB_BUILD_REF", "beta")
    monkeypatch.setenv("TTTOOL_WEB_BUILD_SHA", "a1b2c3d4e5f6")
    for module in [m for m in list(sys.modules) if m.startswith("tttool_web")]:
        del sys.modules[module]
    from tttool_web.app import create_app

    with create_app().test_client() as client:
        assert client.get("/healthz").get_json()["build"] == {"ref": "beta", "commit": "a1b2c3d"}
        assert "beta (a1b2c3d)" in client.get("/").data.decode()


def test_help_page(client):
    assert b"oid-table" in client.get("/help").data


def test_basic_auth(tmp_path, monkeypatch):
    monkeypatch.setenv("TTTOOL_WEB_DATA", str(tmp_path))
    monkeypatch.setenv("TTTOOL_WEB_USER", "u")
    monkeypatch.setenv("TTTOOL_WEB_PASSWORD", "p")
    for module in [m for m in list(sys.modules) if m.startswith("tttool_web")]:
        del sys.modules[module]
    from tttool_web.app import create_app

    with create_app().test_client() as client:
        assert client.get("/").status_code == 401
        assert client.get("/healthz").status_code == 200  # for container health checks
        import base64

        token = base64.b64encode(b"u:p").decode()
        assert client.get("/", headers={"Authorization": f"Basic {token}"}).status_code == 200

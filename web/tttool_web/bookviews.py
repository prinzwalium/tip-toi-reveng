"""Routes for the book editor.

Registered from :func:`tttool_web.app.create_app` so that they share its
authentication and error handling.
"""

import re

from flask import jsonify, redirect, render_template, request, url_for

from .book import PAPER_SIZES, Book, store_upload
from .bookbuild import build, converters_available
from .i18n import t
from .projects import Project, ProjectError, list_projects
from .runner import convert_audio

#: Strings the editor needs in the browser.
JS_STRINGS = [
    "Saved",
    "Saving …",
    "Could not save — is the server still running?",
    "Delete this area?",
    "Building …",
    "Area",
    "No sound yet — the area stays silent.",
    "Print this",
    "Copy this onto the pen",
    "Print test page first",
    "Delete this page with everything on it?",
    "Click the corners; click the first one again to close the shape.",
    "Done",
    "Page {number}",
    "Drag on the picture to create an area.",
]


def _slug(title: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-").lower()
    return slug[:48] or "buch"


def register_book_routes(app, route, get_project):
    def get_book_project(name: str) -> tuple[Project, Book]:
        project = get_project(name)
        return project, Book.load(project)

    # -- creating ---------------------------------------------------------

    @route("/books", methods=["POST"])
    def create_book():
        title = (request.form.get("title") or "").strip()[:80]
        if not title:
            raise ProjectError(t("Please give your book a name."))
        paper = request.form.get("paper") if request.form.get("paper") in PAPER_SIZES else None

        taken = {p["name"] for p in list_projects()}
        base = _slug(title)
        name, suffix = base, 2
        while name in taken:
            name, suffix = f"{base}-{suffix}", suffix + 1

        project = Project(name).create()
        book = Book(title=title, paper=paper or Book().paper)
        book.product_id = _free_product_id(taken)
        book.add_page("Seite 1")
        book.save(project)
        (project.path / "sounds").mkdir(exist_ok=True)
        (project.path / "seiten").mkdir(exist_ok=True)
        return redirect(url_for("edit_book", name=project.name))

    def _free_product_id(taken_names: set[str]) -> int:
        """Give every book its own product number, so two books can coexist."""
        used = set()
        for other in taken_names:
            try:
                project = Project(other)
                if Book.is_book(project):
                    used.add(Book.load(project).product_id)
            except ProjectError:
                continue
        for candidate in range(42, 1000):
            if candidate not in used:
                return candidate
        return 42

    # -- the editor -------------------------------------------------------

    @route("/b/<name>")
    def edit_book(name):
        project, book = get_book_project(name)
        problems, hints = book.check()
        return render_template(
            "book_edit.html",
            project=project,
            book=book,
            page_size=book.page_size,
            power_field=book.power_field,
            problems=problems,
            hints=hints,
            can_print=converters_available(),
            js_strings={key: t(key) for key in JS_STRINGS},
        )

    @route("/b/<name>/data", methods=["GET", "PUT"])
    def book_data(name):
        project, book = get_book_project(name)
        if request.method == "GET":
            return jsonify(book.to_dict())
        updated = Book.from_dict(request.get_json(silent=True) or {})
        # The pictures and sounds on disk belong to the server, not the browser.
        by_page = {p.id: p for p in book.pages}
        for page in updated.pages:
            known = by_page.get(page.id)
            if known is None:
                continue
            page.image = known.image
            known_areas = {a.id: a for a in known.areas}
            for area in page.areas:
                if area.id in known_areas:
                    area.sound = known_areas[area.id].sound
                    area.sound_name = known_areas[area.id].sound_name
                else:
                    area.sound = area.sound_name = ""
        updated.save(project)
        problems, hints = updated.check()
        return jsonify({"ok": True, "problems": problems, "hints": hints})

    # -- pictures and sounds ----------------------------------------------

    @route("/b/<name>/pages/<page_id>/image", methods=["POST"])
    def upload_page_image(name, page_id):
        project, book = get_book_project(name)
        page = book.page(page_id)
        upload = request.files.get("image")
        if not upload or not upload.filename:
            raise ProjectError(t("Please choose a picture."))
        page.image, _ = store_upload(project, "seiten", page.id, upload)
        book.save(project)
        return jsonify({"ok": True, "image": page.image,
                        "url": url_for("raw", name=project.name, path=page.image)})

    @route("/b/<name>/areas/<area_id>/sound", methods=["POST"])
    def upload_area_sound(name, area_id):
        project, book = get_book_project(name)
        area = next(
            (a for page in book.pages for a in page.areas if a.id == area_id), None
        )
        if area is None:
            raise ProjectError(t("This area no longer exists."))
        upload = request.files.get("sound")
        if not upload or not upload.filename:
            raise ProjectError(t("Please choose a sound file."))

        # Keep the upload aside, convert it to what the pen needs, drop the rest.
        raw_path, original = store_upload(project, "sounds", f"{area.id}-original", upload)
        try:
            result = convert_audio(project, raw_path, f"sounds/{area.id}.ogg")
        finally:
            (project.path / raw_path).unlink(missing_ok=True)
        if not result["ok"]:
            raise ProjectError(
                t("This sound file could not be converted. Try MP3, WAV or Ogg.")
            )
        area.sound = result["output"]
        area.sound_name = original
        book.save(project)
        return jsonify(
            {
                "ok": True,
                "sound": area.sound,
                "sound_name": area.sound_name,
                "url": url_for("raw", name=project.name, path=area.sound),
            }
        )

    @route("/b/<name>/areas/<area_id>/sound/delete", methods=["POST"])
    def delete_area_sound(name, area_id):
        project, book = get_book_project(name)
        for page in book.pages:
            for area in page.areas:
                if area.id == area_id and area.sound:
                    (project.path / area.sound).unlink(missing_ok=True)
                    area.sound = area.sound_name = ""
        book.save(project)
        return jsonify({"ok": True})

    # -- building ---------------------------------------------------------

    @route("/b/<name>/build", methods=["POST"])
    def build_book(name):
        project, book = get_book_project(name)
        if not converters_available():
            raise ProjectError(
                t("This installation cannot create PDFs. Please update the container image.")
            )
        result = build(project, book)
        payload = result.as_dict()
        payload["gme_url"] = (
            url_for("download", name=project.name, path=result.gme) if result.gme else ""
        )
        payload["pdf_url"] = (
            url_for("download", name=project.name, path=result.pdf) if result.pdf else ""
        )
        payload["test_pdf_url"] = (
            url_for("download", name=project.name, path=result.test_pdf) if result.test_pdf else ""
        )
        return jsonify(payload)

    # -- pages ------------------------------------------------------------

    @route("/b/<name>/pages", methods=["POST"])
    def add_page(name):
        project, book = get_book_project(name)
        page = book.add_page()
        book.save(project)
        return jsonify({"ok": True, "book": book.to_dict(), "page": page.id})

    @route("/b/<name>/pages/<page_id>/duplicate", methods=["POST"])
    def duplicate_page(name, page_id):
        project, book = get_book_project(name)
        page = book.duplicate_page(book.page(page_id))
        book.save(project)
        return jsonify({"ok": True, "book": book.to_dict(), "page": page.id})

    @route("/b/<name>/pages/<page_id>/delete", methods=["POST"])
    def delete_page(name, page_id):
        project, book = get_book_project(name)
        book.remove_page(page_id)
        book.save(project)
        return jsonify({"ok": True, "book": book.to_dict(), "page": book.pages[0].id})

    @route("/b/<name>/pages/<page_id>/move", methods=["POST"])
    def move_page(name, page_id):
        project, book = get_book_project(name)
        delta = -1 if (request.form.get("direction") or request.args.get("direction")) == "up" else 1
        book.move_page(page_id, delta)
        book.save(project)
        return jsonify({"ok": True, "book": book.to_dict(), "page": page_id})

    @route("/b/<name>/areas/<area_id>/duplicate", methods=["POST"])
    def duplicate_area(name, area_id):
        project, book = get_book_project(name)
        for page in book.pages:
            for area in page.areas:
                if area.id == area_id:
                    copy = book.duplicate_area(page, area)
                    book.save(project)
                    return jsonify({"ok": True, "book": book.to_dict(), "area": copy.id})
        raise ProjectError(t("This area no longer exists."))

    return app

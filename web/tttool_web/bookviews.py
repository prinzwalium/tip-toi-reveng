"""Routes for the book editor.

Registered from :func:`tttool_web.app.create_app` so that they share its
authentication and error handling.
"""

import tempfile
from dataclasses import asdict
from pathlib import Path

from flask import flash, jsonify, redirect, render_template, request, send_file, url_for

from .audio import VOICES, speak, speech_engine, store_sound
from .book import GROUP_KINDS, PAPER_SIZES, Book, store_upload
from .bookbuild import build, converters_available
from .pictures import forget as forget_derived, make_preview
from .starters import STARTERS, apply_starter
from .i18n import plural, t
from .projects import (
    Project,
    ProjectError,
    list_projects,
    sanitize_filename,
    unique_name,
)
from .transfer import (
    backup_name,
    export_all,
    export_book,
    export_name,
    import_backup,
    import_book,
    looks_like_backup,
)

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
    "No sounds yet — record one, let the computer speak, or upload a file.",
    "Use",
    "used {count}×",
    "unused",
    "Delete this sound?",
    "This sound is used {count}× — delete it anyway?",
    "Play",
    "Delete",
    "This browser cannot record, or the page is not served over https.",
    "No microphone available, or permission was refused.",
    "This installation cannot speak text (no speech synthesizer installed).",
    "One sound per tap, in this order; then it starts again.",
    "The pen picks one of these each time.",
    "+ New game",
    "Sound for a right answer",
    "Sound for a wrong answer",
    "Reward when everything is found",
    "none",
    "Choose",
    "Area {name}, {x} by {y} millimetres, {sound}",
    "plays {sound}",
    "no sound yet",
]


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
        project = Project(unique_name(title)).create()
        book = Book(title=title, paper=paper or Book().paper)
        book.product_id = _free_product_id(taken)
        book.add_page("Seite 1")
        (project.path / "sounds").mkdir(exist_ok=True)
        (project.path / "seiten").mkdir(exist_ok=True)
        starter = request.form.get("starter")
        apply_starter(project, book, starter if starter in STARTERS else "empty")
        book.save(project)
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

    # -- taking a book elsewhere ------------------------------------------

    @route("/b/<name>/export")
    def export_book_file(name):
        """The whole book — model, pictures, sounds, codes — as one file."""
        project, book = get_book_project(name)
        # Spooled: a book with a few sounds stays in memory, a big one does not.
        buffer = tempfile.SpooledTemporaryFile(max_size=32 * 1024 * 1024)
        export_book(project, book, buffer)
        buffer.seek(0)
        return send_file(
            buffer,
            mimetype="application/zip",
            as_attachment=True,
            download_name=export_name(project),
        )

    @route("/books/import", methods=["POST"])
    def import_book_file():
        """One book or a whole backup — the file says which."""
        upload = request.files.get("book")
        if not upload or not upload.filename:
            raise ProjectError(t("Please choose an exported book."))
        if looks_like_backup(upload):
            restored = import_backup(upload)
            flash(
                plural(
                    "Added one book from the backup.",
                    "Added {count} books from the backup.",
                    len(restored),
                ),
                "success",
            )
            return redirect(url_for("index"))
        project = import_book(upload, (request.form.get("title") or "").strip()[:80])
        flash(t("Imported “{title}”.", title=Book.load(project).title), "success")
        return redirect(url_for("edit_book", name=project.name))

    @route("/books/backup")
    def backup_everything():
        """Every book on this server, in one file."""
        books = []
        for entry in list_projects():
            try:
                project = Project(entry["name"]).require()
            except ProjectError:
                continue
            if Book.is_book(project):
                books.append((project, Book.load(project)))
        if not books:
            raise ProjectError(t("There are no books to back up yet."))
        buffer = tempfile.SpooledTemporaryFile(max_size=64 * 1024 * 1024)
        export_all(books, buffer)
        buffer.seek(0)
        return send_file(
            buffer,
            mimetype="application/zip",
            as_attachment=True,
            download_name=backup_name(),
        )

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
        # The library, the games and the pictures on disk belong to the
        # server: a browser tab with a stale copy must not be able to delete a
        # sound just by saving where an area sits.
        updated = Book.from_dict(request.get_json(silent=True) or {}, keep=book)
        by_page = {p.id: p for p in book.pages}
        for page in updated.pages:
            known = by_page.get(page.id)
            if known is None:
                continue
            page.image = known.image
            page.preview = known.preview
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
        forget_derived(project, page.image)
        page.image, _ = store_upload(project, "seiten", page.id, upload)
        # The editor gets a small copy; the original is kept for printing.
        page.preview = make_preview(project, page.image)
        book.save(project)
        return jsonify({"ok": True, "image": page.image, "preview": page.preview,
                        "url": url_for("raw", name=project.name,
                                       path=page.preview or page.image)})

    # -- the sound library ------------------------------------------------

    def library(project, book) -> dict:
        usage = book.sound_usage()
        return {
            "sounds": [
                {
                    **asdict(sound),
                    "url": url_for("raw", name=project.name, path=sound.file),
                    "used": usage.get(sound.id, 0),
                }
                for sound in book.sounds
            ],
            "voices": [{"code": code, "label": label} for code, label in VOICES],
            "can_speak": bool(speech_engine()),
        }

    @route("/b/<name>/sounds")
    def list_sounds(name):
        project, book = get_book_project(name)
        return jsonify(library(project, book))

    @route("/b/<name>/sounds/add", methods=["POST"])
    def add_sound(name):
        """One entry point for an uploaded file and for a browser recording."""
        project, book = get_book_project(name)
        upload = request.files.get("sound")
        if not upload or not upload.filename:
            raise ProjectError(t("Please choose a sound file."))
        source = "record" if request.form.get("source") == "record" else "upload"
        given = (request.form.get("name") or "").strip()[:120]
        sound = book.add_sound(
            name=given or Path(sanitize_filename(upload.filename)).stem,
            source=source,
        )
        sound.file = f"sounds/{sound.id}.ogg"
        store_sound(project, upload, sound.file)
        book.save(project)
        return jsonify({"ok": True, "sound": sound.id, **library(project, book)})

    @route("/b/<name>/sounds/speak", methods=["POST"])
    def speak_sound(name):
        project, book = get_book_project(name)
        text = (request.form.get("text") or "").strip()
        language = (request.form.get("language") or "de").strip()
        sound_id = (request.form.get("sound_id") or "").strip()

        # Speaking again replaces the file of an existing sound, so every area
        # that uses it follows along.
        sound = book.sound(sound_id) if sound_id else book.add_sound(source="speak")
        sound.source = "speak"
        sound.text = text[:500]
        sound.language = language
        sound.name = sound.name or text[:40]
        sound.file = f"sounds/{sound.id}.ogg"
        engine = speak(text, language, project.path / sound.file)
        book.save(project)
        return jsonify(
            {"ok": True, "sound": sound.id, "engine": engine, **library(project, book)}
        )

    @route("/b/<name>/sounds/<sound_id>/rename", methods=["POST"])
    def rename_sound(name, sound_id):
        project, book = get_book_project(name)
        sound = book.sound(sound_id)
        sound.name = (request.form.get("name") or "").strip()[:120] or sound.name
        book.save(project)
        return jsonify({"ok": True, **library(project, book)})

    @route("/b/<name>/sounds/<sound_id>/delete", methods=["POST"])
    def delete_sound(name, sound_id):
        project, book = get_book_project(name)
        sound = book.sound(sound_id)
        (project.path / sound.file).unlink(missing_ok=True)
        book.sounds = [s for s in book.sounds if s.id != sound_id]
        for page in book.pages:
            for area in page.areas:
                if area.sound_id == sound_id:
                    area.sound_id = ""
        book.save(project)
        return jsonify({"ok": True, "book": book.to_dict(), **library(project, book)})

    @route("/b/<name>/areas/<area_id>/sound", methods=["POST"])
    def assign_area_sound(name, area_id):
        """Point an area at a sound of the library, or silence it."""
        project, book = get_book_project(name)
        _, area = book.area(area_id)
        sound_id = (request.form.get("sound_id") or "").strip()
        if sound_id:
            book.sound(sound_id)  # raises if it is gone
        area.sound_id = sound_id
        book.save(project)
        return jsonify({"ok": True, "book": book.to_dict(), **library(project, book)})

    # -- games ------------------------------------------------------------

    @route("/b/<name>/groups", methods=["POST"])
    def add_group(name):
        """A quiz or a collecting game that areas can be put into."""
        project, book = get_book_project(name)
        kind = request.form.get("kind") if request.form.get("kind") in GROUP_KINDS else "quiz"
        given = (request.form.get("name") or "").strip()[:80]
        default = t("Quiz {number}") if kind == "quiz" else t("Collection {number}")
        group = book.add_group(
            kind=kind,
            name=given or default.format(number=len(book.groups) + 1),
        )
        book.save(project)
        return jsonify({"ok": True, "group": group.id, "book": book.to_dict()})

    @route("/b/<name>/groups/<group_id>", methods=["POST"])
    def update_group(name, group_id):
        project, book = get_book_project(name)
        group = book.group_of(group_id)
        if "name" in request.form:
            group.name = (request.form.get("name") or "").strip()[:80] or group.name
        for field_name in ("right_sound_id", "wrong_sound_id", "reward_sound_id"):
            if field_name in request.form:
                value = (request.form.get(field_name) or "").strip()
                if value:
                    book.sound(value)  # raises if it is gone
                setattr(group, field_name, value)
        book.save(project)
        return jsonify({"ok": True, "book": book.to_dict()})

    @route("/b/<name>/groups/<group_id>/delete", methods=["POST"])
    def delete_group(name, group_id):
        project, book = get_book_project(name)
        book.group_of(group_id)
        book.groups = [g for g in book.groups if g.id != group_id]
        for page in book.pages:
            for area in page.areas:
                if area.group == group_id:
                    area.group = ""
                    if area.behaviour in ("answer", "collect"):
                        area.behaviour = "play"
        book.save(project)
        return jsonify({"ok": True, "book": book.to_dict()})

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
        page = book.page(page_id)
        book.remove_page(page_id)
        # The picture of a deleted page is of no use to anyone, and would sit
        # in the project (and in every export) for the rest of its life — but a
        # duplicated page shares the file with its original, so only the last
        # page using it may throw it away.
        still_used = any(other.image == page.image for other in book.pages)
        if page.image and not still_used:
            forget_derived(project, page.image)
            (project.path / page.image).unlink(missing_ok=True)
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

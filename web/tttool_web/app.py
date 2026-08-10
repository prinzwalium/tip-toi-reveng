"""Flask application: a small web GUI around the tttool command line tool."""

import mimetypes
import os
import secrets
import shutil
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse

from flask import (
    Flask,
    Response,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from . import __version__
from .book import PAPER_SIZES, Book
from .bookviews import register_book_routes
from .commands import COMMANDS, GROUPS, OID_GLOBAL_PARAMS, get_command
from .config import config
from .i18n import LANG_COOKIE, LANGUAGES, current_lang, known as known_lang, t
from .projects import Project, ProjectError, list_projects
from .runner import build_invocation, convert_audio, diff_snapshots, run, tttool_version

TEMPLATE_YAML = """\
# tttool project – see https://tttool.readthedocs.io/de/latest/ for the handbook.
product-id: 42

# Where the audio files live. "%s" is replaced by the name used in P(...).
media-path: "audio/%s"

comment: Created with the tttool web GUI

# Sounds played when the pen touches the book's power-on code
welcome: hello

scripts:
  8065: P(hello)
"""


#: Strings app.js needs in the browser; the English source is the key.
UI_STRINGS = [
    "created",
    "changed",
    "deleted",
    "Files this run wrote that were not there before. Click one to download it.",
    "Files that already existed and this run overwrote. Click one to download it.",
    "Files that were removed while this command ran.",
    "… and {count} more",
    "in",
    "ok",
    "error",
    "timeout",
    "exit",
    "running …",
    "(no output — that means success)",
    "(no output)",
    "Request failed:",
]


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_UPLOAD_MB * 1024 * 1024
    app.secret_key = os.environ.get("TTTOOL_WEB_SECRET_KEY") or secrets.token_hex(32)
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)

    # -- authentication ---------------------------------------------------

    def requires_auth(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not config.auth_enabled:
                return view(*args, **kwargs)
            auth = request.authorization
            ok = (
                auth
                and secrets.compare_digest(auth.username or "", config.AUTH_USER)
                and secrets.compare_digest(auth.password or "", config.AUTH_PASSWORD)
            )
            if not ok:
                return Response(
                    "Authentication required",
                    401,
                    {"WWW-Authenticate": 'Basic realm="tttool"'},
                )
            return view(*args, **kwargs)

        return wrapper

    def route(rule, **options):
        def decorator(view):
            return app.route(rule, **options)(requires_auth(view))

        return decorator

    # -- helpers ----------------------------------------------------------

    def get_project(name: str) -> Project:
        try:
            return Project(name).require()
        except ProjectError as exc:
            abort(404, str(exc))

    #: Endpoints that always answer with JSON, errors included.
    JSON_ENDPOINTS = {
        "run_command",
        "convert",
        "healthz",
        "book_data",
        "upload_page_image",
        "list_sounds",
        "add_sound",
        "speak_sound",
        "rename_sound",
        "delete_sound",
        "assign_area_sound",
        "add_group",
        "update_group",
        "delete_group",
        "build_book",
        "add_page",
        "duplicate_page",
        "delete_page",
        "move_page",
        "duplicate_area",
    }

    def wants_json() -> bool:
        return (
            request.endpoint in JSON_ENDPOINTS
            or request.headers.get("Accept", "").startswith("application/json")
            or request.headers.get("X-Requested-With") == "fetch"
        )

    @app.before_request
    def block_cross_site_writes():
        """Small CSRF guard: browsers send Origin on every cross-site write."""
        if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
            return None
        origin = request.headers.get("Origin")
        if not origin:  # curl and friends, no ambient credentials involved
            return None
        # Compare hosts only — a TLS terminating proxy makes the schemes differ.
        if urlparse(origin).netloc != urlparse(request.host_url).netloc:
            abort(403, "Cross-site request blocked")
        return None

    def back() -> str:
        """Where to return to after a failed form post — never off-site."""
        referrer = request.referrer or ""
        return referrer if referrer.startswith(request.host_url) else url_for("index")

    @app.errorhandler(ProjectError)
    def handle_project_error(exc: ProjectError):
        if wants_json():
            return jsonify({"error": str(exc)}), 400
        flash(str(exc), "error")
        return redirect(back())

    @app.errorhandler(413)
    def handle_too_large(_exc):
        flash(f"Upload too large (limit: {config.MAX_UPLOAD_MB} MB)", "error")
        return redirect(back()), 413

    #: Files that do not match a parameter's extension are still offered, but
    #: only so many of them — a project with a dumped media directory would
    #: otherwise blow up every select on the page.
    OTHER_FILES_LIMIT = 100

    @app.template_filter("by_ext")
    def by_ext(choices, exts):
        """Split the file list into those matching the parameter's extensions and the rest."""
        exts = tuple(e.lower() for e in exts or ())
        if not exts:
            return {"matching": list(choices), "other": []}
        matching = [c for c in choices if c.lower().endswith(exts)]
        other = [c for c in choices if not c.lower().endswith(exts)]
        return {"matching": matching, "other": other[:OTHER_FILES_LIMIT]}

    app.jinja_env.globals["t"] = t

    @app.context_processor
    def template_globals():
        return {
            "app_version": __version__,
            "app_build": config.build,
            "tttool_version": app.config.setdefault("TTTOOL_VERSION", tttool_version()),
            "allow_delete": config.ALLOW_DELETE,
            "lang": current_lang(),
            "languages": LANGUAGES,
            "ui_strings": {key: t(key) for key in UI_STRINGS},
        }

    @route("/language", methods=["POST"])
    def set_language():
        """Remember the visitor's language; the default stays the configured one."""
        lang = (request.form.get("lang") or "").strip().lower()
        if not known_lang(lang):
            raise ProjectError("Unknown language")
        response = redirect(back())
        # A year: long enough that nobody has to pick twice, short enough that
        # a shared browser forgets eventually.
        response.set_cookie(
            LANG_COOKIE, lang, max_age=365 * 24 * 3600, samesite="Lax", httponly=False
        )
        return response

    # -- projects ---------------------------------------------------------

    def copy_examples(project: Project) -> None:
        shutil.copytree(config.EXAMPLES_DIR, project.path, dirs_exist_ok=True)

    @route("/")
    def index():
        projects = list_projects()
        for entry in projects:
            try:
                entry["is_book"] = Book.is_book(Project(entry["name"]))
            except ProjectError:
                entry["is_book"] = False
        return render_template(
            "index.html",
            projects=projects,
            books=[p for p in projects if p["is_book"]],
            others=[p for p in projects if not p["is_book"]],
            examples=config.examples_available,
            papers=PAPER_SIZES,
        )

    @route("/projects", methods=["POST"])
    def create_project():
        project = Project(request.form.get("name", "").strip()).create()
        start = request.form.get("start", "template")
        if start == "example" and config.examples_available:
            copy_examples(project)
        elif start != "empty":
            project.write_text("book.yaml", TEMPLATE_YAML)
            (project.path / "audio").mkdir(exist_ok=True)
        flash(f"Created project {project.name}", "success")
        return redirect(url_for("project_view", name=project.name))

    @route("/p/<name>/delete", methods=["POST"])
    def delete_project(name):
        if not config.ALLOW_DELETE:
            abort(403)
        get_project(name).delete()
        flash(f"Deleted project {name}", "success")
        return redirect(url_for("index"))

    @route("/p/<name>")
    def project_view(name):
        project = get_project(name)
        files = project.files()
        return render_template(
            "project.html",
            project=project,
            files=files,
            file_choices=[f.relpath for f in files if not f.is_dir],
            commands=COMMANDS,
            groups=GROUPS,
            oid_params=OID_GLOBAL_PARAMS,
            selected=request.args.get("cmd", "assemble"),
        )

    @route("/p/<name>/files")
    def files_fragment(name):
        project = get_project(name)
        return render_template("_files.html", project=project, files=project.files())

    @route("/p/<name>/archive")
    def archive(name):
        project = get_project(name)
        return send_file(
            project.archive(),
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"{project.name}.zip",
        )

    # -- files ------------------------------------------------------------

    @route("/p/<name>/upload", methods=["POST"])
    def upload(name):
        project = get_project(name)
        uploads = [f for f in request.files.getlist("files") if f and f.filename]
        if not uploads:
            raise ProjectError("No files selected")
        subdir = request.form.get("subdir", "").strip()
        saved = [project.save_upload(f.filename, f, subdir) for f in uploads]
        flash(f"Uploaded {len(saved)} file(s)", "success")
        return redirect(url_for("project_view", name=project.name))

    @route("/p/<name>/download")
    def download(name):
        project = get_project(name)
        path = project.resolve(request.args.get("path", ""))
        if path.is_dir():
            raise ProjectError("Cannot download a directory; use 'Download all'")
        return send_file(path, as_attachment=True, download_name=path.name)

    @route("/p/<name>/raw")
    def raw(name):
        """Serve a file inline, for the image and audio previews."""
        project = get_project(name)
        path = project.resolve(request.args.get("path", ""))
        if path.is_dir():
            abort(404)
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if not (mime.startswith(("image/", "audio/")) or mime == "application/pdf"):
            mime = "application/octet-stream"
        response = send_file(path, mimetype=mime, conditional=True)
        response.headers["Content-Security-Policy"] = "sandbox; default-src 'none'"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @route("/p/<name>/files/delete", methods=["POST"])
    def delete_file(name):
        if not config.ALLOW_DELETE:
            abort(403)
        project = get_project(name)
        relpath = request.form.get("path", "")
        project.delete_file(relpath)
        flash(f"Deleted {relpath}", "success")
        return redirect(url_for("project_view", name=project.name))

    @route("/p/<name>/edit", methods=["GET", "POST"])
    def edit(name):
        project = get_project(name)
        relpath = request.values.get("path", "")
        if request.method == "POST":
            content = request.form.get("content", "").replace("\r\n", "\n")
            project.write_text(relpath, content)
            flash(f"Saved {relpath}", "success")
            if request.form.get("stay"):
                return redirect(url_for("edit", name=project.name, path=relpath))
            return redirect(url_for("project_view", name=project.name))
        return render_template(
            "edit.html", project=project, relpath=relpath, content=project.read_text(relpath)
        )

    @route("/p/<name>/new", methods=["POST"])
    def new_file(name):
        project = get_project(name)
        relpath = request.form.get("path", "").strip()
        if not relpath:
            raise ProjectError("Give a file name")
        if not Path(relpath).suffix:
            relpath += ".yaml"
        target = project.resolve(relpath, must_exist=False)
        if target.exists():
            raise ProjectError(f"{relpath} already exists")
        project.write_text(relpath, TEMPLATE_YAML if target.suffix in (".yaml", ".yml") else "")
        return redirect(url_for("edit", name=project.name, path=project.relpath_of(target)))

    @route("/p/<name>/convert", methods=["POST"])
    def convert(name):
        project = get_project(name)
        result = convert_audio(
            project,
            request.form.get("path", ""),
            request.form.get("out", "").strip(),
        )
        result["files"] = {"created": [result["output"]] if result["output"] else [], "changed": [], "deleted": []}
        result["command"] = " ".join(result.pop("argv"))
        return jsonify(result)

    # -- running tttool ---------------------------------------------------

    @route("/p/<name>/run", methods=["POST"])
    def run_command(name):
        project = get_project(name)
        command = get_command(request.form.get("command", ""))
        argv, cwd = build_invocation(command, request.form, project)
        before = project.snapshot()
        result = run(argv, cwd)
        result["files"] = diff_snapshots(before, project.snapshot())
        result["command"] = " ".join(
            [Path(argv[0]).name] + [_quote(a) for a in argv[1:]]
        )
        result["cwd"] = project.relpath_of(cwd) if cwd != project.path else "."
        return jsonify(result)

    # -- misc -------------------------------------------------------------

    @route("/help")
    def help_page():
        return render_template("help.html", commands=COMMANDS, groups=GROUPS)

    @route("/hilfe/erste-schritte")
    def start_page():
        """The illustrated walk through making a first book."""
        return render_template("start.html")

    @route("/hilfe/stift")
    def pen_page():
        """How the printed page and the file get to the pen."""
        return render_template("pen.html")

    @app.route("/healthz")
    def healthz():
        return jsonify(
            {
                "status": "ok",
                "tttool": tttool_version(),
                "version": __version__,
                "build": {"ref": config.BUILD_REF, "commit": config.BUILD_SHA},
            }
        )

    register_book_routes(app, route, get_project)

    return app


def _quote(arg: str) -> str:
    return f"'{arg}'" if (" " in arg or not arg) else arg


app = create_app()

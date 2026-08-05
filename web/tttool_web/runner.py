"""Validating the submitted form values and running tttool."""

import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from .commands import OID_GLOBAL_PARAMS, Command, Param
from .config import config
from .projects import Project, ProjectError

CODE_DIM_RE = re.compile(r"^\d{1,3}(x\d{1,3})?$")
OFFSET_RE = re.compile(r"^(0[xX])?[0-9a-fA-F]{1,10}$")
RANGE_RE = re.compile(r"^[0-9]+(-[0-9]+)?(,[0-9]+(-[0-9]+)?)*$")
LANG_RE = re.compile(r"^[A-Za-z][A-Za-z-]{0,19}$")
TEXT_VALIDATORS = {
    "pos": (OFFSET_RE, "Offsets look like 4660 or 0x1234."),
    "range": (RANGE_RE, "Ranges look like 1,3,1000-1085."),
    "lang": (LANG_RE, "Languages are plain words such as GERMAN."),
    "code_dim": (CODE_DIM_RE, "Sizes look like 30 or 30x20 (millimeters)."),
}


class RunError(ProjectError):
    pass


def _validate(param: Param, raw: str, project: Project) -> object:
    raw = (raw or "").strip()

    if param.type == "bool":
        return raw not in ("", "0", "false", "off", "no")

    if not raw:
        if param.required:
            raise RunError(f"{param.label} is required")
        return "" if param.type != "int" else ""

    if param.type == "file":
        path = project.resolve(raw)
        if path.is_dir():
            raise RunError(f"{param.label}: {raw} is a directory")
        return path

    if param.type == "outpath":
        return project.resolve(raw, must_exist=False)

    if param.type == "int":
        if not raw.isdigit():
            raise RunError(f"{param.label} must be a number")
        value = int(raw)
        if not (param.minimum <= value <= param.maximum):
            raise RunError(f"{param.label} must be between {param.minimum} and {param.maximum}")
        return value

    if param.type == "choice":
        allowed = {value for value, _ in param.choices}
        if raw not in allowed:
            raise RunError(f"{param.label}: unknown value {raw!r}")
        return raw

    if param.type == "text":
        pattern = TEXT_VALIDATORS.get(param.name)
        if pattern and not pattern[0].match(raw):
            raise RunError(f"{param.label}: {pattern[1]}")
        if len(raw) > 200:
            raise RunError(f"{param.label} is too long")
        return raw

    raise RunError(f"Unsupported parameter type {param.type}")


def _global_args(values: dict, command: Command, cwd: Path) -> list[str]:
    args: list[str] = []
    transscript = values.get("transscript")
    if isinstance(transscript, Path):
        args += ["-t", os.path.relpath(transscript, cwd)]
    if command.oid_options:
        if values.get("dpi"):
            args += ["--dpi", str(values["dpi"])]
        if values.get("pixel_size"):
            args += ["--pixel-size", str(values["pixel_size"])]
        if values.get("code_dim"):
            args += ["--code-dim", str(values["code_dim"])]
        if values.get("image_format"):
            args += ["--image-format", str(values["image_format"])]
    return args


def build_invocation(command: Command, form: dict, project: Project) -> tuple[list[str], Path]:
    """Validate ``form`` and return the argv plus the working directory."""
    values: dict = {}
    params = list(command.params)
    if command.oid_options:
        params += list(OID_GLOBAL_PARAMS)
    for param in params:
        values[param.name] = _validate(param, form.get(param.name, param.default), project)

    if command.id == "set-language" and not values["empty"] and not values["lang"]:
        raise RunError("Give a language, or tick '--empty' to clear the field.")

    cwd = project.path
    if command.workdir_param:
        cwd = values[command.workdir_param]
        if cwd.exists() and not cwd.is_dir():
            raise RunError(f"{project.relpath_of(cwd)} is not a directory")
        cwd.mkdir(parents=True, exist_ok=True)

    # tttool gets paths relative to its working directory.
    argv_values = dict(values)
    for param in params:
        value = values[param.name]
        if isinstance(value, Path):
            if param.type == "outpath":
                value.parent.mkdir(parents=True, exist_ok=True)
            relative = os.path.relpath(value, cwd)
            # A file called "-x.gme" would otherwise look like an option.
            argv_values[param.name] = f"./{relative}" if relative.startswith("-") else relative

    if command.workdir_param:
        # The working directory itself is not passed on the command line.
        argv_values[command.workdir_param] = ""

    argv = [config.TTTOOL_BIN] + _global_args(values, command, cwd) + list(command.build(argv_values))
    return argv, cwd


def run(argv: list[str], cwd: Path, timeout: int | None = None) -> dict:
    started = time.monotonic()
    env = dict(os.environ)
    env.setdefault("HOME", str(cwd))
    env["LC_ALL"] = env.get("LC_ALL", "C.UTF-8")
    env["LANG"] = env.get("LANG", "C.UTF-8")
    try:
        proc = subprocess.run(
            argv,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=timeout or config.RUN_TIMEOUT,
        )
    except FileNotFoundError:
        raise RunError(
            f"Could not execute {argv[0]!r}. Set TTTOOL_BIN to the path of the tttool binary."
        ) from None
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "exit_code": None,
            "stdout": _decode(exc.stdout),
            "stderr": _decode(exc.stderr) + f"\nAborted after {exc.timeout:.0f} seconds.",
            "duration": time.monotonic() - started,
        }
    return {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout": _decode(proc.stdout),
        "stderr": _decode(proc.stderr),
        "duration": time.monotonic() - started,
    }


def _decode(data: bytes | None) -> str:
    if not data:
        return ""
    limit = config.MAX_OUTPUT_BYTES
    truncated = len(data) > limit
    text = data[:limit].decode("utf-8", errors="replace")
    if truncated:
        text += f"\n… output truncated at {limit} bytes …"
    return text


def diff_snapshots(before: dict, after: dict) -> dict[str, list[str]]:
    created = sorted(set(after) - set(before))
    changed = sorted(p for p in set(after) & set(before) if after[p] != before[p])
    deleted = sorted(set(before) - set(after))
    return {"created": created, "changed": changed, "deleted": deleted}


def tttool_version() -> str:
    binary = shutil.which(config.TTTOOL_BIN) or config.TTTOOL_BIN
    try:
        proc = subprocess.run(
            [binary, "--help"], capture_output=True, timeout=20, stdin=subprocess.DEVNULL
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown (tttool not found)"
    text = (proc.stdout or b"").decode("utf-8", errors="replace")
    match = re.search(r"tttool-([0-9][^\s]*)", text)
    return match.group(1) if match else "unknown"


def convert_audio(project: Project, relpath: str, out_relpath: str) -> dict:
    """Convert any audio file into the mono/22050 Hz Ogg Vorbis the pen wants."""
    source = project.resolve(relpath)
    target = project.resolve(out_relpath or (Path(relpath).with_suffix(".ogg").as_posix()), must_exist=False)
    if target.suffix.lower() != ".ogg":
        target = target.with_suffix(".ogg")
    if target == source:
        raise RunError("Pick a different output name than the input file")
    target.parent.mkdir(parents=True, exist_ok=True)
    argv = [
        config.FFMPEG_BIN, "-hide_banner", "-nostdin", "-y",
        "-i", os.path.relpath(source, project.path),
        "-ar", "22050", "-ac", "1", "-c:a", "libvorbis",
        os.path.relpath(target, project.path),
    ]
    try:
        result = run(argv, project.path)
    except RunError:
        raise RunError("ffmpeg is not available in this container") from None
    result["argv"] = argv
    result["output"] = project.relpath_of(target) if target.exists() else ""
    return result

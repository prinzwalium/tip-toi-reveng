"""The catalogue of tttool commands exposed by the web GUI.

Every command declares its parameters; the argv is assembled from validated
values only, and is handed to :mod:`subprocess` as a list — no shell is ever
involved.
"""

from dataclasses import dataclass, field
from typing import Callable

from .projects import ProjectError

YAML_EXTS = (".yaml", ".yml")
GME_EXTS = (".gme",)


@dataclass(frozen=True)
class Param:
    name: str
    label: str
    type: str  # file | outpath | text | int | bool | choice
    required: bool = False
    default: str = ""
    help: str = ""
    exts: tuple[str, ...] = ()
    choices: tuple[tuple[str, str], ...] = ()
    placeholder: str = ""
    minimum: int = 0
    maximum: int = 100000


def file_param(name="input", label="Input file", exts=(), help="", required=True):
    return Param(name=name, label=label, type="file", exts=tuple(exts), help=help, required=required)


@dataclass(frozen=True)
class Command:
    id: str
    label: str
    group: str
    description: str
    build: Callable[[dict], list[str]]
    params: tuple[Param, ...] = ()
    #: Name of the parameter that names the working directory for the run.
    workdir_param: str = ""
    #: Show the OID related global options (dpi, code size, image format).
    oid_options: bool = False
    #: Command rewrites its input file in place.
    in_place: bool = False
    #: Extra note rendered above the form.
    note: str = ""
    #: Suggest a default name for the output parameter, derived from the input.
    derive_out: tuple[str, str, str] = ()  # (input param, output param, suffix)


def _flag(values: dict, name: str, flag: str) -> list[str]:
    return [flag] if values.get(name) else []


def _opt(values: dict, name: str, flag: str) -> list[str]:
    value = values.get(name)
    return [flag, str(value)] if value not in (None, "") else []


OUT_HELP = "Optional; defaults to the input name with the new extension."

COMMANDS: tuple[Command, ...] = (
    # -- creation ---------------------------------------------------------
    Command(
        id="assemble",
        label="assemble",
        group="Build",
        description="Compile a YAML source file into a GME file for the pen.",
        params=(
            file_param("yaml", "YAML source", YAML_EXTS),
            Param("out", "Output GME file", "outpath", help=OUT_HELP, placeholder="my-book.gme"),
            Param("no_date", "--no-date (reproducible output)", "bool"),
        ),
        build=lambda v: ["assemble", *_flag(v, "no_date", "--no-date"), v["yaml"], *([v["out"]] if v["out"] else [])],
        derive_out=("yaml", "out", ".gme"),
    ),
    # -- analysis ---------------------------------------------------------
    Command(
        id="info",
        label="info",
        group="Inspect",
        description="Print general information about a GME file.",
        params=(file_param("gme", "GME file", GME_EXTS),),
        build=lambda v: ["info", v["gme"]],
    ),
    Command(
        id="export",
        label="export",
        group="Inspect",
        description="Dump a GME file in the human readable YAML format.",
        params=(
            file_param("gme", "GME file", GME_EXTS),
            Param("out", "Output YAML file", "outpath", help=OUT_HELP, placeholder="book.yaml"),
        ),
        build=lambda v: ["export", v["gme"], *([v["out"]] if v["out"] else [])],
        derive_out=("gme", "out", ".yaml"),
    ),
    Command(
        id="scripts",
        label="scripts",
        group="Inspect",
        description="Print the decoded scripts for every OID in the file.",
        params=(
            file_param("gme", "GME file", GME_EXTS),
            Param("raw", "--raw (undecoded form)", "bool"),
            Param(
                "transscript",
                "Transcript file",
                "file",
                exts=(".csv", ".txt", ".semantic"),
                required=False,
                help="';'-separated mapping from media indices to plain text.",
            ),
        ),
        build=lambda v: ["scripts", *_flag(v, "raw", "--raw"), v["gme"]],
    ),
    Command(
        id="script",
        label="script",
        group="Inspect",
        description="Print the decoded script of one specific OID.",
        params=(
            file_param("gme", "GME file", GME_EXTS),
            Param("oid", "OID", "int", required=True, default="", placeholder="8065", maximum=65535),
            Param("raw", "--raw (undecoded form)", "bool"),
        ),
        build=lambda v: ["script", *_flag(v, "raw", "--raw"), v["gme"], str(v["oid"])],
    ),
    Command(
        id="games",
        label="games",
        group="Inspect",
        description="Print the decoded games of a GME file.",
        params=(file_param("gme", "GME file", GME_EXTS),),
        build=lambda v: ["games", v["gme"]],
    ),
    Command(
        id="lint",
        label="lint",
        group="Inspect",
        description="Check a GME file for errors (and tttool for misunderstandings).",
        params=(file_param("gme", "GME file", GME_EXTS),),
        build=lambda v: ["lint", v["gme"]],
    ),
    Command(
        id="segments",
        label="segments",
        group="Inspect",
        description="List all known parts of the file, with a description.",
        params=(file_param("gme", "GME file", GME_EXTS),),
        build=lambda v: ["segments", v["gme"]],
    ),
    Command(
        id="segment",
        label="segment",
        group="Inspect",
        description="Print the segment that contains a specific offset.",
        params=(
            file_param("gme", "GME file", GME_EXTS),
            Param("pos", "Offset", "text", required=True, placeholder="0x1234 or 4660",
                  help="Decimal or hexadecimal byte offset into the file."),
        ),
        build=lambda v: ["segment", v["gme"], v["pos"]],
    ),
    Command(
        id="holes",
        label="holes",
        group="Inspect",
        description="List all parts of the file that are not understood yet.",
        params=(file_param("gme", "GME file", GME_EXTS),),
        build=lambda v: ["holes", v["gme"]],
    ),
    Command(
        id="explain",
        label="explain",
        group="Inspect",
        description="Hexdump of the GME file, annotated with descriptions.",
        params=(
            file_param("gme", "GME file", GME_EXTS),
            Param("dont_skip", "--dont-skip (do not omit long segments)", "bool"),
        ),
        build=lambda v: ["explain", *_flag(v, "dont_skip", "--dont-skip"), v["gme"]],
        note="This produces a lot of output; without --dont-skip long segments are shortened.",
    ),
    Command(
        id="rewrite",
        label="rewrite",
        group="Inspect",
        description="Parse the file and write it again (for debugging tttool).",
        params=(
            file_param("gme", "GME file", GME_EXTS),
            Param("out", "Output GME file", "outpath", required=True, placeholder="rewritten.gme"),
        ),
        build=lambda v: ["rewrite", v["gme"], v["out"]],
    ),
    # -- extraction -------------------------------------------------------
    Command(
        id="media",
        label="media",
        group="Extract",
        description="Dump all audio samples of a GME file into a directory.",
        params=(
            file_param("gme", "GME file", GME_EXTS),
            Param("dir", "Output directory", "outpath", default="media", required=True),
        ),
        build=lambda v: ["media", "-d", v["dir"], v["gme"]],
    ),
    Command(
        id="binaries",
        label="binaries",
        group="Extract",
        description="Dump all binaries contained in a GME file.",
        params=(
            file_param("gme", "GME file", GME_EXTS),
            Param("dir", "Output directory", "outpath", default="binaries", required=True),
        ),
        build=lambda v: ["binaries", "-d", v["dir"], v["gme"]],
    ),
    # -- OID codes --------------------------------------------------------
    Command(
        id="oid-table",
        label="oid-table",
        group="OID codes",
        description="Create a PDF or SVG sheet with all codes used in a YAML file.",
        params=(
            file_param("yaml", "YAML source", YAML_EXTS),
            Param("out", "Output file", "outpath", help=OUT_HELP, placeholder="book-codes.pdf"),
        ),
        build=lambda v: ["oid-table", v["yaml"], *([v["out"]] if v["out"] else [])],
        oid_options=True,
        derive_out=("yaml", "out", ".pdf"),
    ),
    Command(
        id="oid-codes",
        label="oid-codes",
        group="OID codes",
        description="Create one image file per OID used in a YAML file.",
        params=(
            file_param("yaml", "YAML source", YAML_EXTS),
            Param("dir", "Output directory", "outpath", default="oid-codes", required=True,
                  help="The images are written here as oid-<code>.<format>."),
        ),
        build=lambda v: ["oid-codes", v["yaml"]],
        workdir_param="dir",
        oid_options=True,
    ),
    Command(
        id="oid-code",
        label="oid-code",
        group="OID codes",
        description="Create images for an explicit list or range of codes.",
        params=(
            Param("range", "Code range", "text", required=True, placeholder="1,3,1000-1085",
                  help="Single codes, comma separated lists and ranges are allowed."),
            Param("dir", "Output directory", "outpath", default="oid-codes", required=True),
            Param("raw", "--raw (treat as raw codes)", "bool"),
        ),
        build=lambda v: ["oid-code", *_flag(v, "raw", "--raw"), v["range"]],
        workdir_param="dir",
        oid_options=True,
    ),
    # -- modification -----------------------------------------------------
    Command(
        id="set-language",
        label="set-language",
        group="Modify",
        description="Set (or clear) the language field of a GME file.",
        params=(
            file_param("gme", "GME file", GME_EXTS),
            Param(
                "lang",
                "Language",
                "text",
                placeholder="GERMAN",
                help="Leave empty together with the checkbox below to clear the field.",
            ),
            Param("empty", "--empty (remove the language)", "bool"),
        ),
        build=lambda v: ["set-language", "--empty" if v["empty"] else v["lang"], v["gme"]],
        in_place=True,
        note="This modifies the GME file in place. Duplicate it first if you want to keep the original.",
    ),
    Command(
        id="set-product-id",
        label="set-product-id",
        group="Modify",
        description="Change the product id of a GME file.",
        params=(
            file_param("gme", "GME file", GME_EXTS),
            Param("product_id", "Product id", "int", required=True, placeholder="42", maximum=4294967295),
        ),
        build=lambda v: ["set-product-id", str(v["product_id"]), v["gme"]],
        in_place=True,
        note="This modifies the GME file in place. Duplicate it first if you want to keep the original.",
    ),
)

COMMANDS_BY_ID = {c.id: c for c in COMMANDS}

GROUPS = ("Build", "Inspect", "Extract", "OID codes", "Modify")

#: Global options that apply to the OID drawing commands.
OID_GLOBAL_PARAMS: tuple[Param, ...] = (
    Param("dpi", "Resolution (dpi)", "int", default="1200", minimum=72, maximum=4800,
          help="The resolution the codes are printed at. 1200 dpi is what works on paper."),
    Param("pixel_size", "Pixels per dot", "int", default="2", minimum=1, maximum=32,
          help="Must go down together with the dpi, or tttool stops with “Dots too large”."),
    Param("code_dim", "Code size in mm (WxH)", "text", default="30", placeholder="30 or 30x20"),
    Param(
        "image_format",
        "Image format",
        "choice",
        default="",
        choices=(("", "default"), ("png", "PNG"), ("pdf", "PDF"), ("svg", "SVG"), ("svg+png", "SVG+PNG")),
    ),
)


def get_command(command_id: str) -> Command:
    try:
        return COMMANDS_BY_ID[command_id]
    except KeyError:
        raise ProjectError(f"Unknown command: {command_id}") from None

"""The German interface has to stay complete.

Every string the interface can show goes through ``t()``, and the English
source doubles as the key. That makes it possible to simply collect the keys
and check them against the catalogue — so a new button in an English source
file cannot quietly appear untranslated in a German interface.
"""

import ast
import json
import re
import sys
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1]
PACKAGE = WEB / "tttool_web"
sys.path.insert(0, str(WEB))

from tttool_web.app import UI_STRINGS  # noqa: E402
from tttool_web.bookviews import JS_STRINGS  # noqa: E402
from tttool_web.commands import COMMANDS, GROUPS, OID_GLOBAL_PARAMS  # noqa: E402
from tttool_web.i18n import LANGUAGES, SOURCE_LANG, load_catalog  # noqa: E402

#: Words that are the same in every language we ship.
UNTRANSLATED = {"PNG", "PDF", "SVG", "SVG+PNG"}

#: ``t("…")`` in a template, honouring backslash escapes inside the quotes.
TEMPLATE_CALL = re.compile(r"""t\(\s*(['"])((?:\\.|(?!\1).)*)\1""", re.S)


def python_strings(path: Path) -> list[str]:
    """Every literal handed to ``t()`` — via ast, so "a" "b" is one string."""
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
        if name == "t" and node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                found.append(first.value)
    return found


def param_strings(params) -> list[str]:
    found = []
    for param in params:
        found += [getattr(param, attr) for attr in ("label", "help", "tip") if getattr(param, attr)]
        found += [label for _, label in param.choices]
    return found


def all_source_strings() -> set[str]:
    found: list[str] = []
    for path in sorted(PACKAGE.glob("*.py")):
        found += python_strings(path)
    for template in sorted((PACKAGE / "templates").glob("*.html")):
        text = template.read_text(encoding="utf-8")
        found += [
            match.group(2).replace("\\'", "'").replace('\\"', '"')
            for match in TEMPLATE_CALL.finditer(text)
        ]

    # Strings the browser needs are translated on the server and handed over
    # as JSON, so they never appear in a t() call of their own.
    found += list(JS_STRINGS) + list(UI_STRINGS)

    # The command catalogue is data, rendered through t() in the templates.
    for command in COMMANDS:
        found += [command.description] + ([command.note] if command.note else [])
        found += param_strings(command.params)
    found += param_strings(OID_GLOBAL_PARAMS) + list(GROUPS)

    # The file-kind tooltips live in a Jinja dict rather than in t() calls.
    files_template = (PACKAGE / "templates" / "_files.html").read_text(encoding="utf-8")
    tips = re.search(r"set kind_tips = \{(.*?)\n\} %\}", files_template, re.S)
    assert tips, "the kind_tips table moved — this check needs updating"
    found += re.findall(r"'[a-z]+':\s*'(.*?)',", tips.group(1))

    return {s for s in found if s.strip()}


@pytest.mark.parametrize("lang", [code for code, _ in LANGUAGES if code != SOURCE_LANG])
def test_every_interface_string_is_translated(lang):
    catalog = load_catalog(lang)
    missing = sorted(s for s in all_source_strings() if s not in catalog and s not in UNTRANSLATED)
    assert not missing, (
        f"{len(missing)} string(s) have no {lang} translation:\n  "
        + "\n  ".join(missing[:20])
    )


@pytest.mark.parametrize("lang", [code for code, _ in LANGUAGES if code != SOURCE_LANG])
def test_the_catalogue_has_no_leftovers(lang):
    """A translation for a string nobody shows any more is dead weight."""
    catalog = load_catalog(lang)
    sources = all_source_strings()
    stale = sorted(key for key in catalog if key not in sources)
    assert not stale, f"{len(stale)} unused {lang} entries:\n  " + "\n  ".join(stale[:20])


@pytest.mark.parametrize("lang", [code for code, _ in LANGUAGES if code != SOURCE_LANG])
def test_placeholders_survive_translation(lang):
    """A dropped {name} would raise KeyError at the worst possible moment."""
    catalog = load_catalog(lang)
    for source, translated in catalog.items():
        assert set(re.findall(r"\{(\w+)\}", source)) == set(
            re.findall(r"\{(\w+)\}", translated)
        ), f"placeholders differ:\n  {source}\n  {translated}"


def test_the_catalogue_is_valid_json_and_sorted_by_nothing_in_particular():
    """Guards against a merge leaving the file unparseable."""
    for code, _ in LANGUAGES:
        if code == SOURCE_LANG:
            continue
        path = PACKAGE / "locales" / f"{code}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert all(isinstance(k, str) and isinstance(v, str) for k, v in data.items())

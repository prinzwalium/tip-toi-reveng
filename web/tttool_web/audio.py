"""Making sounds the pen can play.

Whatever comes in — a phone recording, an MP3, a browser recording, a spoken
sentence — leaves here as mono Ogg Vorbis at 22050 Hz at a sensible volume, so
that a whisper and a studio file are equally usable in the same book.
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .config import config
from .i18n import t
from .projects import Project, ProjectError

#: Loudness levelling (EBU R128). Without it, one sample booms and the next is
#: inaudible, which on a pen with one small speaker is what people notice most.
LOUDNESS_FILTER = "loudnorm=I=-16:TP=-1.5:LRA=11"

#: Languages offered for spoken sounds, in the order they are shown.
VOICES: tuple[tuple[str, str], ...] = (
    ("de", "Deutsch"),
    ("en", "English"),
    ("fr", "Français"),
    ("it", "Italiano"),
    ("es", "Español"),
)

#: SVOX pico sounds much better than espeak but only knows these.
PICO_LANGUAGES = {
    "de": "de-DE",
    "en": "en-GB",
    "fr": "fr-FR",
    "it": "it-IT",
    "es": "es-ES",
}


def _run(argv: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        argv,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=timeout,
        env={**os.environ, "LC_ALL": "C.UTF-8"},
    )


def convert_to_pen_audio(source: Path, target: Path, level: bool = True) -> None:
    """Convert any audio file into what the pen expects, or raise."""
    target.parent.mkdir(parents=True, exist_ok=True)
    argv = [
        config.FFMPEG_BIN, "-hide_banner", "-nostdin", "-y",
        "-i", str(source),
        "-ar", "22050", "-ac", "1",
    ]
    if level:
        argv += ["-af", LOUDNESS_FILTER]
    argv += ["-c:a", "libvorbis", str(target)]
    try:
        result = _run(argv)
    except FileNotFoundError:
        raise ProjectError(t("This installation cannot convert sounds (ffmpeg is missing).")) from None
    except subprocess.SubprocessError:
        raise ProjectError(t("This sound file could not be converted. Try MP3, WAV or Ogg.")) from None
    if result.returncode != 0 or not target.exists() or target.stat().st_size == 0:
        raise ProjectError(t("This sound file could not be converted. Try MP3, WAV or Ogg."))


def speech_engine() -> str:
    """Which synthesizer this installation has, if any."""
    if shutil.which(config.PICO_BIN):
        return "pico"
    if shutil.which(config.ESPEAK_BIN):
        return "espeak"
    return ""


def speak(text: str, language: str, target: Path) -> str:
    """Synthesize ``text`` into ``target``; returns the engine that did it."""
    text = (text or "").strip()
    if not text:
        raise ProjectError(t("Please write what should be said."))
    if len(text) > 500:
        raise ProjectError(t("That is a lot of text for one sound — please split it up."))
    language = language if language in dict(VOICES) else "de"

    engine = speech_engine()
    if not engine:
        raise ProjectError(
            t("This installation cannot speak text (no speech synthesizer installed).")
        )

    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "speech.wav"
        if engine == "pico":
            argv = [config.PICO_BIN, "--wave", str(wav), "--lang",
                    PICO_LANGUAGES.get(language, "de-DE"), text]
        else:
            argv = [config.ESPEAK_BIN, "-v", language, "-s", "150", "-w", str(wav), text]
        try:
            result = _run(argv)
        except (OSError, subprocess.SubprocessError):
            raise ProjectError(t("The text could not be spoken.")) from None
        if result.returncode != 0 or not wav.exists() or wav.stat().st_size == 0:
            raise ProjectError(t("The text could not be spoken."))
        convert_to_pen_audio(wav, target)
    return engine


def store_sound(project: Project, upload, target_relpath: str) -> None:
    """Save an uploaded or recorded file and convert it in one go."""
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "upload"
        upload.save(raw)
        if raw.stat().st_size == 0:
            raise ProjectError(t("The sound file is empty."))
        convert_to_pen_audio(raw, project.path / target_relpath)

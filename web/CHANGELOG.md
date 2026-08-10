Changelog — tttool web GUI
==========================

Versioned separately from tttool itself; see `RELEASING.md`. Dates are
YYYY-MM-DD.

Unreleased
----------

* Release channels: `:latest` for releases, `:beta` for the `beta` branch,
  `:edge` for `master`, plus pinned `:1.2.3` and `:sha-…` tags.
* The footer and `/healthz` report which build the container was made from, so
  a beta report can name it.
* A development roadmap, `ROADMAP.md`.

1.0.0 — 2026-08-05
------------------

First version.

* Projects: one directory per book, file upload, in-browser YAML editor,
  download of single files or the whole project as a zip.
* Every non-interactive tttool command as a form, showing stdout, stderr, the
  exit code, the exact command line and the files a run created or changed.
* Previews for generated OID codes, extracted samples and PDFs.
* Audio conversion to mono 22050 Hz Ogg Vorbis with ffmpeg.
* Text to speech via pico2wave, falling back to espeak-ng.
* Tooltips throughout the interface.
* Docker image built from this repository, published to the GitHub container
  registry by CI after a smoke test.

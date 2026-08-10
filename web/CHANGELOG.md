Changelog — tttool web GUI
==========================

Versioned separately from tttool itself; see `RELEASING.md`. Dates are
YYYY-MM-DD.

Unreleased
----------

1.1.0 — the book editor
-----------------------

Milestone 1 of `ROADMAP.md`: making a Tiptoi book no longer requires knowing
what a YAML file or an OID code is.

* **Book editor.** Create a book, upload a picture of the page, drag areas onto
  it, give each area a sound, press *Buch erstellen*. Out come a PDF to print
  and a GME file to copy onto the pen. Areas are placed in millimetres on the
  page, so what the editor shows is what gets printed.
* **The power-on field** is placed on every page automatically — without it the
  pen ignores the book.
* **Printing safeguards**: the PDF carries its true physical size, and a printed
  50 mm ruler mark reveals a page that was scaled while printing. Areas that are
  too small for the pen, areas without a sound, overlapping areas and areas on
  the power-on field are all pointed out before building.
* **Codes stay stable** across rebuilds, so pages you have already printed keep
  working when you add to the book.
* **German interface**, with English as the fallback: set `TTTOOL_WEB_LANG=en`
  to see the source strings. The expert area (the tttool command panel) is still
  English.
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

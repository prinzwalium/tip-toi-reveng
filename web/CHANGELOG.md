Changelog — tttool web GUI
==========================

Versioned separately from tttool itself; see `RELEASING.md`. Dates are
YYYY-MM-DD.

Unreleased
----------

1.4.0 — games without programming
---------------------------------

Milestone 4 of `ROADMAP.md`. An area no longer only plays a sound; it can do
the things the pen is actually capable of, chosen from a list instead of
written as a script.

* **One of several, at random** — for variety, so the dog does not say exactly
  the same thing every time.
* **One after the other** — a story in pieces, one per tap, starting over at
  the end.
* **Quiz** — mark areas as the right or a wrong answer of a game, and give the
  game its “right” and “wrong” sounds once.
* **Find them all** — every area of a collecting game counts itself when it is
  first tapped, and the last one missing triggers the reward.
* **Written by hand** — a raw script per area for anyone who has read the
  handbook, with the rest of the panel ignored.

Underneath, each behaviour generates ordinary tttool script lines with the
registers it needs; the generated file is quoted throughout, so a hand-written
script can never break the structure of the YAML.

1.3.0 — sound without fuss
--------------------------

Milestone 3 of `ROADMAP.md`. A book can now be made without any audio software
at all.

* **A sound library per book.** Sounds are no longer stuck to one area: the
  same “wau” can play on every dog in the book, is renamed in one place, and
  shows how often it is used before you delete it.
* **Record with the microphone** straight in the browser: record, listen, keep
  or discard. (Browsers only allow this over `https://` or on `localhost` —
  the dialog says so.)
* **Let the computer speak**: type a sentence, pick a language, and the sound
  is synthesized with the voice already in the container. Speaking it again
  replaces the file, so every area that uses it follows along.
* **Volume levelling** (EBU R128) for everything that comes in, so a phone
  recording and a studio file are equally usable on the pen's small speaker.
* Books written by 1.1 and 1.2 are migrated automatically: their sounds move
  into the library, and areas that shared a file end up sharing one entry.

1.2.0 — books that are actually books
-------------------------------------

Milestone 2 of `ROADMAP.md`.

* **Several pages per book**: add, rename, duplicate, reorder and delete pages;
  every page gets its own picture and its own printed sheet, and they are bound
  into one PDF.
* **Free shapes**: an area no longer has to be a rectangle. Click the corners
  of a lake or an animal and close the outline by clicking the first corner
  again; the corners can be dragged afterwards. Printed as a polygon, so the
  dots stop exactly where the shape does.
* **Print test page** (*Druckprobe*): the same code printed at 8, 10, 12, 15,
  20 and 30 mm, with the power-on field and instructions. Tap the squares with
  the pen and the smallest one that answers is the smallest area your printer
  can do. It is offered before the book itself.
* **Dark artwork is flagged**: areas sitting on a dark part of the picture are
  pointed out before printing, because the pen cannot read dots there.
* **Duplicate an area** with the same shape and size.

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

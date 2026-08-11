Changelog — tttool web GUI
==========================

Versioned separately from tttool itself; see `RELEASING.md`. Dates are
YYYY-MM-DD.

Unreleased
----------

2.1.3 — the test page said the wrong thing about itself
-------------------------------------------------------

The squares on the test page were labelled as if they told you what your
printer manages. They do not, and saying so sent people looking in the wrong
place when nothing worked.

Every square carries the same code at the same dot size and the same spacing —
the pattern is *tiled*, so a bigger square is simply more repetitions of the
same 1.016 mm tile. Nothing about the printing differs between them. (tttool's
`--pixel-size` does not change this either: its SVG output draws every dot as
the same two units regardless.)

What the ladder actually measures is **how small an area may be**. The pen
reads a small window around its tip, so near the edge of a small square part of
that window is blank paper, and there is less to decode. Together with having
to hit the thing at all, that is what makes small areas unreliable — a property
of the pen and of aim, not of the printer.

* The page now says this on itself: tap biggest first, all squares carry the
  same code, the smallest that still answers reliably is the smallest area
  worth drawing — **and if even the biggest stays silent it is not the size but
  the printer or the scale.** That last line is the one that would have saved a
  wrong turn.
* `/hilfe/stift` says the same, in place of the claim it made before.

2.1.2 — out of the printer's dead zone
--------------------------------------

The first print test also came out with pieces missing at the edges, the 50 mm
ruler mark among them. That is not the printer misbehaving: no consumer printer
prints to the edge of the sheet, and four to five millimetres all round stay
white. This program was putting things there.

* The ruler mark sat **4 mm from the bottom edge**, with its end ticks reaching
  to 2.5 mm — inside the dead zone of essentially every printer. The one mark
  that proves the print was not scaled was the first thing to be cut off.
  Everything the program places now keeps **12 mm** clear.
* The power-on field moved from 8 mm to the same 12 mm. Half a power-on field
  is a book that never switches on.
* The test page gained a **dashed frame at that margin**. If it comes out
  complete on all four sides, the printer reaches far enough for everything
  else on the page — worth knowing from one sheet rather than from a finished
  book.
* An area you place yourself within 10 mm of the edge is now flagged before
  printing, the same way areas that are too small are.
* `/hilfe/stift` explains the margin, and says the thing that is easy to get
  backwards: a page that comes out **cut off was printed at true size**. It is
  a page where everything fits but the 50 mm line measures 48 that has been
  scaled down — and that is the one no pen can read.

2.1.1 — the dots were 1.6 % too tight
-------------------------------------

**Every page printed before this version has to be printed again.** The file
for the pen is unaffected — only the paper was wrong. Open the book, press
*Buch erstellen*, print the new PDF.

The first real print test failed: correct paper size, ruler said 50 mm, and the
pen ignored every field. The cause was a rounding in tttool's SVG output taken
at face value here. A code is written as `width="30mm" viewBox="0 0 1440 1440"`,
which reads as 48 units per millimetre — but 1440 of those units are 30.48 mm,
not 30. One unit is 1/1200 inch, so a millimetre is 47.244 units.

Printing the dot grid at 48 units/mm made it **1.6 % too tight**: 1.000 mm per
cell of the OID grid instead of 1.016 mm. Everything a person can check looked
right, which is exactly why it took a sheet of paper to find.

* The page is now drawn at 47.244 units per millimetre, and the scale is
  derived from the pattern tttool actually emits rather than assumed, so a
  future tttool that draws its tiles differently moves the page with it.
* Measured against tttool's own PDF output, which tiles at 2.88 pt: ours now
  tiles at 2.88 pt too, on both the book page and the test page.
* Two tests check that number through the whole pipeline, and the image smoke
  test measures it in the container on every build. Nothing about a page's
  appearance would have caught this; the number is the only witness.

2.1.0 — every area in a list
----------------------------

Finding an area on the page only works when you can see it. An area three
millimetres wide, or one sitting underneath another, was effectively
unreachable — and those are exactly the ones you want to get rid of.

* **A list of every area of the page**, under the picture: name, its sound,
  and per row a button to listen, to change the sound, and to delete. Pointing
  at a row lights the area up on the page; clicking the name selects it.
* Areas too small for the pen are marked *zu klein* in the list, and ones
  without a sound say so — so the two things that would otherwise be found by
  the check before printing are visible while you work.
* **Deleting an area no longer asks.** It is undoable, and this program's own
  rule is that only what cannot be undone asks first. Instead it says what it
  deleted and offers *Rückgängig* right there — which is what made clearing
  away several stray areas tedious.

2.0.0 — the finished product
----------------------------

Milestone 7 of `ROADMAP.md`, and the point of the whole exercise: a program you
can hand to somebody who will never read this file. Nothing here is a new thing
a book can do — it is what a tool needs before it can be recommended.

* **Big pictures no longer cost what they used to.** An ordinary A4 scan at
  300 dpi is 3508 × 2480 pixels, twelve megabytes as a PNG. It used to be sent
  to the browser in full on every page, and embedded in the PDF as raw pixels.
  Now the editor gets a small copy of its own, and the picture goes into the
  PDF as JPEG at print resolution. Measured on one such page: the editor
  downloads **12 MB → 0.5 MB**, and the printed PDF is **18 MB → 1.9 MB** at
  unchanged resolution. The original is never modified — it is still what gets
  printed from.
  Only the artwork is compressed. The dots the pen reads are vector patterns
  and are provably untouched: the code re-encodes exactly the one image whose
  size it embedded, and a test checks the patterns are still there afterwards.
* **Back up everything, restore everything.** *Alles sichern* packs every book
  on the server into one file; adding that file back restores all of them.
  Inside it is simply one `.tiptoi` per book, so a single book can be pulled
  out of a backup with any unzip program.
* **Books made by earlier versions keep working**, and there is now a test that
  says so: a `book.json` in the 1.1 shape — no sound library, no behaviours, no
  groups — opens, gets a library, and builds. A migrated sound is named "wau"
  now rather than "wau.mp3".
* **The project stops accumulating rubbish.** Deleting a page deletes its
  picture (unless a duplicated page still uses it), and a book that loses a
  page no longer keeps offering the printed page that went with it.
* Proper plurals: "1 Seite(n)" was software talking. It says *eine Seite* and
  *3 Seiten* now, in both languages.

1.6.0 — sharing and finish
--------------------------

Milestone 6 of `ROADMAP.md`. Up to now a book lived on the server that made it,
in a language chosen by whoever started the container, and needed a mouse. All
three are fixed.

* **Pass a book on.** *Weitergeben* packs a whole book — the model, the page
  pictures, the sounds and the code assignment — into one `.tiptoi` file;
  *Buch hinzufügen* unpacks it into a new book on any other server. The codes
  come along, so a page printed before the export still works with the
  re-imported book. It doubles as the backup: one file, everything in it.
  Nothing from the archive is written to a path that came out of the archive —
  file names are rebuilt from the book, so a hand-crafted archive cannot reach
  outside its own project.
* **The language is now the visitor's choice**, DE/EN in the header, remembered
  in a cookie; `TTTOOL_WEB_LANG` still sets what everyone sees first. The
  German is complete this time — the tttool command panel, the file list and
  the browser-side strings were the last English corners, and a test now walks
  every translatable string and fails on a missing one (and on a leftover, and
  on a dropped `{placeholder}`).
* **The editor works without a mouse.** Tab reaches every area, Enter selects
  it, the arrow keys move it and `+`/`−` resize it — with shift for bigger
  steps, and a whole burst of nudges collapsing into one undo step. Each area
  carries a label a screen reader can read out ("Feld Hund, 32 zu 88
  Millimeter, spielt Hund"), every page starts with a skip link, and the accent
  colour was darkened to reach WCAG AA on the page background.
* **Erste Schritte**, an illustrated walk through making a first book, at
  `/hilfe/erste-schritte` and linked from the start screen.

1.5.0 — the guided path
-----------------------

Milestone 5 of `ROADMAP.md`. Everything the previous versions made *possible*
this one tries to make *obvious*. Nothing here adds a capability to the pen; it
adds a path through the program for someone who has never made a book before.

* **Starting points instead of an empty page.** Creating a book asks what you
  want to make — a sound book, a quiz, a collecting game, or nothing at all —
  and sets it up: an example picture drawn to the page size, areas already
  painted on it, and sounds that already speak. A new book says something on
  the first tap without anything being uploaded.
* **The four steps, always visible.** A strip above the editor shows where you
  are — picture, areas, sounds, build — with the step you are on marked and the
  ones you finished struck through. It can be hidden, and stays hidden.
* **“Onto the pen”**, a page of its own: printing at 100 %, why a laser
  printer, how to measure the test page, where the `.gme` file goes on the pen,
  and the five things people actually run into when the pen stays silent.
* **A checklist before printing** in the editor, next to the build button, so
  the printer dialogue settings are read at the moment they matter.
* **Redo**, next to the undo that was already there (`Ctrl+Shift+Z`, `Ctrl+Y`).
* Area names are drawn in the corner of the area now, not across the middle of
  the picture.

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

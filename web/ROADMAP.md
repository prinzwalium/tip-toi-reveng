Roadmap — from a tttool front end to a Tiptoi book maker
========================================================

What we are building
--------------------

A program you run on your own server and open in a browser, in which you make
your own Tiptoi books and games: upload the picture of a page, paint the areas
the pen should react to, give each area a sound, print the result, copy one file
onto the pen. No command line, no YAML, no knowing what an OID code is.

Everything underneath is done by `tttool`, which is in this repository and knows
the GME file format, the dot patterns and the whole Tiptoi ecosystem. We are not
reimplementing any of that — we are building the part that is missing: a way to
use it without being a programmer.


The one rule
------------

**A person who has never opened a terminal must be able to make a working book.**

In practice that means, for every feature we add:

* The interface talks about *pages, areas, sounds and printing* — not about
  OID codes, GME files, product ids, YAML or resolutions. Those words may
  appear in an “advanced” corner, never in the main path.
* The program prevents the mistakes it can (an area too small for the pen, a
  page without a power-on field, a PDF printed at the wrong scale) instead of
  documenting them.
* When something can only go wrong outside the program — nearly always the
  printer — it says so in plain words, before the user wastes paper, and offers
  a cheap way to check (a test page).
* Anything a user cannot undo asks first; anything they can undo does not.
* No step ever requires editing a file by hand. Hand-editing stays *possible*
  for people who want it; it is never the only way to do something.


Where we are now
----------------

Version 1.0 is a faithful front end for the tool: projects, file upload, an
editor for the YAML source, every tttool command as a form, previews, audio
conversion, packaged as a Docker image with CI, betas and releases.

That is a good tool for someone who already understands Tiptoi files, and it is
the foundation for everything below — but it is not yet something you can hand
to a person who just wants to make a sound book for their child.

The step that is missing is the one the handbook currently describes as “open
GIMP at 1200 dpi, generate one PNG per code, place them as layers, do not scale
them, print without fitting to page”. That is the step we are replacing.


Milestone 1 — the book editor, first usable version ✅
------------------------------------------------------

*Shipped in 1.1 · the smallest thing that produces a real book*

Goal: upload one picture, paint rectangles on it, drop a sound on each, get a
printable PDF and a file for the pen — without leaving the browser.

Ships:

* A **book** as its own kind of project: pages with a picture and a physical
  size, areas with a shape and a sound.
* An **editor canvas**: the page picture, draw and move and resize rectangular
  areas, zoom and pan, delete, undo.
* **Sounds**: upload a file per area (converted automatically to what the pen
  needs) and hear it back in the browser.
* **Make it** in one button: generates the source, assembles the GME file and
  composes the printable PDF, in which each area is filled with its dot
  pattern over the picture. (This part is proven — tttool emits each code as a
  tileable SVG pattern that any shape can be filled with.)
* **The power-on field**, placed automatically on every page, because a book
  without one does nothing.
* Plain-language result: *print this, copy that onto the pen*.

Done when: someone who has never used a command line uploads a drawing, paints
four areas, gives them four sounds, prints the PDF on a laser printer and hears
the right sound for each area — guided only by the screen.

Status: everything above is in 1.1, and the interface is German. What is still
open is the last half of that sentence — the printed page has been verified on
screen and in CI (true size, patterns inside the painted areas), but not yet
with a real printer and a real pen. That is the first thing to try on the beta.


Milestone 2 — books that are actually books ✅
----------------------------------------------

*Shipped in 1.2 · everything M1 left out that a real project needs*

* Several pages per book, reorderable, each with its own picture.
* Areas that are not rectangles: polygons, so a lake or an animal can be tapped
  exactly where it is drawn. (Freehand drawing, as opposed to clicking corners,
  is still open.)
* A **test page** to print before the whole book: the same code at 8–30 mm with
  instructions for checking it with the pen. This is the cheapest possible
  answer to “will my printer work for this?”, and it tells the user the
  smallest area size their printer supports.
* Print safeguards: a PDF that carries its true size, a printed ruler mark to
  verify the scale, a warning for areas smaller than the pen can read reliably,
  and a warning when the artwork under an area is so dark that the dots will
  drown in it.
* Copy, rename, duplicate pages and areas.

Done when: a 12-page book with irregular areas prints correctly at the right
scale, and a user who prints it wrong is told what went wrong.


Milestone 3 — sound without fuss ✅
-----------------------------------

*Shipped in 1.3*

* **Record straight into the browser** with a microphone, listen, keep or
  discard, assign to an area.
* **Let the computer speak it**: type the text, pick a voice, hear it — using
  the speech synthesis already in the image.
* A **sound library** per book: every sound in one place, reusable across
  areas, drag onto an area, replace everywhere at once.
* Automatic conversion and loudness levelling, so a phone recording and a
  studio file sound equally usable on the pen.

Done when: a book can be made end to end without any audio software.

Status: all of it is in 1.3. Recording needs the page to be served over https
or from localhost — that is a browser rule, not something the program can lift,
so the recording tab says so instead of failing silently.


Milestone 4 — games without programming ✅
------------------------------------------

*Shipped in 1.4 · this is where a “book maker” becomes a “game maker”*

The pen can do far more than play a sound per area — count, remember, choose at
random, react differently the second time. Today that means writing script
lines. Instead, each area gets a small set of understandable behaviours:

* *Play a sound* (the default).
* *Play one of these, at random* — for variety.
* *Say something different each time* — first tap, second tap, …
* *Quiz*: one question area, several answer areas, right and wrong reactions.
* *Find them all*: tap every animal on the page, get a reward when complete.
* *Counter*: score, lives, collected items, with a sound when a total is
  reached.

Each behaviour is a small form, and generates the script underneath. An
“advanced” field per area accepts a raw script line for anybody who has read the
handbook and wants more.

Done when: a memory game and a quiz can be built without ever seeing a script.

Status: random, sequence, quiz, find-them-all and the hand-written escape hatch
are in 1.4, and every generated script was checked against the real tttool
(assembled and linted, not only unit tested). Counters as a separate behaviour
— score, lives — are not there yet: “find them all” covers the same mechanism,
so they are waiting for someone to actually want them.


Milestone 5 — the guided path ✅
--------------------------------

*Shipped in 1.5 · the difference between “possible” and “obvious”*

* A **start screen** that asks what you want to make (sound book, quiz,
  collecting game, blank) and sets the book up accordingly.
* **Starting points** with drawn example artwork and spoken sounds, so the
  first book talks back within a minute of creating it.
* **“Onto the pen”**: a page that explains, with pictures, how to plug in the
  pen, where the file goes, and what to do when the pen ignores it.
* A **checklist before printing**, with the printer settings that matter.
* Undo *and* redo across the whole editor, and a warning before anything
  destructive.

Done when: a first-time user reaches a working book from the start screen
without asking anyone for help.

Still open from this milestone: nobody has yet held a page printed by this
program next to a pen. Everything up to the PDF is checked automatically —
paper size, physical scale, dot pitch — but the last centimetre is unverified.


Milestone 6 — sharing and finish ✅
-----------------------------------

*Shipped in 1.6 · a book stops being stuck on the server that made it*

* **Export and import a whole book** as one `.tiptoi` file (pictures, sounds,
  areas and the code assignment), so books can be shared, backed up and moved
  between servers — and a page printed before the move still works after it.
* **German interface**, switchable per visitor. Complete this time: the command
  panel for advanced users is translated too, and a test fails if any string in
  the interface has no German counterpart.
* Accessibility pass: the whole editor is operable from the keyboard (tab
  between areas, arrows to move, `+`/`−` to resize), every area carries a
  spoken label, every page starts with a skip link, and the colours meet
  WCAG AA.
* Illustrated getting-started documentation at `/hilfe/erste-schritte`, written
  against the interface as it now is.

Done when: a book made on one server can be opened and printed on another, and
the interface is usable in German and by keyboard.


Milestone 7 — 2.0, the finished product ✅
------------------------------------------

*Shipped in 2.0 · the promise that it is finished*

* **Stability under real use.** The measured problem was the page picture: an
  ordinary 300 dpi scan meant 12 MB downloaded per page in the editor and an
  18 MB PDF per printed page. The editor now works on a small preview and the
  original is kept only for output — exactly as this file predicted it would
  have to. Same page today: 0.5 MB to the editor, 1.9 MB of PDF, unchanged
  resolution on paper.
* **Backup and restore**: every book on the server in one file, and back again.
* **A migration path**, with a test that opens a `book.json` in the shape 1.1
  wrote and builds it.
* **Documentation that explains itself**: *Erste Schritte*, *Auf den Stift* and
  the command reference, all illustrated, all in German.

What is still not verified is the one thing no test can reach: nobody has held
a page printed by this program next to a pen. Everything up to the PDF is
checked automatically — paper size, physical scale, dot pitch, and that the dot
patterns survive every step — but the last centimetre is between a printer and
a piece of paper.


Decisions worth making early
----------------------------

* **The editor owns the book.** The visual book is the source of truth and the
  YAML is generated from it. Round-tripping arbitrary hand-written YAML back
  into a visual editor is where projects like this drown. Advanced users keep
  the raw editor and the command panel — for a *book project* those become a
  read-only view of what was generated, plus per-area raw script fields.
* **German first or English first?** See M6. Cheap to decide now, expensive to
  retrofit late.
* **Print output is vector.** Filling shapes with the dot pattern keeps the PDF
  small and exact instead of rasterising a page at 1200 dpi. Large filled areas
  can fall back to tttool's pattern-as-embedded-image variant.


Risks, honestly
---------------

* **The printer is the weak link,** not the software. Toner-based laser
  printers work because the pen reads infrared absorption; most inkjets do not.
  No amount of interface can fix that, so the tool must detect it early (test
  page) and say it plainly.
* **Scale errors are silent.** A PDF printed with “fit to page” produces a book
  that looks perfect and does nothing. Hence the printed ruler mark.
* **Big pages in the browser.** A 1200 dpi page picture is large; the editor
  works on a downscaled preview and keeps the original only for output.
* **Scope.** Every milestone is a usable product on its own; if the project
  stops after M2, what exists still makes books.


Out of scope
------------

Reimplementing anything tttool already does; editing commercial Ravensburger
products beyond what tttool supports; pen firmware; user accounts and
multi-tenant hosting (this is a tool you run for yourself or your family).

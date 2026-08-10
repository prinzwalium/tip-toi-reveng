tttool web GUI
==============

Make your own Tiptoi books in the browser, on your own server. The interface is
German by default (`TTTOOL_WEB_LANG=en` switches to English).

**Making a book** — the part that needs no technical knowledge:

 1. *Neues Buch*, give it a name, pick the paper size.
 2. Upload a picture of the page.
 3. Drag rectangles onto it (or click the corners of a free shape), one per
    thing that should make a sound.
 4. Give each one a sound: record it with the microphone, let the computer
    speak a sentence, or upload a file. Sounds live in the book's library and
    can be reused on as many areas as you like.
 5. *Buch erstellen* → a test page for your printer, a PDF to print, and a
    `.gme` file to copy onto the pen.

Recording needs the page to be served over `https://` or opened on
`localhost` — browsers do not allow microphone access otherwise.

Print the PDF **at 100%** (never “fit to page”) on a laser printer, check the
printed 50 mm mark with a ruler, tap the power-on field, and the pen reads your
book. What is still missing is on the [roadmap](ROADMAP.md).

Under the book editor sits a full front end for
[`tttool`](https://github.com/entropia/tip-toi-reveng), for anyone who wants it:

 * **projects** — one directory per book, with upload, in-browser YAML editing,
   download of single files and of the whole project as a zip,
 * **every non-interactive tttool command** — assemble, export, info, scripts,
   games, lint, segments, holes, explain, media, binaries, oid-table,
   oid-codes, oid-code, set-language, set-product-id — as a form, with the
   resulting output, the exact command line and the list of files it wrote,
 * **previews** — play extracted `.ogg` samples, look at generated OID codes and
   PDFs without leaving the page,
 * **audio conversion** — turn any uploaded audio file into the mono 22050 Hz
   Ogg Vorbis the pen expects, using ffmpeg,
 * **tooltips** — point at (or tab to) any command, field or file action for a
   one-line explanation of what it does; the *Commands* page has the long version.

`tttool play` is not available in the browser: it is an interactive terminal
simulation. Run it inside the container if you need it (see below).


Running it
----------

```console
$ git clone https://github.com/entropia/tip-toi-reveng.git
$ cd tip-toi-reveng
$ cp .env.example .env          # optional: port, auth, where the data goes
$ docker compose up -d --build
```

Then open <http://localhost:8080>.

Every setting in `.env` is optional; `docker compose` picks the file up
automatically and falls back to the defaults documented in `.env.example`.

The first build compiles tttool from source with GHC, which needs roughly
**4 GB of RAM and 15–30 minutes**. Everything after that is cached; changing
only the web GUI rebuilds in seconds.

If that is too much for your server, build against the official statically
linked release binary instead (x86_64 only, downloaded from the project's
GitHub releases — takes about a minute):

```console
$ docker build --build-arg TTTOOL_SOURCE=release -t tttool-web .
```

or set `TTTOOL_SOURCE: release` under `build.args` in `docker-compose.yml`.

Without compose:

```console
$ docker build -t tttool-web .
$ docker run -d --name tttool-web -p 8080:8080 -v tttool-data:/data tttool-web
```


Running a prebuilt image
------------------------

`.github/workflows/docker.yml` builds the image on every push to `master` and
on every tag, smoke tests it, and pushes it to the GitHub container registry as
`ghcr.io/<owner>/tttool-web`. On the server you then need two files and no
checkout at all:

```console
$ curl -O https://raw.githubusercontent.com/entropia/tip-toi-reveng/master/docker-compose.ghcr.yml
$ curl -o .env https://raw.githubusercontent.com/entropia/tip-toi-reveng/master/.env.example
$ $EDITOR .env                  # at least TTTOOL_IMAGE, if you forked
$ docker compose -f docker-compose.ghcr.yml up -d
```

`docker compose -f docker-compose.ghcr.yml pull && … up -d` updates it later.
The workflow builds `linux/amd64` only — compiling tttool for arm64 under
emulation takes hours, so build the image on the ARM machine itself instead.

Pick a channel with `TTTOOL_IMAGE` in `.env`: `:latest` for releases, `:beta`
for the next version if you are willing to report what breaks, `:edge` for
every merge. [RELEASING.md](RELEASING.md) explains the channels, how to report
a beta problem and how a release is cut; [ROADMAP.md](ROADMAP.md) is where this
is going — a book editor that needs no technical knowledge at all.


Where your data lives
---------------------

Everything is in `/data`, one directory per project — nothing else is stored,
there is no database. Back it up by copying that directory (or by using
“Download .zip” in the GUI).

The container runs as uid 1000. A named volume (the default) just works; for a
directory on the host, point `TTTOOL_DATA` at it and make it writable for that
uid first:

```console
$ mkdir -p data && sudo chown -R 1000:1000 data
$ echo 'TTTOOL_DATA=./data' >> .env
$ docker compose up -d
```


Configuration
-------------

The compose files read these from `.env` (see `.env.example`): `TTTOOL_PORT`,
`TTTOOL_BIND_IP`, `TTTOOL_DATA`, `TTTOOL_IMAGE`, `TTTOOL_CONTAINER_NAME`,
`TTTOOL_SOURCE` and `TZ`. They only shape the container; the application itself
is configured with the environment variables below, which the compose files
pass through:

| Variable | Default | Meaning |
| --- | --- | --- |
| `TTTOOL_WEB_USER` / `TTTOOL_WEB_PASSWORD` | unset | Enable HTTP basic auth (both must be set) |
| `TTTOOL_WEB_PORT` | `8080` | Port inside the container |
| `TTTOOL_WEB_HOST` | `0.0.0.0` | Listen address |
| `TTTOOL_WEB_THREADS` | `4` | Number of request threads |
| `TTTOOL_WEB_DATA` | `/data` | Where projects are stored |
| `TTTOOL_WEB_MAX_UPLOAD_MB` | `512` | Maximum size of one upload request |
| `TTTOOL_WEB_TIMEOUT` | `300` | Seconds after which a tttool run is killed |
| `TTTOOL_WEB_MAX_OUTPUT_BYTES` | `524288` | How much command output is sent to the browser |
| `TTTOOL_WEB_ALLOW_DELETE` | `true` | Set to `false` to hide all delete buttons |
| `TTTOOL_WEB_SECRET_KEY` | random | Flask session key, only used for flash messages |
| `TTTOOL_BIN` | `/usr/local/bin/tttool` | Path of the tttool binary |
| `TTTOOL_WEB_EXAMPLES` | `/app/examples` | Files used by “start from the example book” |

There is a health endpoint at `/healthz` (always reachable, even with basic
auth enabled) that reports the tttool version.


Exposing it to the internet
---------------------------

The GUI has no user accounts and lets anyone who can reach it read and write
files in `/data` and run tttool. Do not put it on a public address without at
least basic auth, and terminate TLS in a reverse proxy in front of it, e.g.:

```nginx
location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host $host;
    client_max_body_size 512m;
}
```


A typical session
-----------------

 1. **New project** → *start from the example book* → *Create*.
 2. Press **Run assemble** — you now have `example.gme`, downloadable from the
    file list, ready for the pen.
 3. Edit `example.yaml` in the browser, upload your own `.ogg` files (or upload
    an mp3 and press **→ Ogg**), assemble again.
 4. Use **oid-table** to get a PDF with all the codes used in your book, print
    it at 1200 dpi with a laser printer, and glue it into the book.

To inspect an existing GME file, create an empty project, upload the `.gme` and
run **info**, **scripts**, **games** or **media**.


The interactive simulator
-------------------------

```console
$ docker compose exec -it tttool-web tttool play /data/my-book/book.yaml
```


Continuous integration
----------------------

`.github/workflows/docker.yml` runs the pytest suite, builds the image, and
smoke tests it: it starts the container, waits for `/healthz`, checks that a
speech synthesizer, `oggenc` and `ffmpeg` are present, then creates a project
from the example book through the HTTP API and has it assemble a GME file and
an OID code PDF. Only after that does it push to the registry (never for pull
requests). Layer caching keeps the GHC build out of most runs; a manual run
(“Run workflow”) can pick `release` instead to skip it entirely.


Development
-----------

The GUI is a small Flask app; it only ever calls tttool with an argument list
built from validated form values, never through a shell.

```console
$ cd web
$ python3 -m venv .venv && . .venv/bin/activate
$ pip install -r requirements.txt -r requirements-dev.txt
$ TTTOOL_WEB_DATA=/tmp/tttool-data TTTOOL_BIN=../tttool \
    python -m flask --app wsgi run --debug --port 8080
$ pytest                      # runs against a stub tttool, no GHC needed
```

Layout:

| Path | What it is |
| --- | --- |
| `tttool_web/app.py` | routes |
| `tttool_web/commands.py` | the catalogue of exposed tttool commands |
| `tttool_web/runner.py` | validation of form values and the subprocess call |
| `tttool_web/projects.py` | project directories and safe path handling |
| `tttool_web/templates`, `tttool_web/static` | the UI (no build step, no CDN) |
| `tests/` | pytest suite |

Adding a command means adding one `Command(...)` entry in `commands.py`; the
form and the argv are derived from its parameter list.

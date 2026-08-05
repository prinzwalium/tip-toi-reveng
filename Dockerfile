# tttool web GUI — https://github.com/entropia/tip-toi-reveng
#
#   docker build -t tttool-web .
#   docker run -p 8080:8080 -v tttool-data:/data tttool-web
#
# By default tttool is compiled from the sources in this repository, which takes
# a while (~15-30 minutes and about 4 GB of RAM for GHC).  On a small server you
# can use the official statically linked release binary instead:
#
#   docker build --build-arg TTTOOL_SOURCE=release -t tttool-web .
#
# Either way the final image contains just that binary and the Python front end.

# Both are used in FROM instructions, so they have to live before the first one.
ARG TTTOOL_SOURCE=build
ARG TTTOOL_VERSION=1.11

# ---------------------------------------------------- tttool, built from source

FROM haskell:9.2.8 AS tttool-build

# buildpack-deps (the base of the haskell image) already provides git, zlib and
# gmp headers.  Buster is archived by now, so only touch apt if something is
# genuinely missing.
RUN set -eux; \
    if [ ! -e /usr/include/zlib.h ] || ! command -v git > /dev/null; then \
        sed -i 's|deb.debian.org|archive.debian.org|g; s|security.debian.org|archive.debian.org|g; /buster-updates/d' \
            /etc/apt/sources.list; \
        apt-get update; \
        apt-get install -y --no-install-recommends git zlib1g-dev; \
        rm -rf /var/lib/apt/lists/*; \
    fi

WORKDIR /src

# Only the files that actually take part in the Haskell build are copied here,
# so that editing the web GUI does not invalidate this (expensive) layer.
COPY cabal.project cabal.project.freeze tttool.cabal Setup.hs LICENSE ./
COPY README.md Changelog.md ./
COPY src ./src

RUN cabal update && cabal build exe:tttool

RUN set -eux; \
    mkdir -p /out; \
    cp "$(cabal list-bin exe:tttool)" /out/tttool; \
    strip /out/tttool; \
    /out/tttool --help > /dev/null

# ------------------------------------------- tttool, from the official release

# Alternative to the stage above, selected with --build-arg TTTOOL_SOURCE=release.
# The release zip only contains an x86_64 binary.
FROM debian:bookworm-slim AS tttool-release

ARG TTTOOL_VERSION
RUN set -eux; \
    [ "$(dpkg --print-architecture)" = "amd64" ] || \
        { echo "The tttool release binary is x86_64 only; build from source instead." >&2; exit 1; }; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl unzip; \
    rm -rf /var/lib/apt/lists/*; \
    cd /tmp; \
    curl -fsSL -o tttool.zip \
        "https://github.com/entropia/tip-toi-reveng/releases/download/${TTTOOL_VERSION}/tttool-${TTTOOL_VERSION}.zip"; \
    unzip -q tttool.zip; \
    mkdir -p /out; \
    cp "tttool-${TTTOOL_VERSION}/linux/tttool" /out/tttool; \
    chmod +x /out/tttool; \
    /out/tttool --help > /dev/null

# ------------------------------------------------------------------- runtime

FROM tttool-${TTTOOL_SOURCE} AS tttool-bin

FROM debian:bookworm-slim

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/opt/venv/bin:$PATH \
    TTTOOL_WEB_DATA=/data \
    TTTOOL_BIN=/usr/local/bin/tttool

# ffmpeg converts uploaded audio, vorbis-tools (oggenc) and a speech synthesizer
# are what tttool needs for its text-to-speech feature.  SVOX pico sounds much
# better than espeak but lives in Debian's non-free component, so it is optional.
RUN set -eux; \
    echo 'deb http://deb.debian.org/debian bookworm main contrib non-free' \
        > /etc/apt/sources.list.d/tttool-nonfree.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        espeak-ng \
        ffmpeg \
        libgmp10 \
        libnuma1 \
        libtinfo6 \
        python3 \
        python3-venv \
        vorbis-tools \
        zlib1g; \
    apt-get install -y --no-install-recommends libttspico-utils \
        || echo 'note: libttspico-utils unavailable, text-to-speech will use espeak-ng'; \
    command -v espeak > /dev/null || ln -s espeak-ng /usr/bin/espeak; \
    rm -rf /var/lib/apt/lists/*

COPY --from=tttool-bin /out/tttool /usr/local/bin/tttool

# The binary is built on an older Debian; fail the build here rather than at
# run time if the runtime image is missing one of its shared libraries.
RUN tttool --help > /dev/null

RUN python3 -m venv /opt/venv
COPY web/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY web /app
# Example files a new project can be seeded with, straight out of the repository.
# example.yaml refers to its samples as example/<name>.ogg, so keep that layout.
COPY example.yaml text2speech.yaml text2speech-multi-lang.yaml /app/examples/
COPY example /app/examples/example

RUN set -eux; \
    groupadd --gid 1000 tttool; \
    useradd --uid 1000 --gid 1000 --home-dir /data --shell /usr/sbin/nologin tttool; \
    mkdir -p /data; \
    chown -R tttool:tttool /data

WORKDIR /app
USER tttool
VOLUME ["/data"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=4).status == 200 else 1)"

CMD ["python3", "serve.py"]

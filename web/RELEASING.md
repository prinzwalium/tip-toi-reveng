Releases and test builds
========================

The web GUI is versioned separately from tttool itself. Its version lives in
one place, `web/tttool_web/__init__.py`, and is shown in the footer of every
page together with the build the container was made from.


Which image should I run?
-------------------------

| Tag | Built from | Use it when |
| --- | --- | --- |
| `ghcr.io/<owner>/tttool-web:latest` | the newest release tag | you just want a working tool |
| `…:1.2.3`, `…:1.2`, `…:1` | that release | you want to pin a version |
| `…:beta` | the `beta` branch | you agreed to try the next version and report back |
| `…:edge` | `master` | you follow development and can live with rough edges |
| `…:sha-abc1234` | one commit | you need exactly the build someone mentioned |

`latest` only moves when a release is tagged, so pulling it never lands you on
an untested build.

Switch channels by setting `TTTOOL_IMAGE` in `.env`:

```dotenv
TTTOOL_IMAGE=ghcr.io/prinzwalium/tttool-web:beta
```

```console
$ docker compose -f docker-compose.ghcr.yml pull
$ docker compose -f docker-compose.ghcr.yml up -d
```

Your projects live in the `/data` volume and are not touched by switching
images. Going *back* to an older image is equally safe as long as you have not
used a feature the older version does not know about yet.


Testing a beta build
--------------------

1. Run the `:beta` image as above.
2. Use it for something real — a book you actually want to print.
3. When something is wrong, open an issue with **the build id from the page
   footer** (for example `beta (a1b2c3d)`), what you did, and what you
   expected. `/healthz` reports the same information as JSON.

Nothing else is expected of a tester; a beta that eats an afternoon and
produces a working book is a successful test, and so is one that does not.


How the branches work
---------------------

```
feature branch  ──PR──▶  beta  ──PR──▶  master  ──tag web-v1.2.3──▶  release
                          ↓               ↓                ↓
                        :beta           :edge     :1.2.3 :1.2 :1 :latest
```

* `beta` is the integration branch: work that is ready for someone to try, but
  not yet promised to be stable.
* `master` is what has survived beta.
* Release tags are prefixed `web-v` so that they never collide with tttool's
  own version tags (`1.11`, …) in this repository.


Cutting a release
-----------------

1. Decide the version, following [semantic versioning](https://semver.org/):
   * **patch** (1.2.3 → 1.2.4) — fixes only,
   * **minor** (1.2.3 → 1.3.0) — new things, existing books keep working,
   * **major** (1.2.3 → 2.0.0) — existing projects need a migration step.
2. Update `__version__` in `web/tttool_web/__init__.py`.
3. Move the entries under “Unreleased” in `web/CHANGELOG.md` into a section for
   the new version, with today's date.
4. Merge to `master` and tag it:

   ```console
   $ git tag web-v1.2.3
   $ git push origin web-v1.2.3
   ```

CI refuses to publish a tag whose version does not match `__version__`, then
builds, smoke tests and pushes `1.2.3`, `1.2`, `1` and `latest`.


Publishing the package
----------------------

The first push creates the container package under the repository owner. GitHub
makes new packages **private**; to let others (or a server without credentials)
pull it, open the package page → *Package settings* → *Change visibility* →
*Public*. A private package needs a login on the server:

```console
$ echo "$GITHUB_TOKEN" | docker login ghcr.io -u <user> --password-stdin
```

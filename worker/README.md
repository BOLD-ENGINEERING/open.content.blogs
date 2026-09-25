# Markdown publishing worker

Python 3.14 turns a Git ref into sanitized Markdown, builds the static Astro
template, and atomically publishes a local site. Run commands from `worker/`.
Production uses Linux/glibc atomic directory exchange (`renameat2`). Availability
is probed on first use per filesystem; other hosts use the rename fallback.
Git, Node >=22.12.0, pnpm 11.7.0, and Python 3.14 must be on PATH.

## Fresh checkout setup

From the repository root:

```sh
cd web
pnpm install --frozen-lockfile
cd ../worker
python3.14 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install --group dev
pnpm install --frozen-lockfile
```

The worker npm manifest has only Wrangler. Its optional engine installation
scripts are disabled: Pages static upload and CLI commands need no local Workerd
runtime. The template's existing esbuild install script remains enabled.
Dependencies are installed explicitly; pnpm's pre-script auto-install is disabled
to prevent each isolated build HOME from triggering a dependency reinstall.

For browser checks, either install Chromium using:

```sh
.venv/bin/python -m playwright install --with-deps chromium
```

or use an already installed `chromium` on PATH. Tests prefer Playwright's bundled
browser, then the system executable. An offline/local-only session can use the
system executable without downloading a browser. No browser test contacts an
external site, and the tests use only local `file://` Git repositories.

```sh
.venv/bin/python -m worker doctor
```

Doctor checks tool versions, the template and its dependencies, writable roots,
and browser availability. Missing Cloudflare credentials are reported as MISSING
and do not fail local setup. Values are never printed. Wrangler version checks
are local and do not deploy anything.

## Commands

```sh
.venv/bin/python -m worker --verbose build \
  --repo file:///absolute/path/to/content.git --ref main --slug my-blog \
  --subdir posts --title 'My blog' --author 'Writer' \
  --description 'Notes from my work' --target local
.venv/bin/python -m worker build \
  --repo file:///absolute/path/to/content.git --ref main --slug my-blog --json
.venv/bin/python -m worker serve --port 8787
.venv/bin/python -m worker rollback --slug my-blog --branch main --sha FULL_SHA
.venv/bin/python -m worker clean --older-than 24h
```

`--ref` accepts a branch, tag, or full commit SHA; default `main`. `--subdir`
defaults to `.`. Site metadata starts with the template's `blog.config.json` and
CLI flags override its title, author, and description. The target determines the
canonical URL. `--json` emits the complete build and deployment results to stdout;
verbose diagnostic logging goes to stderr. A failed build or deployment exits 1.
Human output includes stage durations and the last 40 lines of the failed log.
`clean` removes only directories bearing an old `.finished` marker, never active
builds. Duration syntax accepts combined integer `s`, `m`, `h`, and `d` units.

The local server runs in the foreground, binds 127.0.0.1, and handles SIGINT and
SIGTERM. Visit `http://localhost:8787/` for deployments, SHAs and publication times.
Main is `http://my-blog.localhost:8787`; staging is
`http://staging.my-blog.localhost:8787`. Other branch names are lowercased and each
character outside `[a-z0-9-]` becomes `-`, then edge hyphens are stripped.
`Feature/Test` becomes `feature-test`; `Release.V1` becomes `release-v1`.
Empty results (including `...`) are rejected. Slugs must be 1–58 lowercase
letters, digits or hyphens, with no edge hyphens. Both targets and the CLI validate
before work; branch sanitization can collide, so the API must enforce ownership.
Browsers resolve these names locally.
For command-line HTTP clients, connect to 127.0.0.1 with an explicit Host header.
There is no TLS or production authentication on this development server.

Local activation copies into a sibling directory then atomically exchanges the
old/new trees. Five previous deployments per branch are retained by SHA under
`SERVE_ROOT/<slug>/.history/<branch>/<sha>/`. Rollback exchanges directories without
rebuilding or copying. Deployments of the same SHA share one history key.

When exchange is unavailable, activation renames `live` to `.previous-<sha>`,
then `new` to `live`, then moves the previous tree into history. Between the first
two renames the live directory is absent: normally a sub-millisecond window,
not a timing guarantee under scheduling or filesystem stalls. Production uses
exchange to avoid this window. Failure of the second rename restores live.
A process crash in the gap can require operator recovery from `.previous-<sha>`;
that path is never overwritten automatically. `OCB_FORCE_RENAME_FALLBACK=1`
forces this path for tests. `doctor` prints the detected/forced activation mode.

## Environment

| Variable | Default | Meaning |
| --- | --- | --- |
| `TEMPLATE_DIR` | repository `web/` | Astro template, resolved independently of working directory |
| `BUILD_ROOT` | `/tmp/ocb-builds` | UUID directories containing content, config, logs, manifest and dist |
| `SERVE_ROOT` | `/tmp/ocb-serve` | Published sites and rollback history |
| `OCB_FORCE_RENAME_FALLBACK` | unset | Set `1` to force portable rename activation |
| `BUILD_TIMEOUT` | `300` | Positive seconds for the Astro subprocess; timeout kills its process group |
| `SERVE_PORT` | `8787` | Port used in generated site URLs; keep consistent with `serve --port` |
| `CLOUDFLARE_API_TOKEN` | absent | Token for the optional Cloudflare target |
| `CLOUDFLARE_ACCOUNT_ID` | absent | Account for the optional Cloudflare target |
| `OCB_E2E_ROOT` | fresh pytest temp directory | Optional **unused** root for one test run; logs and fixture repositories remain for inspection |

The worker supplies `CONTENT_DIR`, `BLOG_CONFIG`, `BUILD_OUT_DIR`,
`BUILD_CACHE_DIR=BUILD_ROOT/<build_id>/.astro`, and `SITE_URL` to Astro. Their
standalone defaults and relative-path behavior are in AGENTS.md. Builds use a
minimal PATH and private HOME. The installed Rolldown/Rayon native pool is capped
at two threads per build (`RAYON_NUM_THREADS=2`) to limit contention between
concurrent processes; this also applies to single-build baselines. Only dependency
installation holds the shared
lock under `/tmp/ocb-template-locks`; compilation runs concurrently.

Astro 7.2.10's `cacheDir` does not relocate generated types under `root/.astro`
or its working-directory prerender fallback. `pnpm build` therefore runs the
installed Astro JavaScript `build()` API in a private template workspace inside
the build cache, copies only first-party source/config/public files, and links
the installed dependencies. Vite's cache is explicitly per build. The workspace
is removed on normal completion/failure; timeout leftovers are collected by
`clean`. All of the installed template, including `node_modules`, remains
unchanged. CSS uses Astro's default externalization; prerender and output are on
the build filesystem, so cross-filesystem templates need no inline CSS workaround.

Only regular `.md` files enter the build. Symlinks, hidden paths, MDX and other
extensions are inventoried but excluded. Hidden directories are traversed only to
inventory their excluded files. Limits are 2 MiB/file, 500 files, and 20 MiB total;
exceeding any fails the entire fetch and removes partial content. One Git log
pass preserves first-add timestamps, including renames and Unicode filenames.
The disposable clone is deleted after successful sanitization. Build-time failures
retain logs; the pipeline retains a finished UUID directory with `pipeline.log`
for fetch failures, without the partial clone or content.

## Tests

From `worker/`:

```sh
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/pytest
.venv/bin/pytest -m e2e
.venv/bin/pytest -m e2e
.venv/bin/pytest -m e2e -k test_s9_rollback
```

Unit tests run without Node or network access. E2E tests require local sockets,
Git, the installed template and Chromium. Each run creates clean build/serve
roots, real bare repositories and pinned-date commits; executes the real CLI;
starts/stops its server and browser; and checks for leftover owned processes.
Tests never use Cloudflare. The pipeline cases include S4b and rollback under both activation modes, plus
four visual combinations (two sizes, two themes). The visual cases produce
36 incidental PNGs under the run's `screenshots/` directory and per-page
transfer/accessibility metrics in the run's root. Captures are not deliverables. Axe 4.13.0 is vendored with its license and injected locally.
The 404 design is captured via `/404.html` (HTTP 200); separate pipeline tests
require actual missing routes to return the branded page with HTTP 404. This
avoids counting Chromium's expected 404 navigation diagnostic as a console bug.
Every internal link is crawled; browser requests must stay on localhost and never
load fonts. All page variants check metadata, responsive width, persistent theme,
keyboard focus, zero serious/critical axe violations and transfer below 100,000 bytes.

### Local demonstration from a fresh checkout

After setup, create a fixture repository and publish it (all commands local):

```sh
mkdir -p /tmp/ocb-demo
cd /tmp/ocb-demo
git init --bare --initial-branch=main content.git
git clone file:///tmp/ocb-demo/content.git content
cd content
git config user.name 'Local Writer'
git config user.email writer@localhost
printf '%s\n' '---' 'title: Hello' 'description: A local example' '---' '' 'Hello from Markdown.' > hello.md
git add hello.md
GIT_AUTHOR_DATE=2024-01-01T12:00:00Z GIT_COMMITTER_DATE=2024-01-01T12:00:00Z git commit -m 'Add first post'
git push origin main
```

Return to the fresh checkout's `worker/` directory, then:

```sh
.venv/bin/python -m worker doctor
.venv/bin/python -m worker build --repo file:///tmp/ocb-demo/content.git --slug demo
.venv/bin/python -m worker serve
```

Visit `http://demo.localhost:8787/`, stop the server with Ctrl-C, and run
`.venv/bin/pytest -m e2e`. You can instead use the `remote.git` directory of any
E2E fixture left in a previous run's `repos/` directory. Choose unused paths for
repeated demonstrations or set fresh `BUILD_ROOT` and `SERVE_ROOT` values.

## Cloudflare target (future use)

In the Cloudflare dashboard, open your profile's API Tokens, create a custom
token scoped to the intended account with **Account / Cloudflare Pages / Edit**,
and obtain the account ID from the account dashboard. Export
`CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` privately; never put them in Git.
Then `build --target cloudflare` uses the exact pinned local Wrangler binary,
ensures the Pages project with production branch `main`, and uploads static dist.
Both commands have 300-second timeouts. Project names allow 1–58 lowercase letters,
digits or hyphens, with no edge hyphens. Already-existing projects are accepted.
Main aliases to `https://<slug>.pages.dev`; previews to
`https://<sanitized-branch>.<slug>.pages.dev`. Command output is redacted before
writing deploy.log. This target is tested with mocked subprocess results only.
The saved output fixture follows the completion strings in Wrangler 4.140.0's
installed source; the illustrative deployment identifiers are not a real upload.

## Python interfaces

`BuildRequest`, `ContentManifest`, `BuildResult`, and `DeployResult` are dataclasses
in `worker.models`. Call `fetch_content(request)`, then
`run_build(request, content_dir, target.site_url(slug, ref))`, then
`target.deploy(result.dist_dir, slug, ref, result.sha)` only on success.
`DeployTarget` is a structural protocol. Fetch errors raise `SourceError` carrying
an optional manifest; user compilation errors return failed/timeout results;
worker misconfiguration raises `BuildConfigurationError`. The CLI marks finished
build directories after deployment/failure for cleanup. A future queue should own
job state, cancellation, retries, concurrency limits and finished markers when
calling these interfaces directly. Authentication, webhooks and durable job/event
storage belong to the API/queue layer.

## API pipeline interface

```python
from worker.pipeline import run_pipeline
from worker.targets.local import LocalTarget

result = run_pipeline(request, LocalTarget(), on_event=record_progress)
```

`run_pipeline(request, target, on_event=None) -> PipelineResult` is the blocking
entry point for the API. It owns `site_url -> fetch -> build -> deploy` and writes
`.finished` on every terminal outcome, including fetch errors and timeouts.
The API should run it in a worker, not on its async event loop.

`PipelineResult` contains `status` (`success`, `failed`, `timeout`), `stages`,
`build`, `deploy`, `manifest`, `alias_url`, `error`, `site_url`, and `log_paths`.
Each stage has `name`, `status`, UTC ISO `started_at`/`ended_at`, and monotonic
`duration_seconds`. The callback receives an independent dictionary on start
(`running`, no end time) and finish. JSON CLI output serializes this result.
Fetch failures retain a failed `BuildResult` for CLI compatibility, with the
fetch manifest and error-log path. Unreached stages are absent.

User validation/fetch errors and build/deploy failures become results. Worker
misconfiguration (including `BuildConfigurationError`, target configuration, and
filesystem infrastructure failures) still raises; exceptions from the event
consumer also propagate. Callbacks should be quick and reliable. Job IDs must be
unique. Authentication, durable scheduling, retries, cancellation, ownership and
branch-collision policy remain API responsibilities.

# Phase 2 delivery report

## 1. Summary

The worker turns a Git ref into sanitized Markdown, a static Astro build, and an atomically published local site.
It supports branch previews, five-deployment history, rollback, diagnostics, cleanup, and a fully mocked Cloudflare target.
The final checks cover 37 worker unit tests, the existing API test, 13 publishing scenarios, and 36 browser screenshots.
Two consecutive clean E2E runs and an independent fresh-clone run prove the complete CLI pipeline.

## 2. What was built

| Part | Files and outcome |
| --- | --- |
| 1 — template | `web/astro.config.mjs`, `web/src/layouts/BaseLayout.astro`, `web/src/utils/posts-loader.ts`, `web/scripts/check-fixture-build.mjs`, `web/package.json`, `web/pnpm-lock.yaml`, `web/pnpm-workspace.yaml`: retained the four existing environment overrides, corrected canonical/OG URLs, supported output on another filesystem, enforced the exact TypeScript pin, and kept scrollable code keyboard-accessible. The fixture script checks temporary config/output and a Git-clean template. |
| 2 — fetch/build | `worker/worker/config.py`, `models.py`, `source.py`, `build.py`, `__init__.py`: full Git checkout, ref resolution, UUID isolation, safe Markdown copying, all three limits, exclusion manifests, one-pass first-add timestamps, clone disposal, minimal build environment, logs/reports, serialized template access and process-group timeout cleanup. |
| 3 — targets/server | `worker/worker/targets/{base,local,cloudflare,__init__}.py`, `worker/worker/serve.py`: target protocol, atomic activation and rollback, five previous SHAs, Pages command implementation, redaction, URL parsing, Host routing, MIME handling, branded 404, listing, no-store headers and signal shutdown. `worker/package.json`, `pnpm-lock.yaml`, `pnpm-workspace.yaml` isolate Wrangler. |
| 4 — CLI/docs | `worker/worker/cli.py`, `__main__.py`, `worker/README.md`, root `README.md`, `AGENTS.md`: doctor, build, JSON results, verbose logging, rollback, serve and clean; complete setup/env/host/token/interface documentation. |
| 5 — tests | `worker/pyproject.toml`, `worker/tests/unit/{test_source,test_targets,test_build_cli_serve}.py`, `worker/tests/e2e/{conftest,test_pipeline}.py`, `worker/tests/fixtures/wrangler-deploy-output.txt`: replaced the placeholder test with meaningful unit and CLI pipeline assertions. `.gitignore` excludes worker dependencies and temporary CI artifacts. |
| 6 — visual QA | `worker/tests/e2e/test_visual.py`, pinned `axe-core-4.13.0.min.js` and its licenses; `test-fixtures/sample-content/long-form.md` now includes headings/code while retaining the 3,000-word fixture count. `docs/qa/phase-2/` contains all 36 full-page screenshots, per-image verdicts, metrics and verification evidence. |
| 7 — CI | `.github/workflows/ci.yml`: `worker-e2e` on Python 3.14 / Node 22.12.0, local browser pipeline, relevant path filters, screenshot and build-log artifacts; YAML parsed successfully. |

## 3. Decisions

- Use the existing pytest infrastructure; keep E2E opt-in with `-m e2e`. Deselected unit tests in an E2E run are expected marker selection, not skipped tests.
- Resolve the default template relative to the installed source checkout so changing the shell directory cannot select another template.
- Use binary size limits: 2 MiB/file and 20 MiB total, plus 500 Markdown files. A limit failure removes the entire fetch directory and preserves an existing deployment.
- Inventory excluded files inside hidden directories without copying them. Never traverse symlink directories; omit Git's own `.git` internals from the user-content manifest.
- Parse a single NUL-delimited Git history stream, preserving Unicode, tabs and original dates through renames.
- Keep template caches ignored and serialize Astro builds using a lock keyed by the template's resolved path, outside the tracked template. Separate CLI requests still produce independent UUID outputs.
- Disable pnpm's automatic pre-script dependency installation. Explicit frozen-lockfile installation occurs only when dependencies are absent, under a separate installation lock.
- Use Linux `renameat2(RENAME_EXCHANGE)` for replacement and rollback, avoiding an interval in which the live directory is absent. The worker documents its Linux/glibc requirement.
- Include `_build-report.json` in determinism checks: it contains no build timestamp. No output files are excluded from hash comparison.
- Retain Astro's normal sitemap behavior: published routes are included; the error page is not an indexable content route.
- Capture the branded 404 through `/404.html` at HTTP 200 so Chromium's expected failed-navigation diagnostic is not mistaken for a JavaScript error. Separate tests require real missing paths to return the same branded page with HTTP 404.
- Add a local Alpine theme control to the plain server listing so it satisfies the same keyboard, persistence, accessibility and visual checks as the sites. No new UI framework or remote asset is used.
- Keep Cloudflare credentials optional for local doctor checks. Cloudflare construction fails fast when either credential is absent; all deployment subprocesses are mocked in tests.
- Save all CI build logs, a superset of failed-scenario logs, to make failures diagnosable without losing relevant output.
- Promote the tested feature branch directly to main as requested by the mission.
- Interpret the explicit final `push to main` requirement as authorization for the final Git push. All test Git remotes and browser sites remain local; dependency downloads use package registries.

## 4. Deviations

- The requested standalone AGENTS constraints commit already existed as `fc6ead9` when this work resumed. There was no pending constraints edit to commit again.
- The inherited checkout already used Astro 7.2.10, despite an old “Astro 6” repository description. Its version was preserved and the description corrected.
- `subprocess.Popen(..., start_new_session=True)` plus a bounded wait replaces `subprocess.run` for the Astro build. This gives the worker the process-group handle needed to terminate descendants on timeout. Commands still use argument lists and never `shell=True`.
- Astro 7.2.10 attempted a cross-filesystem CSS rename from `web/.astro` to `/tmp` and failed with `EXDEV`. The supported `build.inlineStylesheets: "always"` setting resolves this for the static template; no adapter or SSR mode was added.
- Used the installed Chromium 153.0.8010.52 through Python Playwright rather than downloading another browser from a non-registry host. README documents both the standard Playwright install and the system-browser fallback; CI includes the requested `playwright install --with-deps chromium` step.
- Wrangler's saved sample uses its installed source's exact completion-message format with illustrative deployment identifiers. It is not output from a real Cloudflare deployment. All requested deploy flags were confirmed in Wrangler 4.140.0 help.
- Wrangler's optional esbuild/workerd installation scripts are disabled: the local CLI and static Pages upload do not require running a local Worker engine. Wrangler and its prerelease Miniflare dependency have explicit release-age exceptions required by pnpm's current package policies.
- Standalone Astro verification sets `ASTRO_TELEMETRY_DISABLED=1`. Local socket/browser checks and the fixture script's Git subprocess needed host execution because the sandbox blocked them.

## 5. Dependencies added

| Dependency | Version | Justification |
| --- | --- | --- |
| Python Playwright | 1.63.0 | Automates the required local Chromium crawl, theme/keyboard assertions, transfer checks and screenshots. |
| axe-core, vendored with license | 4.13.0 | Provides offline accessibility checks without another integration package or remote script. |
| Wrangler, only worker npm devDependency | 4.140.0 | Implements and validates the requested future Cloudflare Pages target. |
| pyee, Playwright transitive | 13.0.1 | Supplies Playwright's event dispatch. |
| greenlet, Playwright transitive | 3.5.6 | Supports Playwright's synchronous Python API. |

Wrangler's full transitive dependency graph is recorded in `worker/pnpm-lock.yaml`.
Python runtime code adds no third-party dependency. Existing pytest and Ruff are retained.
TypeScript remains exactly 6.0.3. Validation used Python 3.14.7, Node 26.7.0, pnpm 11.7.0,
Git 2.55.0, pytest 9.1.1, and Ruff 0.16.8; the fresh install selected Ruff 0.16.9 and also passed.

## 6. Test matrix

Run these commands from `worker/`; each E2E invocation creates fresh roots unless an unused `OCB_E2E_ROOT` is supplied.

| Scenario | Assertions | Result | Exact isolated rerun |
| --- | --- | --- | --- |
| S1 | 12 posts, 10/2 pagination, exact tag sets, valid RSS with every declared URL resolving, sitemap routes, local canonical/OG URLs | PASS | `.venv/bin/pytest -m e2e tests/e2e/test_pipeline.py::test_s1_happy` |
| S2 | Main/staging isolation, 12/13 posts, merge/push/rebuild promotion equality | PASS | `.venv/bin/pytest -m e2e tests/e2e/test_pipeline.py::test_s2_promotion` |
| S3 | Exact fallback set, draft exclusion, Unicode URL, complete long-post text and code/headings | PASS | `.venv/bin/pytest -m e2e tests/e2e/test_pipeline.py::test_s3_edges` |
| S4 | Symlinks, hidden files, MDX, PNG and text excluded with exact manifest reasons | PASS | `.venv/bin/pytest -m e2e tests/e2e/test_pipeline.py::test_s4_hostile` |
| S4b | Oversize failure identifies file/limit, no deployment, previous site preserved | PASS | `.venv/bin/pytest -m e2e tests/e2e/test_pipeline.py::test_s4b_oversize` |
| S5 | Nested subdirectory content included, root Markdown excluded | PASS | `.venv/bin/pytest -m e2e tests/e2e/test_pipeline.py::test_s5_subdir` |
| S6 | Removed/renamed old URLs return branded 404; new URL, feed and sitemap correct | PASS | `.venv/bin/pytest -m e2e tests/e2e/test_pipeline.py::test_s6_removal` |
| S7 | Two distinct first-add timestamps persist after an unrelated commit | PASS | `.venv/bin/pytest -m e2e tests/e2e/test_pipeline.py::test_s7_dates` |
| S8 | Full SHA succeeds; invalid ref/repo fail cleanly without leftover build dirs; empty site succeeds | PASS | `.venv/bin/pytest -m e2e tests/e2e/test_pipeline.py::test_s8_refs` |
| S9 | Rollback restores A after B; unknown SHA fails | PASS | `.venv/bin/pytest -m e2e tests/e2e/test_pipeline.py::test_s9_rollback` |
| S10 | Simultaneous CLI builds produce independent outputs and leave tracked web files untouched | PASS | `.venv/bin/pytest -m e2e tests/e2e/test_pipeline.py::test_s10_concurrency` |
| S11 | One-second timeout returns exit 1/status timeout and leaves no matching Node/pnpm process | PASS | `.venv/bin/pytest -m e2e tests/e2e/test_pipeline.py::test_s11_timeout` |
| S12 | Same SHA and URL yield identical paths and hashes, including the report | PASS | `.venv/bin/pytest -m e2e tests/e2e/test_pipeline.py::test_s12_determinism` |
| Visual | 9 pages × 2 widths × 2 themes; metadata, no overflow/errors/failed/remote/font requests, persistent theme, focus ring, axe and transfer limit | PASS | `.venv/bin/pytest -m e2e tests/e2e/test_visual.py` |
| Worker unit | All content limits, path safety, history dates, build results/environment/install lock, timeout signals, routing, cleanup, targets and redaction | PASS, 37 | `.venv/bin/pytest` |

Every served-site scenario crawls internal links in Chromium and checks localhost-only requests and no webfonts. The session teardown asserts no live owned Node, pnpm or Chromium processes remain.

## 7. Visual QA

All images were inspected, including enlarged top and bottom sections of the long post.
The accessibility defect found and fixed was loss of keyboard access to scrollable code blocks after HTML sanitization; generated `pre` elements now receive safe `tabindex="0"`.
The server listing was given responsive wrapping and light/dark styling. Final captures have no serious/critical axe violations, console errors, failed requests, or document overflow.

Measured page transfers ranged from 60,934 to 82,922 bytes, below 200 KiB. Each screenshot below has a recorded SHA-256 and metrics in `visual-review.json`.

### s1-index

**1440px, light:** PASS — consistent cards, readable dates/tags and clear pagination; no overlap.

![s1-index, 1440px, light](screenshots/s1-index-1440-light.png)

**1440px, dark:** PASS — consistent cards, readable dates/tags and clear pagination; no overlap.

![s1-index, 1440px, dark](screenshots/s1-index-1440-dark.png)

**390px, light:** PASS — consistent cards, readable dates/tags and clear pagination; no overlap.

![s1-index, 390px, light](screenshots/s1-index-390-light.png)

**390px, dark:** PASS — consistent cards, readable dates/tags and clear pagination; no overlap.

![s1-index, 390px, dark](screenshots/s1-index-390-dark.png)

### s1-page2

**1440px, light:** PASS — two posts and previous-page navigation fit cleanly.

![s1-page2, 1440px, light](screenshots/s1-page2-1440-light.png)

**1440px, dark:** PASS — two posts and previous-page navigation fit cleanly.

![s1-page2, 1440px, dark](screenshots/s1-page2-1440-dark.png)

**390px, light:** PASS — two posts and previous-page navigation fit cleanly.

![s1-page2, 390px, light](screenshots/s1-page2-390-light.png)

**390px, dark:** PASS — two posts and previous-page navigation fit cleanly.

![s1-page2, 390px, dark](screenshots/s1-page2-390-dark.png)

### s1-post

**1440px, light:** PASS — comfortable prose width, clear title/date/tag hierarchy.

![s1-post, 1440px, light](screenshots/s1-post-1440-light.png)

**1440px, dark:** PASS — comfortable prose width, clear title/date/tag hierarchy.

![s1-post, 1440px, dark](screenshots/s1-post-1440-dark.png)

**390px, light:** PASS — comfortable prose width, clear title/date/tag hierarchy.

![s1-post, 390px, light](screenshots/s1-post-390-light.png)

**390px, dark:** PASS — comfortable prose width, clear title/date/tag hierarchy.

![s1-post, 390px, dark](screenshots/s1-post-390-dark.png)

### s1-tag

**1440px, light:** PASS — three correct entries with consistent spacing and tag treatment.

![s1-tag, 1440px, light](screenshots/s1-tag-1440-light.png)

**1440px, dark:** PASS — three correct entries with consistent spacing and tag treatment.

![s1-tag, 1440px, dark](screenshots/s1-tag-1440-dark.png)

**390px, light:** PASS — three correct entries with consistent spacing and tag treatment.

![s1-tag, 390px, light](screenshots/s1-tag-390-light.png)

**390px, dark:** PASS — three correct entries with consistent spacing and tag treatment.

![s1-tag, 390px, dark](screenshots/s1-tag-390-dark.png)

### s1-404

**1440px, light:** PASS — branded error page, readable message and obvious home link.

![s1-404, 1440px, light](screenshots/s1-404-1440-light.png)

**1440px, dark:** PASS — branded error page, readable message and obvious home link.

![s1-404, 1440px, dark](screenshots/s1-404-1440-dark.png)

**390px, light:** PASS — branded error page, readable message and obvious home link.

![s1-404, 390px, light](screenshots/s1-404-390-light.png)

**390px, dark:** PASS — branded error page, readable message and obvious home link.

![s1-404, 390px, dark](screenshots/s1-404-390-dark.png)

### s3-long

**1440px, light:** PASS — readable prose and headings; code scrolls within its own focusable block; footer intact.

![s3-long, 1440px, light](screenshots/s3-long-1440-light.png)

**1440px, dark:** PASS — readable prose and headings; code scrolls within its own focusable block; footer intact.

![s3-long, 1440px, dark](screenshots/s3-long-1440-dark.png)

**390px, light:** PASS — readable prose and headings; code scrolls within its own focusable block; footer intact.

![s3-long, 390px, light](screenshots/s3-long-390-light.png)

**390px, dark:** PASS — readable prose and headings; code scrolls within its own focusable block; footer intact.

![s3-long, 390px, dark](screenshots/s3-long-390-dark.png)

### s3-unicode

**1440px, light:** PASS — accented title and inline slug render correctly without clipping.

![s3-unicode, 1440px, light](screenshots/s3-unicode-1440-light.png)

**1440px, dark:** PASS — accented title and inline slug render correctly without clipping.

![s3-unicode, 1440px, dark](screenshots/s3-unicode-1440-dark.png)

**390px, light:** PASS — accented title and inline slug render correctly without clipping.

![s3-unicode, 390px, light](screenshots/s3-unicode-390-light.png)

**390px, dark:** PASS — accented title and inline slug render correctly without clipping.

![s3-unicode, 390px, dark](screenshots/s3-unicode-390-dark.png)

### s8-empty

**1440px, light:** PASS — clear empty state with balanced spacing and readable contrast.

![s8-empty, 1440px, light](screenshots/s8-empty-1440-light.png)

**1440px, dark:** PASS — clear empty state with balanced spacing and readable contrast.

![s8-empty, 1440px, dark](screenshots/s8-empty-1440-dark.png)

**390px, light:** PASS — clear empty state with balanced spacing and readable contrast.

![s8-empty, 390px, light](screenshots/s8-empty-390-light.png)

**390px, dark:** PASS — clear empty state with balanced spacing and readable contrast.

![s8-empty, 390px, dark](screenshots/s8-empty-390-dark.png)

### serve-listing

**1440px, light:** PASS — deployment links, full SHAs and timestamps wrap cleanly with no overflow.

![serve-listing, 1440px, light](screenshots/serve-listing-1440-light.png)

**1440px, dark:** PASS — deployment links, full SHAs and timestamps wrap cleanly with no overflow.

![serve-listing, 1440px, dark](screenshots/serve-listing-1440-dark.png)

**390px, light:** PASS — deployment links, full SHAs and timestamps wrap cleanly with no overflow.

![serve-listing, 390px, light](screenshots/serve-listing-390-light.png)

**390px, dark:** PASS — deployment links, full SHAs and timestamps wrap cleanly with no overflow.

![serve-listing, 390px, dark](screenshots/serve-listing-390-dark.png)

## 8. Final verification output

Standalone web commands used `ASTRO_TELEMETRY_DISABLED=1`. Commands ran from their respective project directories. The following are tails from the final recorded logs.

### web: pnpm check

```text
14:10:36 [check] Getting diagnostics for Astro files in /home/puppet-master/Projects/open.content.blogs/web...
Result (18 files): 
- 0 errors
- 0 warnings
- 0 hints

```

### web: pnpm format:check

```text
$ prettier --check .
Checking formatting...
All matched files use Prettier code style!
```

### web: pnpm build

```text
14:10:42 [build] ✓ Completed in 393ms.
14:10:42 [@astrojs/sitemap] `sitemap-index.xml` created at `dist`
14:10:42 [build] 2 page(s) built in 877ms
14:10:42 [build] Complete!
```

### web: pnpm test:fixtures

```text
Fixture build passed: external config and output, clean web/, 7 published posts, RSS, and dynamic sitemap routes.
    }
  ],
  "skipped": []
}
```

### api: .venv/bin/ruff check .

```text
All checks passed!
```

### api: .venv/bin/ruff format --check .

```text
2 files already formatted
```

### api: .venv/bin/pytest

```text
tests/test_smoke.py .                                                    [100%]

============================== 1 passed in 0.29s ===============================
```

### worker: .venv/bin/ruff check .

```text
All checks passed!
```

### worker: .venv/bin/ruff format --check .

```text
19 files already formatted
```

### worker: .venv/bin/pytest

```text
tests/unit/test_targets.py ..................                            [100%]

====================== 37 passed, 17 deselected in 1.00s =======================
```

### worker: OCB_E2E_ROOT=/tmp/ocb-release-run-1 .venv/bin/pytest -m e2e -v

```text

tests/e2e/test_pipeline.py::test_s1_happy PASSED                         [  5%]
tests/e2e/test_pipeline.py::test_s2_promotion PASSED                     [ 11%]
tests/e2e/test_pipeline.py::test_s3_edges PASSED                         [ 17%]
tests/e2e/test_pipeline.py::test_s4_hostile PASSED                       [ 23%]
tests/e2e/test_pipeline.py::test_s4b_oversize PASSED                     [ 29%]
tests/e2e/test_pipeline.py::test_s5_subdir PASSED                        [ 35%]
tests/e2e/test_pipeline.py::test_s6_removal PASSED                       [ 41%]
tests/e2e/test_pipeline.py::test_s7_dates PASSED                         [ 47%]
tests/e2e/test_pipeline.py::test_s8_refs PASSED                          [ 52%]
tests/e2e/test_pipeline.py::test_s9_rollback PASSED                      [ 58%]
tests/e2e/test_pipeline.py::test_s10_concurrency PASSED                  [ 64%]
tests/e2e/test_pipeline.py::test_s11_timeout PASSED                      [ 70%]
tests/e2e/test_pipeline.py::test_s12_determinism PASSED                  [ 76%]
tests/e2e/test_visual.py::test_visual[1440-900-light] PASSED             [ 82%]
tests/e2e/test_visual.py::test_visual[1440-900-dark] PASSED              [ 88%]
tests/e2e/test_visual.py::test_visual[390-844-light] PASSED              [ 94%]
tests/e2e/test_visual.py::test_visual[390-844-dark] PASSED               [100%]

================ 17 passed, 37 deselected in 279.12s (0:04:39) =================
```

### worker: OCB_E2E_ROOT=/tmp/ocb-release-run-2 .venv/bin/pytest -m e2e -v

```text

tests/e2e/test_pipeline.py::test_s1_happy PASSED                         [  5%]
tests/e2e/test_pipeline.py::test_s2_promotion PASSED                     [ 11%]
tests/e2e/test_pipeline.py::test_s3_edges PASSED                         [ 17%]
tests/e2e/test_pipeline.py::test_s4_hostile PASSED                       [ 23%]
tests/e2e/test_pipeline.py::test_s4b_oversize PASSED                     [ 29%]
tests/e2e/test_pipeline.py::test_s5_subdir PASSED                        [ 35%]
tests/e2e/test_pipeline.py::test_s6_removal PASSED                       [ 41%]
tests/e2e/test_pipeline.py::test_s7_dates PASSED                         [ 47%]
tests/e2e/test_pipeline.py::test_s8_refs PASSED                          [ 52%]
tests/e2e/test_pipeline.py::test_s9_rollback PASSED                      [ 58%]
tests/e2e/test_pipeline.py::test_s10_concurrency PASSED                  [ 64%]
tests/e2e/test_pipeline.py::test_s11_timeout PASSED                      [ 70%]
tests/e2e/test_pipeline.py::test_s12_determinism PASSED                  [ 76%]
tests/e2e/test_visual.py::test_visual[1440-900-light] PASSED             [ 82%]
tests/e2e/test_visual.py::test_visual[1440-900-dark] PASSED              [ 88%]
tests/e2e/test_visual.py::test_visual[390-844-light] PASSED              [ 94%]
tests/e2e/test_visual.py::test_visual[390-844-dark] PASSED               [100%]

================ 17 passed, 37 deselected in 268.79s (0:04:28) =================
```

### CI YAML parser

```text
CI YAML parses; worker-e2e job present
```

### Fresh clone: git clone --no-hardlinks file:///home/puppet-master/Projects/open.content.blogs /tmp/ocb-fresh-final

```text
Cloning into '/tmp/ocb-fresh-final'...
```

### Fresh clone web: pnpm install --frozen-lockfile

```text
+ prettier-plugin-astro 1.0.1
+ typescript 6.0.3

Done in 1.2s using pnpm v11.7.0
```

### Fresh clone worker: pnpm install --frozen-lockfile

```text
devDependencies:
+ wrangler 4.140.0

Done in 741ms using pnpm v11.7.0
```

### Fresh clone worker: .venv/bin/python -m pip install --group dev

```text
Installing collected packages: typing-extensions, ruff, pygments, pluggy, packaging, iniconfig, greenlet, pytest, pyee, playwright

Successfully installed greenlet-3.5.6 iniconfig-2.3.0 packaging-26.3 playwright-1.63.0 pluggy-1.6.0 pyee-13.0.1 pygments-2.21.0 pytest-9.1.1 ruff-0.16.9 typing-extensions-4.16.0
```

### Fresh clone worker: .venv/bin/python -m worker doctor

```text
CLOUDFLARE_API_TOKEN: MISSING
CLOUDFLARE_ACCOUNT_ID: MISSING
OK git: git version 2.55.0
OK node >=22.12: v26.7.0
OK pnpm: 11.7.0
OK wrangler: 4.140.0
OK TEMPLATE_DIR: /tmp/ocb-fresh-final/web
OK template node_modules: present
OK BUILD_ROOT: /tmp/ocb-fresh-final-demo-builds (writable)
OK SERVE_ROOT: /tmp/ocb-fresh-final-demo-serve (writable)
OK Playwright Chromium: /usr/bin/chromium
```

### Fresh clone worker: .venv/bin/python -m worker build --repo file:///tmp/ocb-debug-4/repos/happy-1/remote.git --slug fresh-demo

```text
fetch success (0.027s, e685f02d082a957e81effdaddd231b2e9b18484d)
build success (2.622s)
deploy success (0.003s)
http://fresh-demo.localhost:18878
```

### Fresh clone worker: .venv/bin/python -m worker serve --port 18878, HTTP assertions, SIGINT

```text
Fresh-clone serve: HTTP 200, 10 posts on page 1, Cache-Control no-store
Fresh-clone listing: HTTP 200, fresh-demo/main present
SIGINT: clean exit 0
```

### Fresh clone worker: .venv/bin/ruff check .

```text
All checks passed!
```

### Fresh clone worker: .venv/bin/ruff format --check .

```text
19 files already formatted
```

### Fresh clone worker: .venv/bin/pytest

```text
tests/unit/test_targets.py ..................                            [100%]

====================== 37 passed, 17 deselected in 1.29s =======================
```

### Fresh clone worker: OCB_E2E_ROOT=/tmp/ocb-fresh-final-e2e .venv/bin/pytest -m e2e -v

```text
tests/e2e/test_visual.py::test_visual[1440-900-dark] PASSED              [ 88%]
tests/e2e/test_visual.py::test_visual[390-844-light] PASSED              [ 94%]
tests/e2e/test_visual.py::test_visual[390-844-dark] PASSED               [100%]

================ 17 passed, 37 deselected in 278.31s (0:04:38) =================
```

### Final template/process checks

```text
open.content.blogs: git status --porcelain web/ -> empty
ocb-fresh-final: git status --porcelain web/ -> empty
Live owned Node/pnpm/Chromium processes: 0
Screenshot inventory: 36/36 exact expected filenames
```

Self-review: reread the original mission and each test; checked all Parts 1–7 and Definition of Done items against code and evidence. Scanned the owned diff for TODO, FIXME, skip, xfail, pytest.mark.skip, type-ignore and broad swallowed exceptions. Only domain-level `skipped` manifest fields and the instruction forbidding skipped tests matched. Vendored axe source/license were treated as third-party assets. No tests were skipped, weakened or xfailed. Tracked template status is empty, and process scans found no live owned Node/pnpm/Chromium processes.

The evidence and screenshot set are committed before final promotion; the delivery message records the final main commit and push result.

## 9. Known issues

No requested local check remains failing. Cloudflare deployment was deliberately not executed; its subprocess behavior is unit-tested. The new hosted CI job was validated as YAML and exercised through its local equivalents, without querying a hosted run. Atomic local activation requires Linux/glibc, as documented.

## 10. Inputs for Phase 3

Public dataclasses in `worker.models`:

| Interface | Fields |
| --- | --- |
| `BuildRequest` | `repo_url: str`, `slug: str`, `ref: str = "main"`, `content_subdir: str = "."`, `site_config: dict`, `build_id: UUID` (generated by default), `target: "local" or "cloudflare"` |
| `ContentManifest` | `sha: str`, `files: list[str]`, `skipped: list[{path, reason}]` |
| `BuildResult` | `status: success/failed/timeout`, `sha`, `dist_dir`, `log_path`, `report`, `manifest`, `duration_seconds`, `error` |
| `DeployResult` | `status: success/failed`, `deployment_url`, `alias_url`, `log_path`, `error` |

Synchronous entry points:

```python
content_dir, manifest = fetch_content(request)
site_url = target.site_url(request.slug, request.ref)
build_result = run_build(request, content_dir, site_url)
if build_result.status == "success":
    deploy_result = target.deploy(
        build_result.dist_dir, request.slug, request.ref, build_result.sha
    )
```

`DeployTarget` structurally requires `site_url(slug, branch) -> str` and
`deploy(dist_dir, slug, branch, sha) -> DeployResult`. `LocalTarget` additionally
exposes `rollback(slug, branch, sha) -> Path`.

Fetch errors raise `SourceError` with an optional manifest. User compilation failures
return failed/timeout results with logs. Worker configuration errors raise
`BuildConfigurationError`; missing Cloudflare setup raises
`CloudflareConfigurationError`. The API should map these deliberately to job status.

Phase 3 still needs authentication/slug ownership, webhook validation, a durable job
and deployment store, retry/idempotency policy, queue-level concurrency and deadlines,
progress events/log retrieval, cancellation, and production isolation/resource controls.
The public functions are blocking. The CLI owns `.finished` markers today; direct API
callers must mark completion after deployment/failure before cleanup can collect a job.
Git-fetch cancellation/deadlines and typed validation of site_config are not separate
public interfaces yet. Branch sanitization can produce collisions, so ownership and
branch naming policy should be enforced when registering API jobs.

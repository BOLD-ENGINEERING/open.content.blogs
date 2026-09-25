# Phase 2 hardening report

## 1. Summary

A–E are implemented: isolated concurrent builds, shared name validation, portable
activation, a single pipeline API, and one centered reading column. No dependency
was added or upgraded. All verification is local, except permitted package-registry
installs into fresh virtual environments. Cloudflare remains mocked and unexecuted.

## 2. What was built

- `BUILD_CACHE_DIR` drives Astro's `cacheDir`, the content report, Vite cache and
  a disposable template workspace. The worker sets `BUILD_ROOT/<build_id>/.astro`.
  The build lock is removed; dependency installation retains its lock.
- CSS uses Astro defaults again. Builds from a different template filesystem
  succeed with external CSS, without an inline-stylesheet override.
- `worker.naming` validates Pages-compatible slugs and sanitizes branch names.
  The CLI rejects invalid slugs before settings/config reads or cloning; both
  targets validate their public operations.
- Activation detects directory exchange on first use per filesystem. Forced or
  unsupported environments use recoverable rename activation. Doctor prints mode.
- `worker.pipeline.run_pipeline` owns stages, events, results, logs and terminal
  markers. The CLI only creates requests, selects targets and presents results.
- Header, footer, index/tag/empty-state content and posts share a centered 44rem
  (704px) shell with existing responsive gutters and tokens.

## 3. Decisions

1. Installed Astro 7.2.10 supports `cacheDir`, but `core/config/settings.js` still
   fixes generated types at `root/.astro`. Its `core/build/common.js` falls back
   to `cwd/.astro` for external output; `prerender/utils.js` puts `.prerender`
   there, and `static-build.js` renames CSS from that tree into output. Merely
   changing `cacheDir` would leave shared writes and the cross-device rename.
   `scripts/build.mjs` uses the installed `astro.build({root})` API with a private
   first-party template copy and a symlink to installed dependencies. No package
   internals are patched. Worker cache/workspace and output share a filesystem.
2. The private workspace is removed after normal completion or build failure.
   A timeout still kills the entire process group; `clean` can later remove the
   finished build directory, including interrupted workspace leftovers.
3. Center the entire 704px shell. It preserves the established post reading width
   while aligning all page types, navigation and footer. Text remains left-aligned.
4. Branches are lowercased, each non-`[a-z0-9-]` character becomes `-`, and edge
   hyphens are stripped: `Feature/Test` -> `feature-test`, `Release.V1` ->
   `release-v1`. Empty results are rejected. Collision policy belongs to the API.
5. UTC ISO timestamps make independent CLI intervals comparable; durations use
   monotonic clocks. Each event is copied before delivery to the consumer.
6. Pipeline fetch failures retain a log and `.finished` marker after the source
   helper removes partial content. A synthetic failed `BuildResult` preserves
   the existing CLI error shape; no build stage is recorded when compilation
   was not reached. Unreached stages are absent from the result.
7. Native exchange remains the production path. Fallback moves live to
   `.previous-<sha>` and then new to live. The absent-live window is normally
   sub-millisecond, but scheduling and filesystem stalls preclude a guarantee.
   Failure of the second rename restores live. A process crash may require
   manual recovery from the retained previous directory.
8. Keep visual captures only inside each disposable test-run root. Record metrics
   here, with no screenshot deliverables. Use a decimal 100,000-byte budget,
   stricter than 100 KiB, because every measured page fits.
9. An initial fresh-clone S10 missed the unchanged wall-time limit: 4.659344s
   versus 4.598294s. All intervals overlapped and the other 17 cases passed.
   The installed Rolldown 1.2.6 native binary includes Rayon and supports
   `RAYON_NUM_THREADS`; cap it at two threads per worker build to bound native
   pool contention. Serial baselines use the same cap and fixtures. A focused
   check passed at 3.880296s against 5.586497s, followed by complete verification
   of the final implementation. The failed initial run remains in
   `verification/initial-fresh-e2e.log`; the assertion was not changed.
10. The origin is SSH on github.com. The brief's explicit prohibition on all
   external-service connections takes precedence over its push checklist item.
   Complete and commit locally; do not contact GitHub for a push, PR or CI query.

## 4. Deviations

- Astro needs a private template root/cwd in addition to its cache configuration;
  the installed implementation and unchanged-template snapshot justify this.
- S8's old assertion that failed fetches leave no UUID directory conflicts with
  the new required terminal marker. It now requires exactly one finished error
  directory per failure, a readable error log, and no partial clone. This replaces
  an obsolete expectation with assertions for the requested retention contract.
- The CLI E2E tests otherwise retain their prior assertions and gain the requested
  S8/S9/S10 checks. No test was skipped, xfailed or relaxed to conceal a failure.
- Remote push and hosted verification are not performed under the local-only rule.

## 5. Dependencies added

None. Astro 7.2.10, TypeScript 6.0.3, pnpm 11.7.0, Node 26.7.0, Python 3.14.7,
Playwright 1.63.0 and Wrangler 4.140.0 were verified locally. Existing manifests
and lockfiles determine fresh installs. New implementation uses existing Astro
and Python/Node standard-library APIs. The site remains static; no SSR adapter,
user MDX, UI framework or Tailwind was introduced.

## 6. Test matrix

| Area | Coverage | Result |
| --- | --- | --- |
| Web | check, format:check, build, test:fixtures | PASS |
| API | Ruff, format check, pytest | PASS; 1 test |
| Worker | Ruff, format check, pytest | PASS; 70 unit tests |
| S1–S7, S4b | publishing, promotion, edge/hostile/oversize content, subdirs, removal, dates | PASS |
| S8 | SHA/ref/repo errors, terminal logs, empty site, invalid slug and root-parent snapshots | PASS |
| S9 | rollback and unknown SHA under native exchange and forced fallback | PASS |
| S10 | three isolated outputs, simultaneous build intervals, wall < 2x single median, full template snapshot | PASS |
| S11–S12 | process-group timeout cleanup and byte-identical repeat builds | PASS |
| Visual | 9 pages x 2 widths x 2 themes; aligned shell, no overflow, metadata, focus, themes, axe, local-only requests | PASS |
| Fresh clone | local clone, independent installs/venvs, doctor, web/API/worker checks, CLI build/HTTP/SIGINT and full E2E | PASS; 18 E2E tests |

Unit coverage includes every pipeline terminal path with mocked fetch/build/deploy,
configuration exceptions, event pairs, completion markers, every requested invalid
slug, branch transformations, unsupported libc/filesystem detection, and fallback
restoration after activation failure. Native-path unit dispatch is simulated so
unit tests do not require Linux; E2E exercises the actual host exchange syscall.

## 7. Visual QA

The suite tests widths 1440 and 390 in light and dark themes. Header/main/footer
bounding boxes must share left edge and width, the shell must be at most 720px,
and the first content column must share that edge. Existing overflow, accessibility,
keyboard focus, theme persistence, local-only/no-font requests and console checks
remain. There are no images or per-screenshot verdicts in this report.

## 8. Final verification output

All commands ran from their respective subproject directory. Web commands set
`ASTRO_TELEMETRY_DISABLED=1`. Full text logs are in `verification/`; trailing whitespace is normalized for Git.

### Build isolation and filesystems

`stat -c '%d %n' /tmp web` returned device **57** for `/tmp` and **56** for
`web/`. Worker builds used `/tmp` build roots and the repository's template on
56. External `_astro/*.css` assets were produced successfully; no EXDEV failure
occurred. The previous unconditional inline-stylesheet setting is absent.

Snapshots include every recursive path under web, including hidden files,
node_modules, directories and symlinks: path, lstat size, nanosecond mtime,
SHA-256 for regular files, and symlink target. No paths are excluded.

Run 1 snapshot diff:

```json
{
  "entries": 17304,
  "changes": {}
}
```

Run 2 snapshot diff:

```json
{
  "entries": 17304,
  "changes": {}
}
```

Fresh clone snapshot diff:

```json
{
  "entries": 17266,
  "changes": {}
}
```

### Three-build overlap

| Run | Single-build median (s) | Concurrent wall (s) | Limit: 2x median (s) | Result |
| --- | ---: | ---: | ---: | --- |
| Run 1 | 2.664641 | 3.659089 | 5.329283 | PASS |
| Run 2 | 2.807440 | 4.123271 | 5.614879 | PASS |
| Fresh clone | 2.354763 | 3.500369 | 4.709526 | PASS |

Each run asserts `max(started_at) < min(ended_at)`, so all three intervals share
a common overlap, and separately asserts the wall-time bound. Serial baselines
use the same three repositories and full CLI pipeline in the same run.

| Build | Started (UTC) | Ended (UTC) | Duration (s) |
| --- | --- | --- | ---: |
| Run 1, 1 | 2026-09-25T15:13:29.053098+00:00 | 2026-09-25T15:13:32.480612+00:00 | 3.427522 |
| Run 1, 2 | 2026-09-25T15:13:29.053310+00:00 | 2026-09-25T15:13:32.430767+00:00 | 3.377468 |
| Run 1, 3 | 2026-09-25T15:13:29.052171+00:00 | 2026-09-25T15:13:32.581163+00:00 | 3.529002 |
| Run 2, 1 | 2026-09-25T15:19:37.423437+00:00 | 2026-09-25T15:19:41.372033+00:00 | 3.948645 |
| Run 2, 2 | 2026-09-25T15:19:37.423633+00:00 | 2026-09-25T15:19:41.269576+00:00 | 3.845950 |
| Run 2, 3 | 2026-09-25T15:19:37.423613+00:00 | 2026-09-25T15:19:41.312542+00:00 | 3.888939 |
| Fresh clone, 1 | 2026-09-25T15:16:52.965912+00:00 | 2026-09-25T15:16:56.291853+00:00 | 3.325947 |
| Fresh clone, 2 | 2026-09-25T15:16:52.969049+00:00 | 2026-09-25T15:16:56.294965+00:00 | 3.325927 |
| Fresh clone, 3 | 2026-09-25T15:16:52.965878+00:00 | 2026-09-25T15:16:56.193335+00:00 | 3.227468 |

### Per-page transfer sizes

Bytes include navigation and resource transfers on a fresh browser context.
Before is the accepted Phase 2 `visual-review.json`; after is the second complete
hardening run. All four viewport/theme
variants are included as ranges if different.

| Page | Before (bytes) | After (bytes) | Change |
| --- | ---: | ---: | ---: |
| s1-index | 65,686 | 66,053 | +367 |
| s1-page2 | 63,283 | 63,650 | +367 |
| s1-post | 62,884 | 63,251 | +367 |
| s1-tag | 63,471 | 63,838 | +367 |
| s1-404 | 62,593 | 62,960 | +367 |
| s3-long | 82,922 | 83,289 | +367 |
| s3-unicode | 62,742 | 63,109 | +367 |
| s8-empty | 62,472 | 62,839 | +367 |
| serve-listing | 60,934 | 61,618 | +684 |

External CSS adds a request and slightly increases first-page transfer versus
inlining; it can be cached separately for navigation. The listing also includes
additional baseline/concurrency deployments, so its content differs. The maximum
remains below 100,000 bytes; every visual case enforces that new budget.

### Activation modes

Doctor reports `rename-exchange` on this host. Each E2E run executes S9 once with
normal detection and once with `OCB_FORCE_RENAME_FALLBACK=1`. Both pass. The
forced doctor output is also retained. Production should use the exchange mode.

### Required command results

[web-check.log](verification/web-check.log)

```text
Result (19 files):
- 0 errors
- 0 warnings
- 0 hints

```

[web-format.log](verification/web-format.log)

```text
$ prettier --check .
Checking formatting...
All matched files use Prettier code style!
```

[web-build.log](verification/web-build.log)

```text

14:59:36 [build] ✓ Completed in 406ms.
14:59:36 [@astrojs/sitemap] `sitemap-index.xml` created at `../../dist`
14:59:36 [build] 2 page(s) built in 985ms
14:59:36 [build] Complete!
```

[web-fixtures.log](verification/web-fixtures.log)

```text
Fixture build passed: external config and output, clean web/, 7 published posts, RSS, and dynamic sitemap routes.
```

[api-ruff.log](verification/api-ruff.log)

```text
All checks passed!
```

[api-format.log](verification/api-format.log)

```text
2 files already formatted
```

[api-unit.log](verification/api-unit.log)

```text
collected 1 item

tests/test_smoke.py .                                                    [100%]

============================== 1 passed in 0.31s ===============================
```

[worker-ruff.log](verification/worker-ruff.log)

```text
All checks passed!
```

[worker-format.log](verification/worker-format.log)

```text
23 files already formatted
```

[worker-unit.log](verification/worker-unit.log)

```text
tests/unit/test_pipeline_runner.py .........                             [ 60%]
tests/unit/test_source.py ..........                                     [ 74%]
tests/unit/test_targets.py ..................                            [100%]

====================== 70 passed, 18 deselected in 1.13s =======================
```

[e2e-1.log](verification/e2e-1.log)

```text
tests/e2e/test_visual.py::test_visual[1440-900-dark] PASSED              [ 88%]
tests/e2e/test_visual.py::test_visual[390-844-light] PASSED              [ 94%]
tests/e2e/test_visual.py::test_visual[390-844-dark] PASSED               [100%]

================ 18 passed, 70 deselected in 296.22s (0:04:56) =================
```

[e2e-2.log](verification/e2e-2.log)

```text
tests/e2e/test_visual.py::test_visual[1440-900-dark] PASSED              [ 88%]
tests/e2e/test_visual.py::test_visual[390-844-light] PASSED              [ 94%]
tests/e2e/test_visual.py::test_visual[390-844-dark] PASSED               [100%]

================ 18 passed, 70 deselected in 303.82s (0:05:03) =================
```

[fresh-web-check.log](verification/fresh-web-check.log)

```text
Result (19 files):
- 0 errors
- 0 warnings
- 0 hints

```

[fresh-web-format.log](verification/fresh-web-format.log)

```text
$ prettier --check .
Checking formatting...
All matched files use Prettier code style!
```

[fresh-web-build.log](verification/fresh-web-build.log)

```text

15:13:20 [build] ✓ Completed in 583ms.
15:13:20 [@astrojs/sitemap] `sitemap-index.xml` created at `../../dist`
15:13:20 [build] 2 page(s) built in 1.21s
15:13:20 [build] Complete!
```

[fresh-web-fixtures.log](verification/fresh-web-fixtures.log)

```text
Fixture build passed: external config and output, clean web/, 7 published posts, RSS, and dynamic sitemap routes.
```

[fresh-api-ruff.log](verification/fresh-api-ruff.log)

```text
All checks passed!
```

[fresh-api-unit.log](verification/fresh-api-unit.log)

```text
collected 1 item

tests/test_smoke.py .                                                    [100%]

============================== 1 passed in 0.37s ===============================
```

[fresh-worker-ruff.log](verification/fresh-worker-ruff.log)

```text
All checks passed!
```

[fresh-worker-unit.log](verification/fresh-worker-unit.log)

```text
tests/unit/test_pipeline_runner.py .........                             [ 60%]
tests/unit/test_source.py ..........                                     [ 74%]
tests/unit/test_targets.py ..................                            [100%]

====================== 70 passed, 18 deselected in 1.32s =======================
```

[fresh-e2e.log](verification/fresh-e2e.log)

```text
tests/e2e/test_visual.py::test_visual[1440-900-dark] PASSED              [ 88%]
tests/e2e/test_visual.py::test_visual[390-844-light] PASSED              [ 94%]
tests/e2e/test_visual.py::test_visual[390-844-dark] PASSED               [100%]

================ 18 passed, 70 deselected in 300.30s (0:05:00) =================
```

[fresh-smoke.log](verification/fresh-smoke.log)

```text
Fresh-clone pipeline: success http://fresh-demo.localhost:43413
Fresh-clone HTTP: 200, 10 post cards, Cache-Control no-store
Fresh-clone listing: deployment present
Fresh-clone SIGINT: clean exit 0
```

Fresh clone: `/tmp/ocb-hardening-fresh-final`, cloned via `file://` from source commit
`6e0e373`. Node dependencies used `pnpm install --offline --frozen-lockfile`.
API and worker each created their own Python 3.14 venv and installed declared
dependencies. Doctor, the explicit demo and full E2E use local Git/HTTP only.
The demo verified 10 post cards, HTTP 200, `Cache-Control: no-store`, listing
routing with the correct localhost Host header, and exit 0 after SIGINT.

The initial sandbox prevented a fixture check's child Git process; rerunning
with local host permissions passed. An initial ad hoc fresh-demo listing request
used an IP Host header and correctly received 404; using the documented localhost
Host header passed. Neither required weakening a test or a product change.

### Final state

Template and process checks are recorded in `verification/final-state.log`.
Local main promotion and the final clean tree are verified after committing
the evidence. Each E2E teardown independently asserts no live
owned Node, pnpm or Chromium processes. Existing Phase 2 screenshots are unchanged.
Self-review found no new skip/xfail, hidden assertion relaxation, dependency change,
secret file, inline CSS override, shared build lock or external deployment.

## 9. Known issues

The remote push is outstanding: it would connect to github.com, forbidden by
this mission. Hosted CI was not queried. No local test remains intentionally
failing. Fallback activation has the documented absence/crash window; production
uses native exchange. Branch sanitization collisions require API ownership policy.
Direct standalone external-output builds should put `BUILD_CACHE_DIR` on the
same filesystem as `BUILD_OUT_DIR`; the worker always does this. External-service
behavior remains mocked, not production-certified.

## 10. Inputs for Phase 3

```python
from worker.models import BuildRequest
from worker.pipeline import run_pipeline
from worker.targets.local import LocalTarget

result = run_pipeline(request, LocalTarget(), on_event=record_progress)
```

This is the single blocking publishing entry point the API should call in its
worker execution context. Do not reproduce the stage sequence or completion-marker
logic in the API.

| PipelineResult field | Contract |
| --- | --- |
| `status` | `success`, `failed`, or `timeout` |
| `stages` | Ordered `{name, status, started_at, ended_at, duration_seconds}` dictionaries |
| `build` | `BuildResult` or `None`; fetch failures retain a compatibility failure result |
| `deploy` | `DeployResult` or `None` |
| `manifest` | Sanitized content manifest, or partial manifest from a fetch failure |
| `alias_url` | Successful deployment alias, otherwise `None` |
| `error` | User-caused validation/fetch/build/deploy failure detail |
| `site_url` | Target URL resolved before fetching |
| `log_paths` | Available build/deploy/pipeline log locations |

The callback receives independent dictionaries on each stage start (`running`,
`ended_at=None`) and finish. Results retain timestamps and monotonic durations.
The pipeline writes `.finished` on success, compilation failure, timeout, fetch
error and exceptions after entry; cleanup can therefore safely collect completed
jobs. Invalid CLI slugs exit before any filesystem work. API callers receive a
failed result and a finished job directory for invalid names.

User failures become results. Worker/target misconfiguration and infrastructure
errors still raise. Callbacks should not raise; reliable, fast progress handling
is the caller's responsibility. Public `BuildRequest`, `BuildResult`, `DeployResult`, `ContentManifest`
and structural `DeployTarget` remain available. Job IDs must be unique. The API
still needs authentication, slug ownership, durable jobs, scheduling, retries,
cancellation, log access and branch-collision policy.

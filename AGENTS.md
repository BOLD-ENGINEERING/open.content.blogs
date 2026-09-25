# AGENTS.md - Instructions for Coding Agents

## Repository Overview

Monorepo containing a developer-first blogging platform with:
- `web/` - Astro 7 frontend (TypeScript)
- `api/` - FastAPI backend (Python 3.14)
- `worker/` - Git-to-static-site worker, local serving and deployment targets

## Build Commands

### Web (Astro)
Navigate to `web/` directory first.

```bash
pnpm install              # Install dependencies
pnpm dev                  # Start dev server (localhost:4321)
pnpm build                # Build production site to ./dist/
pnpm preview              # Preview production build locally
pnpm astro check          # Run Astro type checking
```

### API (Python)
Navigate to `api/` directory first.

```bash
.venv/bin/python -m pip install -r requirements.txt  # Install dependencies
.venv/bin/python main.py            # Run development server
.venv/bin/uvicorn main:app --reload # Alternative dev server
```

### Testing

Python tests use the existing pytest dev dependency in each project's own venv.
Run `.venv/bin/pytest` from `api/` or `worker/`. Worker unit tests exclude the
`e2e` marker by default. Run `.venv/bin/pytest -m e2e` from `worker/` for the full
local Git/Astro/HTTP/Chromium pipeline. Do not weaken or skip failing assertions.

## Code Style Guidelines

### TypeScript/Astro (web/)
- **Imports**: ES6 style, no comments like `// components/`
- **Formatting**: No formatters configured (no Prettier/prettierd)
- **Types**: Strict mode enabled (`astro/tsconfigs/strict`)
- **Naming**: 
  - Components: PascalCase files (`Welcome.astro`)
  - Functions: camelCase
  - Variables: camelCase
- **Astro components**: 
  - Use `.astro` extension
  - Frontmatter fence (`---`) for imports/logic
  - Scoped styles in `<style>` tags
- **File structure**:
  - `src/pages/` - Route pages
  - `src/components/` - Reusable components
  - `src/layouts/` - Page layouts
  - `src/assets/` - Static assets
- **Type imports**: Use `import type { Type }` for type-only imports when possible

### Python (api/)
- **Type hints**: Use modern pipe syntax (`str | None`, not `Optional[str]`)
- **Naming**: 
  - Functions/variables: snake_case
  - FastAPI dependencies: snake_case
  - Classes: PascalCase
  - Constants: UPPER_SNAKE_CASE
- **Imports**: Standard Python order (stdlib, third-party, local) with blank lines between
- **FastAPI patterns**:
  - Function-based routes with `@app.get/post/put/delete`
  - Type hints for all parameters
  - Return JSON-serializable types (dicts, Pydantic models)
  - Use status codes appropriately (`status_code=200`, etc.)
- **Error handling**:
  - Use FastAPI's `HTTPException` for client errors
  - Log errors appropriately (configure logging if needed)
  - Never expose stack traces to clients
- **Dependencies**: Use `requirements.txt` and `.venv/` virtual environment

### Error Handling
- **Web**: Try/catch blocks around async operations, log errors gracefully
- **API**: Use `HTTPException` for 4xx errors, let FastAPI handle 5xx
- **Never**: Expose stack traces, secrets, or internal state in error messages

### General Rules
- **NO COMMENTS** in code unless explicitly requested
- Follow existing code patterns in the repository
- Use the package manager already in use (pnpm for web, pip for api)
- No emojis unless user requests them
- Keep changes minimal and focused

## Project-Specific Notes

- **Node version**: >=22.12.0
- **Workspace**: Root directory contains all sub-projects
- **Virtual environments**: Uses `.venv/` for Python API
- **Testing**: pytest in API and worker; worker E2E is opt-in.
- **Linting**: Ruff in Python projects; Prettier and Astro check in web.

## Running Commands

Always run commands from the appropriate subdirectory:
- Web commands: `cd web && pnpm <command>`
- API commands: `cd api && .venv/bin/python <command>`

If in doubt about which commands to run, ask the user rather than guessing.

## Security & Best Practices

- **Secrets management**: Use `.env.example` as template, never commit `.env` files
- **Git**: Never commit files with secrets (.env, credentials.json, etc.)
- **Dependencies**: Check what libraries are already in use before adding new ones
- **Async operations**: Handle promises/errors appropriately in both web and api

## Build contract

Run Astro commands from `web/`. Relative paths below resolve from `web/`; absolute paths are also supported.

- `CONTENT_DIR`: Markdown source directory. Defaults to `src/content/posts`.
- `BLOG_CONFIG`: Site config JSON path. Defaults to `./blog.config.json`.
- `BUILD_CACHE_DIR`: Per-build Astro cache directory. Defaults to `./.astro`. Worker sets `BUILD_ROOT/<build_id>/.astro`; Vite cache and a disposable template workspace live inside it.
- `BUILD_OUT_DIR`: Static output directory. Defaults to `./dist`; `_build-report.json` is written inside it.
- `SITE_URL`: Astro `site` URL. Defaults to `baseUrl` in the loaded `BLOG_CONFIG` file.

## Git Workflow

- **Trunk**: `main` is the single source of truth. All prior branches (`develop`, `blog`, `features/foundation`) have been merged and deleted.
- **Branches**: Use short-lived feature branches for new functionality and open a PR back into `main`.
- **Staging/Production**: The project's core idea uses branches for staging and production (see README). When set up, `staging` and `production` should be created from `main` and only receive merges/promotions.
- **Commits**: Create atomic, focused commits with clear messages
- **PRs**: Describe changes clearly, link relevant issues
- **Review**: Ensure all changes build and pass type checks before merging

## Constraints (do not violate without asking)

- Node >=22.12.0, pnpm only. Never run `npm` or `yarn`.
- TypeScript is pinned at 6.0.3. Do NOT upgrade — 7.0.2 breaks `astro check`.
- `web/` is a static Astro site. Never add an SSR adapter or `output: 'server'`.
- No React, Vue, Svelte, or Tailwind. Interactivity is Alpine only.
- User content is plain `.md` only. Never enable MDX for user content — MDX
  executes JS at build time and user repos are untrusted. MDX is first-party only.
- `api/` and `worker/` are Python 3.14, each with its own venv.
- Every change must pass: `pnpm check` (web), `ruff check` + `pytest` (api, worker).
- Do not add a dependency without justifying it in your response.

## Worker

See `worker/README.md` for setup, commands, env vars, contracts and fresh-clone
verification. Run Python commands from `worker/` using its `.venv`. Production uses Linux/glibc atomic directory exchange; other hosts use a
rename fallback with a brief live-directory gap. Unit tests need neither Node nor network.
E2E tests use local bare repositories, local HTTP and headless Chromium; all
Cloudflare calls are mocked. Never deploy Cloudflare during local verification.
Each E2E run needs fresh BUILD_ROOT/SERVE_ROOT (the harness creates them by default).
Visual captures stay in each test run root and are not review deliverables. Keep user content
plain Markdown, preserve sanitization limits, and retain full process-group timeout
cleanup. Builds use private Astro/Vite workspaces and run concurrently. Only dependency
installation keeps the shared template lock; all of web/, including node_modules,
must remain unchanged during worker builds.

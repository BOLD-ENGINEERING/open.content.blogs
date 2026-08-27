# AGENTS.md - Instructions for Coding Agents

## Repository Overview

Monorepo containing a developer-first blogging platform with:
- `web/` - Astro 6 frontend (TypeScript)
- `api/` - FastAPI backend (Python 3.14)
- `worker/` - Background worker (placeholder)

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

**IMPORTANT**: This codebase has no test framework configured. Before adding tests:
1. Check if a testing framework is needed
2. If adding tests, ask user which framework (pytest, vitest, etc.)
3. Configure test commands in package.json or pyproject.toml

**Single test file pattern** (when tests are added):
- Python: `pytest path/to/test_file.py -k test_name`
- JavaScript: `pnpm test src/path/to/test.test.ts`

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
- **No testing infrastructure**: Must be configured if needed
- **No linting infrastructure**: Must be configured if needed

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

## Git Workflow

- **Trunk**: `main` is the single source of truth. All prior branches (`develop`, `blog`, `features/foundation`) have been merged and deleted.
- **Branches**: Use short-lived feature branches for new functionality and open a PR back into `main`.
- **Staging/Production**: The project's core idea uses branches for staging and production (see README). When set up, `staging` and `production` should be created from `main` and only receive merges/promotions.
- **Commits**: Create atomic, focused commits with clear messages
- **PRs**: Describe changes clearly, link relevant issues
- **Review**: Ensure all changes build and pass type checks before merging
# Content renderer

This static Astro site renders Markdown posts from `src/content/posts` by default. Set `CONTENT_DIR` to an absolute path, or to a path relative to `web/`, to use another directory at build time. Markdown files are discovered recursively. Only `.md` files are loaded; `.mdx` files are not treated as user content.

```bash
pnpm install --frozen-lockfile
pnpm check
pnpm build
CONTENT_DIR=/path/to/posts pnpm build
```

Post frontmatter supports `title`, `date`, `description`, `draft`, and `tags`:

```md
---
title: A post
date: 2026-09-23
description: A short summary
draft: false
tags: [news, updates]
---

Post body in Markdown.
```

The filename determines the public slug, so renaming a post changes its URL. Draft posts are loaded but omitted from public pages. Missing titles use the filename; missing or invalid dates use the file's modification time. Malformed frontmatter and other invalid fields are handled per file. The build writes fallback and skipped-file details to `dist/_build-report.json`.

`blog.config.json` supplies the site title, description, author, and base URL. The build worker can replace it before running `pnpm build`.

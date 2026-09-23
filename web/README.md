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

The filename determines the public slug, so renaming a post changes its URL. Missing titles use the filename; missing or invalid dates use the file's modification time. Malformed frontmatter and other invalid fields are handled per file. The build writes fallback and skipped-file details to `dist/_build-report.json`.

`blog.config.json` supplies the site title, description, author, and base URL. The build worker can replace it before running `pnpm build`.

The home page lists the newest posts, with ten posts per page at `/page/2/` and onward. Each post has a `/posts/<slug>/` page, and tags link to `/tags/<tag>/`. The site includes a custom 404 page. Drafts appear with a DRAFT badge during development and are excluded from production builds. The theme button switches between light and dark mode and saves the choice in local storage; before a choice is made, the site follows the system color scheme.

Published posts also appear in `/rss.xml`. The existing sitemap integration writes `sitemap-index.xml` and includes generated post and tag pages. Run `pnpm test:fixtures` from `web/` to build against `test-fixtures/sample-content/` and check the output, including fallback reporting, RSS, and sitemap routes.

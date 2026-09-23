import { promises as fs } from "node:fs";
import { basename, dirname, extname, join, relative, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import type { Loader } from "astro/loaders";
import sanitizeHtml from "sanitize-html";
import { parseDocument } from "yaml";
import { slugify } from "./slug";

type ReportItem = {
  file: string;
  field: string;
  reason: string;
  value?: string;
};
type SkippedItem = { file: string; reason: string };

type BuildReport = {
  loaded: number;
  fallbacks: ReportItem[];
  skipped: SkippedItem[];
};

function splitFrontmatter(source: string): {
  data: Record<string, unknown>;
  body: string;
  error?: string;
} {
  const text = source.replace(/^\uFEFF/, "");
  if (!text.startsWith("---\n") && !text.startsWith("---\r\n")) {
    return { data: {}, body: text };
  }

  const lines = text.split(/\r?\n/);
  const closing = lines.findIndex((line, index) => index > 0 && line === "---");
  if (closing === -1) {
    return {
      data: {},
      body: lines.slice(1).join("\n"),
      error: "Unterminated frontmatter",
    };
  }

  const body = lines.slice(closing + 1).join("\n");
  try {
    const document = parseDocument(lines.slice(1, closing).join("\n"), {
      uniqueKeys: true,
    });
    if (document.errors.length > 0) {
      return { data: {}, body, error: "Invalid YAML frontmatter" };
    }
    const parsed: unknown = document.toJS({ maxAliasCount: 20 });
    if (parsed === null) {
      return { data: {}, body };
    }
    if (typeof parsed !== "object" || Array.isArray(parsed)) {
      return { data: {}, body, error: "Frontmatter must be an object" };
    }
    return { data: parsed as Record<string, unknown>, body };
  } catch {
    return { data: {}, body, error: "Invalid YAML frontmatter" };
  }
}

async function listMarkdownFiles(
  directory: string,
  root: string,
  report: BuildReport,
): Promise<string[]> {
  let entries;
  try {
    entries = await fs.readdir(directory, { withFileTypes: true });
  } catch {
    report.skipped.push({
      file: relative(root, directory) || ".",
      reason: "Directory could not be read",
    });
    return [];
  }

  const files: string[] = [];
  for (const entry of entries.sort((a, b) =>
    a.name < b.name ? -1 : a.name > b.name ? 1 : 0,
  )) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) {
      files.push(...(await listMarkdownFiles(path, root, report)));
    } else if (entry.isFile() && entry.name.toLowerCase().endsWith(".md")) {
      files.push(path);
    }
  }
  return files;
}

export function postsLoader(): Loader {
  return {
    name: "resilient-posts-loader",
    async load({
      config,
      store,
      parseData,
      renderMarkdown,
      generateDigest,
      logger,
    }) {
      const projectRoot = fileURLToPath(config.root);
      const sourceDirectory = resolve(
        projectRoot,
        process.env.CONTENT_DIR || "src/content/posts",
      );
      const report: BuildReport = { loaded: 0, fallbacks: [], skipped: [] };
      const files = await listMarkdownFiles(
        sourceDirectory,
        sourceDirectory,
        report,
      );
      const usedSlugs = new Set<string>();
      store.clear();

      for (const file of files) {
        const relativeFile = relative(sourceDirectory, file).replaceAll(
          "\\",
          "/",
        );
        const filename = basename(file, extname(file));
        const slug = slugify(filename);
        if (!slug) {
          report.skipped.push({
            file: relativeFile,
            reason: "Filename cannot produce a slug",
          });
          continue;
        }
        if (usedSlugs.has(slug)) {
          report.skipped.push({
            file: relativeFile,
            reason: `Duplicate slug: ${slug}`,
          });
          continue;
        }
        usedSlugs.add(slug);

        try {
          const [source, stats] = await Promise.all([
            fs.readFile(file, "utf8"),
            fs.stat(file),
          ]);
          const frontmatter = splitFrontmatter(source);
          if (frontmatter.error) {
            report.fallbacks.push({
              file: relativeFile,
              field: "frontmatter",
              reason: frontmatter.error,
            });
          }

          const raw = frontmatter.data;
          const title =
            typeof raw.title === "string" && raw.title.trim()
              ? raw.title
              : filename;
          if (
            title === filename &&
            (typeof raw.title !== "string" || !raw.title.trim())
          ) {
            report.fallbacks.push({
              file: relativeFile,
              field: "title",
              reason: "Missing or invalid title",
              value: title,
            });
          }

          const dateValue =
            raw.date instanceof Date ||
            typeof raw.date === "string" ||
            typeof raw.date === "number"
              ? new Date(raw.date)
              : undefined;
          const date =
            dateValue && !Number.isNaN(dateValue.getTime())
              ? dateValue
              : stats.mtime;
          if (date === stats.mtime) {
            report.fallbacks.push({
              file: relativeFile,
              field: "date",
              reason: "Missing or unparseable date",
              value: date.toISOString(),
            });
          }

          const description =
            typeof raw.description === "string" ? raw.description : undefined;
          if (raw.description !== undefined && description === undefined) {
            report.fallbacks.push({
              file: relativeFile,
              field: "description",
              reason: "Invalid description omitted",
            });
          }
          const draft = typeof raw.draft === "boolean" ? raw.draft : false;
          if (raw.draft !== undefined && typeof raw.draft !== "boolean") {
            report.fallbacks.push({
              file: relativeFile,
              field: "draft",
              reason: "Invalid draft flag",
              value: "false",
            });
          }
          const tags =
            Array.isArray(raw.tags) &&
            raw.tags.every((tag) => typeof tag === "string")
              ? (raw.tags as string[])
              : [];
          if (raw.tags !== undefined && tags !== raw.tags) {
            report.fallbacks.push({
              file: relativeFile,
              field: "tags",
              reason: "Invalid tags",
              value: "[]",
            });
          }

          const data = await parseData({
            id: slug,
            data: { title, date, description, draft, tags },
            filePath: file,
          });
          const rendered = await renderMarkdown(`\n${frontmatter.body}`, {
            fileURL: pathToFileURL(file),
          });
          const html = sanitizeHtml(rendered.html, {
            allowedTags: [...sanitizeHtml.defaults.allowedTags, "img"],
            allowedAttributes: {
              ...sanitizeHtml.defaults.allowedAttributes,
              "*": ["id", "class"],
              img: ["src", "alt", "title", "width", "height"],
            },
            allowedSchemes: ["http", "https", "mailto"],
          });

          store.set({
            id: slug,
            data,
            body: frontmatter.body,
            filePath: relative(projectRoot, file).replaceAll("\\", "/"),
            digest: generateDigest(source),
            rendered: {
              html,
              metadata: { headings: rendered.metadata?.headings },
            },
          });
          report.loaded += 1;
        } catch (error) {
          logger.warn(
            `Skipping ${relativeFile}: ${error instanceof Error ? error.message : "Unknown error"}`,
          );
          report.skipped.push({
            file: relativeFile,
            reason: "Post could not be parsed or rendered",
          });
        }
      }

      const reportPath = join(projectRoot, ".astro", "_build-report.json");
      await fs.mkdir(dirname(reportPath), { recursive: true });
      await fs.writeFile(reportPath, JSON.stringify(report, null, 2));
      if (report.fallbacks.length || report.skipped.length) {
        logger.warn(
          `${report.fallbacks.length} fallback(s), ${report.skipped.length} skipped post(s). See _build-report.json.`,
        );
      }
    },
  };
}

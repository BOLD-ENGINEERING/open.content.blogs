import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFile, readdir, stat } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const fixtureRoot = resolve(webRoot, "../test-fixtures/sample-content");
const distRoot = join(webRoot, "dist");
const publishedSlugs = [
  "cafe-notes",
  "empty-file",
  "long-form",
  "malformed-date",
  "missing-title",
  "no-frontmatter",
  "tagged-post",
];
const expectedFallbacks = [
  "empty-file.md:date",
  "empty-file.md:title",
  "malformed-date.md:date",
  "missing-title.md:title",
  "no-frontmatter.md:date",
  "no-frontmatter.md:title",
];

const fixtureFiles = (await readdir(fixtureRoot)).filter((file) =>
  file.endsWith(".md"),
);
assert.equal(fixtureFiles.length, 8);
assert.equal((await stat(join(fixtureRoot, "empty-file.md"))).size, 0);
const longForm = await readFile(join(fixtureRoot, "long-form.md"), "utf8");
assert.equal(longForm.split("---\n").at(-1).trim().split(/\s+/).length, 3000);

const build = spawnSync("pnpm", ["build"], {
  cwd: webRoot,
  env: {
    ...process.env,
    ASTRO_TELEMETRY_DISABLED: "1",
    CONTENT_DIR: fixtureRoot,
  },
  stdio: "inherit",
});
if (build.error) throw build.error;
assert.equal(build.status, 0, "Fixture build must exit successfully");

const report = JSON.parse(
  await readFile(join(distRoot, "_build-report.json"), "utf8"),
);
assert.equal(report.loaded, 8);
assert.deepEqual(report.skipped, []);
assert.deepEqual(
  report.fallbacks.map(({ file, field }) => `${file}:${field}`).sort(),
  expectedFallbacks,
);

const actualSlugs = (await readdir(join(distRoot, "posts"))).sort();
assert.deepEqual(actualSlugs, publishedSlugs);
for (const slug of publishedSlugs) {
  await stat(join(distRoot, "posts", slug, "index.html"));
}

const feed = await readFile(join(distRoot, "rss.xml"), "utf8");
assert.equal((feed.match(/<item>/g) ?? []).length, publishedSlugs.length);
assert.ok(!feed.includes("draft-post"));
for (const slug of publishedSlugs) {
  assert.ok(feed.includes(`/posts/${slug}/`), `RSS is missing ${slug}`);
}

const sitemapIndex = await readFile(
  join(distRoot, "sitemap-index.xml"),
  "utf8",
);
assert.ok(sitemapIndex.includes("sitemap-0.xml"));
const sitemapFiles = (await readdir(distRoot)).filter((file) =>
  /^sitemap-\d+\.xml$/.test(file),
);
assert.ok(sitemapFiles.length > 0);
const sitemap = (
  await Promise.all(
    sitemapFiles.map((file) => readFile(join(distRoot, file), "utf8")),
  )
).join("\n");
assert.ok(!sitemap.includes("draft-post"));
for (const slug of publishedSlugs) {
  assert.ok(sitemap.includes(`/posts/${slug}/`), `Sitemap is missing ${slug}`);
}
for (const tag of ["news", "guides"]) {
  assert.ok(sitemap.includes(`/tags/${tag}/`), `Sitemap is missing ${tag}`);
  await stat(join(distRoot, "tags", tag, "index.html"));
}

console.log(
  "Fixture build passed: 7 published posts, RSS, and dynamic sitemap routes.",
);
console.log(JSON.stringify(report, null, 2));

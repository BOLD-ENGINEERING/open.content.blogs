import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import {
  copyFile,
  mkdtemp,
  readFile,
  readdir,
  rm,
  stat,
  writeFile,
} from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = resolve(webRoot, "..");
const fixtureRoot = resolve(repoRoot, "test-fixtures/sample-content");
const siteUrl = "https://fixture.example/";
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

const tempRoot = await mkdtemp(join(repoRoot, ".fixture-build-"));
const distRoot = join(tempRoot, "dist");
const configPath = join(tempRoot, "blog.config.json");

try {
  await copyFile(join(webRoot, "blog.config.json"), configPath);
  const config = JSON.parse(await readFile(configPath, "utf8"));
  config.title = "Fixture Blog";
  config.baseUrl = "https://config.example/";
  await writeFile(configPath, JSON.stringify(config, null, 2));

  const build = spawnSync("pnpm", ["build"], {
    cwd: webRoot,
    env: {
      ...process.env,
      ASTRO_TELEMETRY_DISABLED: "1",
      CONTENT_DIR: fixtureRoot,
      BLOG_CONFIG: configPath,
      BUILD_OUT_DIR: distRoot,
      SITE_URL: siteUrl,
    },
    stdio: "inherit",
  });
  if (build.error) throw build.error;
  assert.equal(build.status, 0, "Fixture build must exit successfully");

  const gitStatus = spawnSync("git", ["status", "--porcelain", "--", "web/"], {
    cwd: repoRoot,
    encoding: "utf8",
  });
  if (gitStatus.error) throw gitStatus.error;
  assert.equal(gitStatus.status, 0);
  assert.equal(gitStatus.stdout.trim(), "", "Build changed files in web/");

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

  const home = await readFile(join(distRoot, "index.html"), "utf8");
  assert.ok(home.includes("Fixture Blog"));
  assert.ok(home.includes(`rel="canonical" href="${siteUrl}"`));
  assert.ok(home.includes(`property="og:url" content="${siteUrl}"`));
  const longHtml = await readFile(
    join(distRoot, "posts", "long-form", "index.html"),
    "utf8",
  );
  assert.match(longHtml, /<pre[^>]*tabindex="0"/);

  const feed = await readFile(join(distRoot, "rss.xml"), "utf8");
  assert.ok(feed.includes("Fixture Blog"));
  assert.equal((feed.match(/<item>/g) ?? []).length, publishedSlugs.length);
  assert.ok(!feed.includes("draft-post"));
  for (const slug of publishedSlugs) {
    assert.ok(
      feed.includes(`${siteUrl}posts/${slug}/`),
      `RSS is missing ${slug}`,
    );
  }

  const sitemapIndex = await readFile(
    join(distRoot, "sitemap-index.xml"),
    "utf8",
  );
  assert.ok(sitemapIndex.includes(`${siteUrl}sitemap-0.xml`));
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
    assert.ok(
      sitemap.includes(`${siteUrl}posts/${slug}/`),
      `Sitemap is missing ${slug}`,
    );
  }
  for (const tag of ["news", "guides"]) {
    assert.ok(
      sitemap.includes(`${siteUrl}tags/${tag}/`),
      `Sitemap is missing ${tag}`,
    );
    await stat(join(distRoot, "tags", tag, "index.html"));
  }

  console.log(
    "Fixture build passed: external config and output, clean web/, 7 published posts, RSS, and dynamic sitemap routes.",
  );
  console.log(JSON.stringify(report, null, 2));
} finally {
  await rm(tempRoot, { recursive: true, force: true });
}

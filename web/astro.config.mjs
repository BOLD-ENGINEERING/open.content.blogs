import { readFileSync } from "node:fs";
import { readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "astro/config";
import alpinejs from "@astrojs/alpinejs";
import mdx from "@astrojs/mdx";
import sitemap from "@astrojs/sitemap";

const projectRoot = dirname(fileURLToPath(import.meta.url));
const blogConfigPath = resolve(
  projectRoot,
  process.env.BLOG_CONFIG || "./blog.config.json",
);
const blogConfig = JSON.parse(readFileSync(blogConfigPath, "utf8"));

export default defineConfig({
  site: process.env.SITE_URL || blogConfig.baseUrl,
  outDir: resolve(projectRoot, process.env.BUILD_OUT_DIR || "./dist"),
  build: { inlineStylesheets: "always" },
  integrations: [
    alpinejs(),
    mdx(),
    sitemap(),
    {
      name: "build-report",
      hooks: {
        "astro:build:done": async ({ dir }) => {
          const report = await readFile(
            new URL("./.astro/_build-report.json", import.meta.url),
          );
          await writeFile(new URL("_build-report.json", dir), report);
        },
      },
    },
  ],
});

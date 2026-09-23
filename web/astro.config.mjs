import { readFileSync } from "node:fs";
import { readFile, writeFile } from "node:fs/promises";
import { defineConfig } from "astro/config";
import alpinejs from "@astrojs/alpinejs";
import mdx from "@astrojs/mdx";
import sitemap from "@astrojs/sitemap";

const blogConfig = JSON.parse(
  readFileSync(new URL("./blog.config.json", import.meta.url), "utf8"),
);

export default defineConfig({
  site: blogConfig.baseUrl,
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

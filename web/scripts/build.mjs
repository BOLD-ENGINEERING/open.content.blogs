import { cp, mkdir, mkdtemp, rm, symlink } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "astro";

const template = resolve(dirname(fileURLToPath(import.meta.url)), "..");
for (const [name, fallback] of Object.entries({
  CONTENT_DIR: "src/content/posts",
  BLOG_CONFIG: "blog.config.json",
  BUILD_OUT_DIR: "dist",
  BUILD_CACHE_DIR: ".astro",
})) {
  process.env[name] = resolve(template, process.env[name] || fallback);
}
const cache = process.env.BUILD_CACHE_DIR;
await mkdir(cache, { recursive: true });
const workspace = await mkdtemp(resolve(cache, "template-"));
for (const name of [
  "src",
  "public",
  "astro.config.mjs",
  "tsconfig.json",
  "package.json",
]) {
  await cp(resolve(template, name), resolve(workspace, name), {
    recursive: true,
  });
}
await symlink(
  resolve(template, "node_modules"),
  resolve(workspace, "node_modules"),
  "dir",
);
process.chdir(workspace);
try {
  await build({ root: workspace });
} finally {
  process.chdir(template);
  await rm(workspace, { recursive: true, force: true });
}

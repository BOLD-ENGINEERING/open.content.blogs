import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { z } from "astro/zod";

const blogConfigSchema = z.object({
  title: z.string().min(1),
  description: z.string(),
  author: z.string().min(1),
  baseUrl: z.url(),
});

export type BlogConfig = z.infer<typeof blogConfigSchema>;

const configPath = resolve(
  process.cwd(),
  process.env.BLOG_CONFIG || "./blog.config.json",
);

export const blogConfig: BlogConfig = blogConfigSchema.parse(
  JSON.parse(readFileSync(configPath, "utf8")),
);

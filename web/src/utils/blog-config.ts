import { z } from "astro/zod";
import config from "../../blog.config.json";

const blogConfigSchema = z.object({
  title: z.string().min(1),
  description: z.string(),
  author: z.string().min(1),
  baseUrl: z.url(),
});

export type BlogConfig = z.infer<typeof blogConfigSchema>;

export const blogConfig: BlogConfig = blogConfigSchema.parse(config);

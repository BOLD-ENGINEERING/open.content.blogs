import { defineCollection } from "astro:content";
import { z } from "astro/zod";
import { postsLoader } from "./utils/posts-loader";

const posts = defineCollection({
  loader: postsLoader(),
  schema: z.object({
    title: z.string(),
    date: z.coerce.date(),
    description: z.string().optional(),
    draft: z.boolean().default(false),
    tags: z.array(z.string()).default([]),
  }),
});

export const collections = { posts };

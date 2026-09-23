import type { APIRoute } from "astro";
import rss from "@astrojs/rss";
import { blogConfig } from "../utils/blog-config";
import { getVisiblePosts } from "../utils/posts";

export const GET: APIRoute = async ({ site }) => {
  const posts = await getVisiblePosts();

  return rss({
    title: blogConfig.title,
    description: blogConfig.description,
    site: site ?? blogConfig.baseUrl,
    items: posts.map((post) => ({
      title: post.data.title,
      description: post.data.description,
      pubDate: post.data.date,
      categories: post.data.tags,
      link: `/posts/${encodeURIComponent(post.id)}/`,
    })),
  });
};

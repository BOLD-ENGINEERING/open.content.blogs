import { getCollection, type CollectionEntry } from "astro:content";
import { slugify } from "./slug";

export type Post = CollectionEntry<"posts">;
export type TagGroup = { name: string; slug: string; posts: Post[] };

export const PAGE_SIZE = 10;

export async function getVisiblePosts(): Promise<Post[]> {
  const posts = await getCollection("posts");
  return posts
    .filter((post) => !import.meta.env.PROD || !post.data.draft)
    .sort(
      (a, b) =>
        b.data.date.getTime() - a.data.date.getTime() ||
        a.id.localeCompare(b.id),
    );
}

export function pageUrl(page: number): string {
  return page === 1 ? "/" : `/page/${page}/`;
}

export function formatDate(date: Date): string {
  return date.toLocaleDateString("en", {
    year: "numeric",
    month: "long",
    day: "numeric",
    timeZone: "UTC",
  });
}

export function getTagGroups(posts: Post[]): TagGroup[] {
  const groups = new Map<string, TagGroup>();
  for (const post of posts) {
    for (const tag of post.data.tags) {
      const slug = slugify(tag);
      if (!slug) continue;
      const group = groups.get(slug);
      if (group) {
        if (!group.posts.some((entry) => entry.id === post.id)) {
          group.posts.push(post);
        }
      } else {
        groups.set(slug, { name: tag, slug, posts: [post] });
      }
    }
  }
  return [...groups.values()].sort((a, b) => a.name.localeCompare(b.name));
}

export interface BlogSummary {
  id: string;
  topic: string;
  title: string;
  audience: string;
  blog_kind: string;
  mode: string;
  created_at: string;
  has_image: boolean;
}

export interface BlogDetail extends BlogSummary {
  tone: string;
  content_markdown: string;
  plan: {
    blog_title: string;
    audience: string;
    tone: string;
    blog_kind: string;
    tasks: Array<{
      id: number;
      title: string;
      goal: string;
      bullets: string[];
      target_words: number;
      requires_code: boolean;
      requires_citations: boolean;
    }>;
  };
  evidence: Array<{ title: string; url: string; snippet?: string | null }>;
  warnings: string[];
}

export interface BlogStreamEvent {
  type: "progress" | "plan" | "content" | "complete" | "error";
  node?: string;
  plan?: BlogDetail["plan"];
  chunk?: string;
  blog?: BlogDetail;
  detail?: string;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const data = (await response.json()) as { detail?: string };
      message = data.detail ?? message;
    } catch {
      // Keep the useful HTTP status message when the response is not JSON.
    }
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  listBlogs: () => request<{ items: BlogSummary[] }>("/api/v1/blogs?limit=50"),
  getBlog: (id: string) => request<BlogDetail>(`/api/v1/blogs/${id}`),
  createBlog: (topic: string) =>
    request<BlogDetail>("/api/v1/blogs", {
      method: "POST",
      body: JSON.stringify({ topic }),
    }),
  streamBlog: async (
    topic: string,
    onEvent: (event: BlogStreamEvent) => void,
  ): Promise<BlogDetail> => {
    const response = await fetch("/api/v1/blogs/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic }),
    });
    if (!response.ok) {
      let message = `Request failed (${response.status})`;
      try {
        const data = (await response.json()) as { detail?: string };
        message = data.detail ?? message;
      } catch {
        // Preserve the HTTP status when the response is not JSON.
      }
      throw new Error(message);
    }
    if (!response.body) {
      throw new Error("The streaming response did not include a readable body.");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffered = "";
    let completedBlog: BlogDetail | undefined;

    const consumeLine = (line: string) => {
      if (!line.trim()) return;
      const event = JSON.parse(line) as BlogStreamEvent;
      if (event.type === "error") {
        throw new Error(event.detail ?? "Blog generation failed.");
      }
      if (event.type === "complete") {
        if (!event.blog) throw new Error("The stream completed without a saved blog.");
        completedBlog = event.blog;
      }
      onEvent(event);
    };

    while (true) {
      const { value, done } = await reader.read();
      buffered += decoder.decode(value, { stream: !done });
      const lines = buffered.split("\n");
      buffered = lines.pop() ?? "";
      lines.forEach(consumeLine);
      if (done) break;
    }
    if (buffered.trim()) consumeLine(buffered);
    if (!completedBlog) {
      throw new Error("The stream ended before the blog was saved.");
    }
    return completedBlog;
  },
  deleteBlog: (id: string) =>
    request<void>(`/api/v1/blogs/${id}`, { method: "DELETE" }),
};

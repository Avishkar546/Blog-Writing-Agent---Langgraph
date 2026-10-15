import { FormEvent, KeyboardEvent, MouseEvent, useCallback, useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, BlogDetail, BlogSummary, BlogStreamEvent } from "./api";

const suggestions = [
  "Designing reliable background jobs in Python",
  "Practical PostgreSQL indexing for developers",
  "Building secure APIs with FastAPI",
];

const generationStages: Record<string, string> = {
  router: "Choosing a research strategy",
  researcher: "Gathering source material",
  orchestrator: "Planning the article",
  worker: "Writing the article",
  reducer: "Preparing the final draft",
};

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export default function App() {
  const [blogs, setBlogs] = useState<BlogSummary[]>([]);
  const [selected, setSelected] = useState<BlogDetail | null>(null);
  const [topic, setTopic] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingList, setLoadingList] = useState(true);
  const [error, setError] = useState("");
  const [generationStage, setGenerationStage] = useState("");
  const [generationLogs, setGenerationLogs] = useState<string[]>([]);
  const [streamingMarkdown, setStreamingMarkdown] = useState("");
  const [streamingPlan, setStreamingPlan] = useState<BlogDetail["plan"] | null>(null);
  const [theme, setTheme] = useState<"light" | "dark">(() => (
    window.localStorage.getItem("draftwell-theme") === "dark" ? "dark" : "light"
  ));

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem("draftwell-theme", theme);
  }, [theme]);

  const refreshBlogs = useCallback(async () => {
    setLoadingList(true);
    try {
      const response = await api.listBlogs();
      setBlogs(response.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load saved blogs.");
    } finally {
      setLoadingList(false);
    }
  }, []);

  useEffect(() => {
    void refreshBlogs();
  }, [refreshBlogs]);

  async function openBlog(id: string) {
    setError("");
    setGenerationLogs([]);
    try {
      setSelected(await api.getBlog(id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load this blog.");
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!topic.trim() || loading) return;
    setLoading(true);
    setError("");
    setSelected(null);
    setGenerationStage("Starting the writing workflow");
    setGenerationLogs(["Generation started"]);
    setStreamingMarkdown("");
    setStreamingPlan(null);
    try {
      const created = await api.streamBlog(topic.trim(), (event: BlogStreamEvent) => {
        if (event.type === "progress" && event.node) {
          const stage = generationStages[event.node] ?? `Running ${event.node}`;
          setGenerationStage(stage);
          setGenerationLogs((logs) => [...logs, stage]);
        } else if (event.type === "plan" && event.plan) {
          setStreamingPlan(event.plan);
          setGenerationLogs((logs) => [...logs, "Article plan received"]);
        } else if (event.type === "content" && event.chunk) {
          setStreamingMarkdown((markdown) => markdown + event.chunk);
        } else if (event.type === "complete") {
          setGenerationStage("Draft saved");
          setGenerationLogs((logs) => [...logs, "Blog saved to the library"]);
        }
      });
      setSelected(created);
      setTopic("");
      setStreamingMarkdown("");
      await refreshBlogs();
    } catch (err) {
      setGenerationLogs((logs) => [
        ...logs,
        err instanceof Error ? `Generation failed: ${err.message}` : "Generation failed",
      ]);
      setError(err instanceof Error ? err.message : "Generation failed. Please retry.");
    } finally {
      setLoading(false);
    }
  }

  async function removeBlog(event: MouseEvent<HTMLButtonElement>, id: string) {
    event.stopPropagation();
    if (!window.confirm("Delete this saved blog? This cannot be undone.")) return;
    setError("");
    try {
      await api.deleteBlog(id);
      if (selected?.id === id) setSelected(null);
      await refreshBlogs();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete this blog.");
    }
  }

  return (
    <div className="app-shell" data-theme={theme}>
      <header className="topbar">
        <a className="brand" href="/" aria-label="Draftwell home">
          <span className="brand-mark">D</span>
          <span>draftwell</span>
        </a>
        <div className="topbar-tools">
          <div className="topbar-note"><span className="status-dot" /> Your writing studio</div>
          <button
            type="button"
            className="theme-toggle"
            aria-label={`Switch to ${theme === "light" ? "dark" : "bright"} theme`}
            aria-pressed={theme === "dark"}
            onClick={() => setTheme(theme === "light" ? "dark" : "light")}
          >
            {theme === "light" ? "☾ Dark" : "☀ Bright"}
          </button>
        </div>
      </header>

      <main className="layout">
        <aside className="sidebar">
          <div className="sidebar-heading">
            <div>
              <p className="eyebrow">LIBRARY</p>
              <h2>Saved drafts</h2>
            </div>
            <span className="count">{blogs.length}</span>
          </div>
          <div className="draft-list">
            {loadingList ? (
              <p className="muted empty-note">Loading your library…</p>
            ) : blogs.length === 0 ? (
              <div className="empty-library">
                <span className="empty-icon">✳</span>
                <p>Your generated blogs will live here.</p>
              </div>
            ) : (
              blogs.map((blog) => (
                <div
                  className={`draft-item ${selected?.id === blog.id ? "selected" : ""}`}
                  key={blog.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => void openBlog(blog.id)}
                  onKeyDown={(event: KeyboardEvent<HTMLDivElement>) => {
                    if (event.target !== event.currentTarget) return;
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      void openBlog(blog.id);
                    }
                  }}
                >
                  <span className="draft-item-title">{blog.title}</span>
                  <span className="draft-item-meta">{formatDate(blog.created_at)}</span>
                  <button
                    type="button"
                    className="delete-draft"
                    aria-label={`Delete ${blog.title}`}
                    onClick={(event) => void removeBlog(event, blog.id)}
                  >
                    ×
                  </button>
                </div>
              ))
            )}
          </div>
          <div className="sidebar-foot">
            <span className="lock-icon">⌑</span>
            Saved drafts are stored in your workspace database.
          </div>
        </aside>

        <section className="main-panel">
          {!selected && (
            <section className="hero">
              <div className="hero-kicker"><span>✦</span> RESEARCH-ASSISTED WRITING</div>
              <h1>Turn a good idea<br />into a <em>great read.</em></h1>
              <p className="hero-copy">
                Start with a topic. Draftwell researches when needed, shapes a clear
                outline, and writes a polished developer-focused blog.
              </p>
              <form className="prompt-card" onSubmit={(event) => void submit(event)}>
                <label htmlFor="topic" className="prompt-label">WHAT SHOULD WE WRITE ABOUT?</label>
                <textarea
                  id="topic"
                  value={topic}
                  onChange={(event) => setTopic(event.target.value)}
                  placeholder="e.g. The trade-offs of event-driven architecture"
                  maxLength={500}
                  rows={3}
                  disabled={loading}
                />
                <div className="prompt-footer">
                  <span>{topic.length}/500</span>
                  <button className="primary-button" type="submit" disabled={loading || topic.trim().length < 3}>
                    {loading ? <><span className="spinner" /> Creating your draft</> : <>Generate blog <span>↗</span></>}
                  </button>
                </div>
              </form>
              <div className="suggestions">
                <span>TRY A STARTER</span>
                {suggestions.map((suggestion) => (
                  <button key={suggestion} onClick={() => setTopic(suggestion)} disabled={loading}>
                    {suggestion}
                  </button>
                ))}
              </div>
              {loading && (
                <div className="progress-note">
                  <span className="progress-pulse" />
                  {generationStage || "Researching, outlining, and writing."}
                </div>
              )}
              {streamingMarkdown && (
                <section className="stream-preview" aria-live="polite">
                  <p className="eyebrow">LIVE DRAFT</p>
                  {streamingPlan?.blog_title && <h2>{streamingPlan.blog_title}</h2>}
                  <div className="markdown-body">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{streamingMarkdown}</ReactMarkdown>
                  </div>
                </section>
              )}
              {generationLogs.length > 0 && (
                <details className="workflow-log">
                  <summary>Workflow log</summary>
                  <ol>{generationLogs.map((entry, index) => <li key={`${index}-${entry}`}>{entry}</li>)}</ol>
                </details>
              )}
            </section>
          )}

          {error && <div className="error-banner" role="alert">{error}</div>}

          {selected && (
            <article className="blog-view">
              <button className="back-link" onClick={() => setSelected(null)}>← Back to studio</button>
              <div className="blog-meta">
                <span>{selected.blog_kind.replace("_", " ")}</span>
                <span>{selected.mode.replace("_", " ")} mode</span>
                <span>{formatDate(selected.created_at)}</span>
              </div>
              <h1 className="blog-title">{selected.title}</h1>
              <p className="blog-byline">For {selected.audience} · {selected.tone} tone</p>
              <div className="blog-actions">
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => {
                    const blob = new Blob([selected.content_markdown], { type: "text/markdown;charset=utf-8" });
                    const downloadUrl = URL.createObjectURL(blob);
                    const link = document.createElement("a");
                    link.href = downloadUrl;
                    link.download = `${selected.title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "blog"}.md`;
                    link.click();
                    URL.revokeObjectURL(downloadUrl);
                  }}
                >
                  Download Markdown
                </button>
                {selected.has_image && (
                  <a className="secondary-button" href={`/api/v1/blogs/${selected.id}/image`} download>
                    Download image
                  </a>
                )}
              </div>
              {selected.warnings.length > 0 && (
                <div className="warning-box">
                  {selected.warnings.map((warning) => <p key={warning}>{warning}</p>)}
                </div>
              )}
              <div className="markdown-body">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    a: ({ href, children, ...props }) => (
                      <a href={href} target="_blank" rel="noreferrer" {...props}>{children}</a>
                    ),
                  }}
                >
                  {selected.content_markdown.replace(/^#\s+.+\n+/, "")}
                </ReactMarkdown>
              </div>
              <details className="plan-details">
                <summary>View article plan</summary>
                <div className="plan-summary">
                  <span><strong>Audience</strong>{selected.plan.audience}</span>
                  <span><strong>Tone</strong>{selected.plan.tone}</span>
                  <span><strong>Format</strong>{selected.plan.blog_kind.replace(/_/g, " ")}</span>
                </div>
                <ol className="plan-tasks">
                  {selected.plan.tasks.map((task) => (
                    <li key={task.id}>
                      <strong>{task.title}</strong>
                      <span>{task.goal}</span>
                      {task.bullets.length > 0 && <small>{task.bullets.join(" · ")}</small>}
                    </li>
                  ))}
                </ol>
              </details>
              {generationLogs.length > 0 && (
                <details className="workflow-log">
                  <summary>Generation log</summary>
                  <ol>{generationLogs.map((entry, index) => <li key={`${index}-${entry}`}>{entry}</li>)}</ol>
                </details>
              )}
              {selected.evidence.length > 0 && (
                <section className="sources">
                  <h2>Sources</h2>
                  {selected.evidence.map((source) => (
                    <div className="source-item" key={source.url}>
                      <a href={source.url} target="_blank" rel="noreferrer">
                        {source.title} <span>↗</span>
                      </a>
                      {source.snippet && <p>{source.snippet}</p>}
                    </div>
                  ))}
                </section>
              )}
            </article>
          )}
        </section>
      </main>
    </div>
  );
}

import base64
import json
import logging
import re
from functools import lru_cache
from typing import Any, Iterator

import requests
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langchain_tavily import TavilySearch
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from app.agents.rate_limit import RollingTokenBudget
from app.agents.state import BlogState, ReducerState
from app.core.config import Settings, get_settings
from app.schemas.workflow import (
    EvidenceItem,
    GlobalImagePlan,
    ImageSpec,
    Plan,
    RouterDecision,
)

logger = logging.getLogger(__name__)

ROUTER_SYSTEM = """You route topics for a technical blog workflow.
Choose closed_book for evergreen fundamentals, hybrid for evergreen subjects
that need current examples, and open_book for volatile subjects such as latest
news, pricing, rankings, or policy. If research is needed, return at most three
specific scoped queries and include a time period when relevant."""

ORCHESTRATOR_SYSTEM = """Create a concise, developer-oriented technical blog plan.
Return exactly 5 sections. Each needs one short goal, exactly 3 distinct actionable
bullets (prefer 3 only), and 120-150 target words. Set requires_code=True for one
useful example; cover relevant failure modes or performance/debugging.
In closed_book mode use evergreen knowledge. In hybrid mode use evidence only
for current claims. In open_book mode include only evidence-supported events
and disclose insufficient sources. Match the Plan schema exactly."""

WORKER_SYSTEM = """Write all five planned sections as concise Markdown, in order,
at 120-150 words each. Cover every goal and bullet. Start each section with its
## title; output no H1 or commentary. For open_book news, include only claims
supported by supplied URLs and cite them inline. Include a short correct code
example when required. Avoid repetition and fluff."""


class GenerationFailure(RuntimeError):
    """Raised for provider failures that prevent a blog from being generated."""


def _estimate_request_tokens(
    messages: list[Any],
    schema: type[BaseModel] | None,
    output_tokens: int,
) -> int:
    schema_size = 0
    if schema is not None:
        schema_size = len(json.dumps(schema.model_json_schema(), separators=(",", ":")).encode("utf-8"))
    prompt_size = sum(len(str(message.content).encode("utf-8")) for message in messages)
    return prompt_size + schema_size + 64 * len(messages) + 256 + output_tokens


def _safe_invoke(
    runnable: Any,
    messages: list[Any],
    budget: RollingTokenBudget,
    output_tokens: int,
    schema: type[BaseModel] | None = None,
) -> Any:
    budget.reserve(_estimate_request_tokens(messages, schema, output_tokens))
    return runnable.invoke(messages)


def _search_evidence(queries: list[str], api_key: str) -> list[EvidenceItem]:
    if not api_key:
        raise GenerationFailure(
            "This topic requires web research, but TAVILY_API_KEY is not configured."
        )
    if not queries:
        raise GenerationFailure("The router requested research but did not provide any search queries.")

    search = TavilySearch(max_results=2, tavily_api_key=api_key)
    evidence_by_url: dict[str, EvidenceItem] = {}
    for query in queries[:3]:
        response = search.invoke({"query": query})
        for result in response.get("results", []):
            url = result.get("url")
            if not url:
                continue
            evidence_by_url[url] = EvidenceItem(
                title=(result.get("title") or url)[:120],
                url=url,
                snippet=(result.get("content") or result.get("snippet") or "")[:240] or None,
            )
    return list(evidence_by_url.values())[:4]


def _insert_image_markdown(markdown: str, plan: Plan, spec: ImageSpec) -> str:
    tasks = sorted(plan.tasks, key=lambda task: task.id)
    task_index = next((i for i, task in enumerate(tasks) if task.id == spec.section_id), None)
    headings = list(re.finditer(r"(?m)^##\s+.+$", markdown))
    if task_index is None or task_index >= len(headings):
        raise ValueError(f"Image section_id {spec.section_id} does not match a generated section.")

    heading = headings[task_index]
    if heading.group(0)[3:].strip().casefold() != tasks[task_index].title.strip().casefold():
        raise ValueError("Generated section headings do not match the structured plan.")

    section_end = headings[task_index + 1].start() if task_index + 1 < len(headings) else len(markdown)
    if spec.placement == "after_heading":
        insert_at = heading.end()
    elif spec.placement == "mid_section":
        paragraph_start = heading.end()
        while paragraph_start < section_end and markdown[paragraph_start] == "\n":
            paragraph_start += 1
        paragraph_end = markdown.find("\n\n", paragraph_start, section_end)
        insert_at = paragraph_end if paragraph_end >= 0 else section_end
    else:
        insert_at = section_end

    block = f"![{spec.alt}](image://generated)"
    if spec.caption:
        block += f"\n\n*{spec.caption}*"
    return markdown[:insert_at].rstrip() + "\n\n" + block + "\n\n" + markdown[insert_at:].lstrip()


def _generate_image(spec: ImageSpec, settings: Settings) -> tuple[bytes, str]:
    if not settings.cloudflare_account_id or not settings.cloudflare_api_token:
        raise RuntimeError("Cloudflare image credentials are not configured.")

    url = (
        f"https://api.cloudflare.com/client/v4/accounts/{settings.cloudflare_account_id}"
        "/ai/run/@cf/black-forest-labs/flux-1-schnell"
    )
    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {settings.cloudflare_api_token}",
            "Content-Type": "application/json",
        },
        json={"prompt": spec.prompt, "steps": 4},
        timeout=(10, 120),
    )
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, dict) or body.get("success") is False:
        raise RuntimeError("Cloudflare Workers AI rejected the image request.")
    result = body.get("result", body)
    encoded = result.get("image") if isinstance(result, dict) else None
    if not encoded:
        raise ValueError("Cloudflare Workers AI response did not contain an image.")
    image_data = base64.b64decode(encoded, validate=True)
    if not image_data:
        raise ValueError("Cloudflare Workers AI returned an empty image.")
    if len(image_data) > settings.max_image_bytes:
        raise ValueError(
            f"Generated image exceeds MAX_IMAGE_BYTES ({settings.max_image_bytes} bytes)."
        )
    if image_data.startswith(b"\x89PNG\r\n\x1a\n"):
        return image_data, "image/png"
    if image_data.startswith(b"\xff\xd8\xff"):
        return image_data, "image/jpeg"
    raise ValueError("Cloudflare Workers AI returned an unsupported image format.")


def build_graph(settings: Settings | None = None):
    settings = settings or get_settings()
    if not settings.groq_api_key:
        raise GenerationFailure("GROQ_API_KEY is not configured.")

    llm = ChatGroq(
        model=settings.groq_model,
        temperature=0,
        max_retries=0,
        api_key=settings.groq_api_key,
    )
    budget = RollingTokenBudget(settings.tpm_budget)

    def router_node(state: BlogState) -> dict[str, Any]:
        messages = [
            SystemMessage(content=ROUTER_SYSTEM),
            HumanMessage(content=f"Topic: {state['topic']}"),
        ]
        decision = _safe_invoke(
            llm.bind(max_tokens=128).with_structured_output(RouterDecision),
            messages,
            budget,
            128,
            RouterDecision,
        )
        return {
            "decision": decision,
            "needs_research": decision.needs_research,
            "mode": decision.mode,
            "queries": decision.queries,
        }

    def research_node(state: BlogState) -> dict[str, Any]:
        evidence = _search_evidence(state.get("queries", []), settings.tavily_api_key)
        return {"evidence": evidence}

    def orchestrator_node(state: BlogState) -> dict[str, Any]:
        evidence = state.get("evidence", [])
        mode = state["mode"]
        messages = [
            SystemMessage(content=ORCHESTRATOR_SYSTEM),
            HumanMessage(
                content=(
                    f"Topic: {state['topic']}\nMode: {mode}\n\n"
                    "Evidence (use only for fresh claims; may be empty):\n"
                    + json.dumps(
                        [
                            {
                                "title": item.title,
                                "url": item.url,
                                "snippet": (item.snippet or "")[:160],
                            }
                            for item in evidence[:3]
                        ],
                        ensure_ascii=True,
                    )
                )
            ),
        ]
        plan = _safe_invoke(
            llm.bind(max_tokens=800).with_structured_output(Plan),
            messages,
            budget,
            800,
            Plan,
        )
        return {"plan": plan}

    def worker_node(state: BlogState) -> dict[str, Any]:
        plan = state["plan"]
        task_text = "\n\n".join(
            f"{task.id}. {task.title} ({task.target_words} words; "
            f"citations={task.requires_citations}; code={task.requires_code})\n"
            f"Goal: {task.goal}\n- " + "\n- ".join(task.bullets)
            for task in sorted(plan.tasks, key=lambda item: item.id)
        )
        evidence_text = "\n".join(
            f"- {item.title} | {item.url} | {(item.snippet or '')[:160]}"
            for item in state.get("evidence", [])[:4]
        )
        messages = [
            SystemMessage(content=WORKER_SYSTEM),
            HumanMessage(
                content=(
                    f"Title: {plan.blog_title}\nTopic: {state['topic']}\n"
                    f"Audience: {plan.audience}\nMode: {state['mode']}; "
                    f"blog kind: {plan.blog_kind}\nSections:\n{task_text}\n\n"
                    f"Evidence (cite only these URLs):\n{evidence_text}"
                )
            ),
        ]
        budget.reserve(_estimate_request_tokens(messages, None, 2500))
        stream_writer = get_stream_writer()
        content: list[str] = []
        for chunk in llm.bind(max_tokens=2500).stream(messages):
            if not isinstance(chunk.content, str):
                raise GenerationFailure("The writer returned non-text content.")
            content.append(chunk.content)
            stream_writer({"type": "content", "chunk": chunk.content})
        return {"markdown_sections": "".join(content).strip()}

    def merge_markdown_node(state: ReducerState) -> dict[str, Any]:
        body = state["markdown_sections"].strip()
        markdown = f"# {state['plan'].blog_title}\n\n{body}\n"
        return {"draft_markdown": markdown}

    def image_plan_node(state: ReducerState) -> dict[str, Any]:
        plan = state["plan"]
        brief = "\n".join(f"{task.id}. {task.title}: {task.goal[:120]}" for task in plan.tasks)
        messages = [
            SystemMessage(
                content=(
                    "Decide whether one original image would materially improve this blog. "
                    "Return zero images if not useful; otherwise exactly one. Choose a valid "
                    "section_id, placement, concise alt/caption, and self-contained prompt. "
                    "Do not request text in the image."
                )
            ),
            HumanMessage(
                content=(
                    f"Topic: {state['topic'][:180]}\nTitle: {plan.blog_title[:100]}\n"
                    f"Audience: {plan.audience[:80]}\nSections:\n{brief}"
                )
            ),
        ]
        image_plan = _safe_invoke(
            llm.with_structured_output(GlobalImagePlan),
            messages,
            budget,
            350,
            GlobalImagePlan,
        )
        return {"image_plan": image_plan}

    def generate_and_save_node(state: ReducerState) -> dict[str, Any]:
        warnings: list[str] = []
        image_data = None
        image_content_type = None
        image_spec = None
        markdown = state["draft_markdown"]
        if state["image_plan"].images:
            spec = state["image_plan"].images[0]
            image_spec = spec.model_dump()
            try:
                image_data, image_content_type = _generate_image(spec, settings)
                markdown = _insert_image_markdown(markdown, state["plan"], spec)
            except (requests.RequestException, ValueError, RuntimeError) as error:
                warning = f"Optional image generation failed: {error}"
                logger.warning(warning)
                warnings.append(warning)
                image_data = None
                image_content_type = None
                image_spec = None

        return {
            "draft_markdown": markdown,
            "image_data": image_data,
            "image_content_type": image_content_type,
            "image_spec": image_spec if image_data is not None else None,
            "warnings": warnings,
        }

    reducer_builder = StateGraph(ReducerState)
    reducer_builder.add_node("merge", merge_markdown_node)
    reducer_builder.add_node("plan_image", image_plan_node)
    reducer_builder.add_node("generate_and_save", generate_and_save_node)
    reducer_builder.add_edge(START, "merge")
    reducer_builder.add_edge("merge", "plan_image")
    reducer_builder.add_edge("plan_image", "generate_and_save")
    reducer_builder.add_edge("generate_and_save", END)
    reducer_subgraph = reducer_builder.compile()

    builder = StateGraph(BlogState)
    builder.add_node("router", router_node)
    builder.add_node("researcher", research_node)
    builder.add_node("orchestrator", orchestrator_node)
    builder.add_node("worker", worker_node)
    builder.add_node("reducer", reducer_subgraph)
    builder.add_edge(START, "router")
    builder.add_conditional_edges(
        "router",
        lambda state: "researcher" if state.get("needs_research") else "orchestrator",
        {"researcher": "researcher", "orchestrator": "orchestrator"},
    )
    builder.add_edge("researcher", "orchestrator")
    builder.add_edge("orchestrator", "worker")
    builder.add_edge("worker", "reducer")
    builder.add_edge("reducer", END)
    return builder.compile()


@lru_cache
def get_graph():
    return build_graph()


def generate_blog(topic: str) -> dict[str, Any]:
    try:
        return get_graph().invoke({"topic": topic})
    except GenerationFailure:
        raise
    except Exception as error:
        logger.exception("Blog generation failed: %s", error)
        raise GenerationFailure(
            "Blog generation failed. Check API logs and provider availability, then retry."
        ) from error


def stream_blog(topic: str) -> Iterator[tuple[str, dict[str, Any]]]:
    try:
        state: dict[str, Any] = {}
        for mode, update in get_graph().stream(
            {"topic": topic}, stream_mode=["updates", "custom"]
        ):
            if mode == "custom":
                if isinstance(update, dict) and update.get("type") == "content":
                    chunk = update.get("chunk")
                    if isinstance(chunk, str):
                        yield "content", {"chunk": chunk}
                continue
            if mode != "updates" or not isinstance(update, dict):
                continue
            for node_name, node_update in update.items():
                if not isinstance(node_update, dict):
                    continue
                state.update(node_update)
                yield "progress", {"node": node_name}

                if node_name == "orchestrator" and "plan" in node_update:
                    plan = node_update["plan"]
                    yield "plan", {
                        "plan": plan.model_dump(mode="json")
                        if hasattr(plan, "model_dump")
                        else plan
                    }

        yield "final", {"result": state}
    except GenerationFailure:
        raise
    except Exception as error:
        logger.exception("Streaming blog generation failed: %s", error)
        raise GenerationFailure(
            "Blog generation failed. Check API logs and provider availability, then retry."
        ) from error

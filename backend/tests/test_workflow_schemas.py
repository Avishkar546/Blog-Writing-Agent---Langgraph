import pytest
from pydantic import ValidationError

from app.agents import graph as graph_module
from app.agents.graph import build_graph
from app.core.config import Settings
from app.schemas.workflow import GlobalImagePlan, Plan, Task


def make_task(task_id: int, bullets: list[str] | None = None) -> dict:
    return {
        "id": task_id,
        "title": f"Section {task_id}",
        "goal": "Explain the section clearly.",
        "bullets": bullets or ["First point", "Second point", "Third point"],
        "target_words": 130,
    }


def test_task_accepts_three_to_five_bullets() -> None:
    for count in (3, 4, 5):
        task = Task.model_validate(make_task(1, [f"Point {i}" for i in range(count)]))
        assert len(task.bullets) == count


def test_task_rejects_fewer_than_three_bullets() -> None:
    with pytest.raises(ValidationError):
        Task.model_validate(make_task(1, ["Only one", "Only two"]))


def test_plan_requires_exactly_five_tasks() -> None:
    with pytest.raises(ValidationError):
        Plan.model_validate(
            {
                "blog_title": "A test blog",
                "audience": "Developers",
                "tone": "Concise",
                "tasks": [make_task(1)],
            }
        )


def test_image_plan_supports_zero_or_one_image() -> None:
    assert GlobalImagePlan(images=[]).images == []
    assert len(
        GlobalImagePlan(
            images=[
                {
                    "section_id": 1,
                    "placement": "after_heading",
                    "alt": "A diagram",
                    "prompt": "A clean technical illustration.",
                }
            ]
        ).images
    ) == 1


def test_final_reducer_is_a_subgraph_with_ordered_stages() -> None:
    graph = build_graph(Settings(groq_api_key="test-key"))
    parent = graph.get_graph()
    expanded = graph.get_graph(xray=True)

    assert "reducer" in parent.nodes
    assert ("worker", "reducer") in {
        (edge.source, edge.target) for edge in parent.edges
    }
    assert ("reducer", "__end__") in {
        (edge.source, edge.target) for edge in parent.edges
    }
    assert {
        "reducer:merge",
        "reducer:plan_image",
        "reducer:generate_and_save",
    }.issubset(expanded.nodes)
    assert (
        "reducer:merge",
        "reducer:plan_image",
    ) in {(edge.source, edge.target) for edge in expanded.edges}
    assert (
        "reducer:plan_image",
        "reducer:generate_and_save",
    ) in {(edge.source, edge.target) for edge in expanded.edges}
    assert (
        "reducer:generate_and_save",
        "__end__",
    ) in {(edge.source, edge.target) for edge in expanded.edges}


def test_stream_blog_emits_progress_plan_content_and_final(monkeypatch) -> None:
    plan = Plan(
        blog_title="A streamed blog",
        audience="Developers",
        tone="Clear",
        tasks=[Task.model_validate(make_task(task_id)) for task_id in range(1, 6)],
    )

    class FakeGraph:
        def stream(self, inputs, stream_mode):
            assert inputs == {"topic": "Streaming"}
            assert stream_mode == ["updates", "custom"]
            yield "updates", {"router": {"mode": "closed_book"}}
            yield "updates", {"orchestrator": {"plan": plan}}
            yield "custom", {"type": "content", "chunk": "First streamed paragraph. "}
            yield "updates", {"worker": {"markdown_sections": "First streamed paragraph."}}
            yield "updates", {"reducer": {"draft_markdown": "# A streamed blog"}}

    monkeypatch.setattr(graph_module, "get_graph", lambda: FakeGraph())

    events = list(graph_module.stream_blog("Streaming"))

    assert [data["node"] for event, data in events if event == "progress"] == [
        "router",
        "orchestrator",
        "worker",
        "reducer",
    ]
    assert next(data["plan"]["blog_title"] for event, data in events if event == "plan") == "A streamed blog"
    chunks = [data["chunk"] for event, data in events if event == "content"]
    assert chunks == ["First streamed paragraph. "]
    assert events[-1] == (
        "final",
        {
            "result": {
                "mode": "closed_book",
                "plan": plan,
                "markdown_sections": "First streamed paragraph.",
                "draft_markdown": "# A streamed blog",
            }
        },
    )

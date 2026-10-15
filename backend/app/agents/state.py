from typing import TypedDict

from app.schemas.workflow import EvidenceItem, GlobalImagePlan, Plan, RouterDecision


class BlogState(TypedDict, total=False):
    topic: str
    mode: str
    needs_research: bool
    queries: list[str]
    evidence: list[EvidenceItem]
    decision: RouterDecision
    plan: Plan
    markdown_sections: str
    draft_markdown: str
    image_plan: GlobalImagePlan
    image_data: bytes | None
    image_content_type: str | None
    image_spec: dict | None
    warnings: list[str]


class ReducerState(TypedDict, total=False):
    topic: str
    plan: Plan
    markdown_sections: str
    draft_markdown: str
    image_plan: GlobalImagePlan
    image_data: bytes | None
    image_content_type: str | None
    image_spec: dict | None
    warnings: list[str]

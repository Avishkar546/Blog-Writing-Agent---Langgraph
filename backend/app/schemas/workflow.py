from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class Task(BaseModel):
    id: int = Field(ge=1, le=5)
    title: str = Field(min_length=1, max_length=80)
    goal: str = Field(min_length=1, max_length=180)
    bullets: list[Annotated[str, Field(min_length=1, max_length=180)]] = Field(
        min_length=3,
        max_length=5,
        description="Three to five concise, distinct section points; prefer three.",
    )
    target_words: int = Field(default=135, ge=120, le=150)
    tags: list[str] = Field(default_factory=list, max_length=2)
    requires_research: bool = False
    requires_citations: bool = False
    requires_code: bool = False


class Plan(BaseModel):
    blog_title: str = Field(min_length=1, max_length=100)
    audience: str = Field(min_length=1, max_length=80)
    tone: str = Field(min_length=1, max_length=40)
    blog_kind: Literal["explainer", "tutorial", "news_roundup", "comparison", "system_design"] = "explainer"
    constraints: list[str] = Field(default_factory=list, max_length=2)
    tasks: list[Task] = Field(min_length=5, max_length=5)


class EvidenceItem(BaseModel):
    title: str
    url: str
    published_at: str | None = None
    snippet: str | None = None
    source: str | None = None


class RouterDecision(BaseModel):
    needs_research: bool
    mode: Literal["closed_book", "hybrid", "open_book"]
    queries: list[str] = Field(default_factory=list, max_length=3)


class ImageSpec(BaseModel):
    section_id: int = Field(ge=1, le=5)
    placement: Literal["after_heading", "mid_section", "end_section"]
    alt: str = Field(min_length=1, max_length=120)
    caption: str = Field(default="", max_length=180)
    prompt: str = Field(min_length=1, max_length=700)


class GlobalImagePlan(BaseModel):
    images: list[ImageSpec] = Field(default_factory=list, max_length=1)


class BlogCreate(BaseModel):
    topic: str = Field(min_length=3, max_length=500)


class BlogSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    topic: str
    title: str
    audience: str
    blog_kind: str
    mode: str
    created_at: str
    has_image: bool


class BlogDetail(BlogSummary):
    tone: str
    content_markdown: str
    plan: dict
    evidence: list[dict]
    warnings: list[str]


class BlogList(BaseModel):
    items: list[BlogSummary]
    limit: int
    offset: int

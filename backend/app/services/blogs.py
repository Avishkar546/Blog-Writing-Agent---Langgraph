from typing import Any, Iterator
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.agents.graph import generate_blog, stream_blog
from app.models.blog import Blog, BlogImage
from app.schemas.workflow import BlogCreate, BlogDetail, BlogList, BlogSummary, Plan


class BlogNotFound(LookupError):
    pass


def _summary(blog: Blog) -> BlogSummary:
    return BlogSummary(
        id=str(blog.id),
        topic=blog.topic,
        title=blog.title,
        audience=blog.audience,
        blog_kind=blog.blog_kind,
        mode=blog.mode,
        created_at=blog.created_at.isoformat(),
        has_image=blog.image is not None,
    )


def generate_and_save(payload: BlogCreate, session: Session) -> BlogDetail:
    result = generate_blog(payload.topic)
    return _save_generated_blog(payload, result, session)


def stream_and_save(
    payload: BlogCreate, session: Session
) -> Iterator[tuple[str, dict[str, Any]]]:
    result: dict[str, Any] | None = None
    for event, data in stream_blog(payload.topic):
        if event == "final":
            result = data["result"]
        else:
            yield event, data

    if result is None:
        raise RuntimeError("The blog workflow completed without a result.")

    blog = _save_generated_blog(payload, result, session)
    yield "complete", {"blog": blog.model_dump(mode="json")}


def _save_generated_blog(
    payload: BlogCreate, result: dict[str, Any], session: Session
) -> BlogDetail:
    plan = Plan.model_validate(result["plan"])
    image_data = result.get("image_data")
    image_spec = result.get("image_spec")
    markdown = result["draft_markdown"]

    blog = Blog(
        topic=payload.topic,
        title=plan.blog_title,
        audience=plan.audience,
        tone=plan.tone,
        blog_kind=plan.blog_kind,
        mode=result["mode"],
        content_markdown=markdown,
        plan=plan.model_dump(mode="json"),
        evidence=[item.model_dump(mode="json") for item in result.get("evidence", [])],
        warnings=result.get("warnings", []),
    )
    if image_data is not None and image_spec is not None:
        blog.image = BlogImage(
            content_type=result["image_content_type"],
            data=image_data,
            alt_text=image_spec["alt"],
            caption=image_spec.get("caption", ""),
        )

    try:
        session.add(blog)
        session.flush()
        if blog.image is not None:
            blog.content_markdown = markdown.replace(
                "image://generated", f"/api/v1/blogs/{blog.id}/image"
            )
        session.commit()
        session.refresh(blog)
        return BlogDetail(
            **_summary(blog).model_dump(),
            tone=blog.tone,
            content_markdown=blog.content_markdown,
            plan=blog.plan,
            evidence=blog.evidence,
            warnings=blog.warnings,
        )
    except Exception:
        session.rollback()
        raise


def list_blogs(session: Session, limit: int, offset: int) -> BlogList:
    blogs = session.scalars(
        select(Blog)
        .options(joinedload(Blog.image))
        .order_by(Blog.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return BlogList(items=[_summary(blog) for blog in blogs], limit=limit, offset=offset)


def get_blog(session: Session, blog_id: UUID) -> BlogDetail:
    blog = session.scalar(
        select(Blog).options(joinedload(Blog.image)).where(Blog.id == blog_id)
    )
    if blog is None:
        raise BlogNotFound(f"Blog {blog_id} was not found.")
    return BlogDetail(
        **_summary(blog).model_dump(),
        tone=blog.tone,
        content_markdown=blog.content_markdown,
        plan=blog.plan,
        evidence=blog.evidence,
        warnings=blog.warnings,
    )


def get_blog_image(session: Session, blog_id: UUID) -> BlogImage:
    image = session.scalar(select(BlogImage).where(BlogImage.blog_id == blog_id))
    if image is None:
        raise BlogNotFound(f"No generated image was found for blog {blog_id}.")
    return image


def delete_blog(session: Session, blog_id: UUID) -> None:
    blog = session.get(Blog, blog_id)
    if blog is None:
        raise BlogNotFound(f"Blog {blog_id} was not found.")
    session.delete(blog)
    session.commit()

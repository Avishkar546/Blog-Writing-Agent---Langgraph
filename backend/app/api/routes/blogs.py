import json
import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.agents.graph import GenerationFailure
from app.db.session import get_db
from app.models.blog import BlogImage
from app.schemas.workflow import BlogCreate, BlogDetail, BlogList
from app.services.blogs import (
    BlogNotFound,
    delete_blog,
    generate_and_save,
    get_blog,
    get_blog_image,
    list_blogs,
    stream_and_save,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/blogs", tags=["blogs"])
Database = Annotated[Session, Depends(get_db)]


@router.post("", response_model=BlogDetail, status_code=status.HTTP_201_CREATED)
def create_blog(payload: BlogCreate, session: Database) -> BlogDetail:
    try:
        return generate_and_save(payload, session)
    except GenerationFailure as error:
        logger.warning("Blog generation request failed: %s", error)
        raise HTTPException(status_code=502, detail=str(error)) from error
    except Exception as error:
        session.rollback()
        logger.exception("Could not save generated blog")
        raise HTTPException(status_code=500, detail="Could not save generated blog.") from error


@router.post("/stream")
def create_blog_stream(payload: BlogCreate, session: Database) -> StreamingResponse:
    def events():
        try:
            for event, data in stream_and_save(payload, session):
                yield json.dumps(
                    {"type": event, **data}, ensure_ascii=False
                ) + "\n"
        except GenerationFailure as error:
            logger.warning("Streaming blog generation request failed: %s", error)
            yield json.dumps({"type": "error", "detail": str(error)}) + "\n"
        except Exception:
            session.rollback()
            logger.exception("Could not stream or save generated blog")
            yield json.dumps(
                {"type": "error", "detail": "Could not generate or save blog."}
            ) + "\n"

    return StreamingResponse(
        events(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("", response_model=BlogList)
def get_blogs(
    session: Database,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> BlogList:
    return list_blogs(session, limit, offset)


@router.get("/{blog_id}", response_model=BlogDetail)
def get_blog_by_id(blog_id: UUID, session: Database) -> BlogDetail:
    try:
        return get_blog(session, blog_id)
    except BlogNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/{blog_id}/image")
def get_image(blog_id: UUID, session: Database) -> Response:
    try:
        image: BlogImage = get_blog_image(session, blog_id)
    except BlogNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return Response(
        content=image.data,
        media_type=image.content_type,
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.delete("/{blog_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_blog(blog_id: UUID, session: Database) -> Response:
    try:
        delete_blog(session, blog_id)
    except BlogNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)

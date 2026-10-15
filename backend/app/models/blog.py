from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, LargeBinary, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Blog(Base):
    __tablename__ = "blogs"
    __table_args__ = (Index("ix_blogs_created_at", "created_at"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    topic: Mapped[str] = mapped_column(String(500), nullable=False)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    audience: Mapped[str] = mapped_column(String(80), nullable=False)
    tone: Mapped[str] = mapped_column(String(40), nullable=False)
    blog_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    content_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    plan: Mapped[dict] = mapped_column(JSONB, nullable=False)
    evidence: Mapped[list] = mapped_column(JSONB, nullable=False)
    warnings: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    image: Mapped["BlogImage | None"] = relationship(
        back_populates="blog", cascade="all, delete-orphan", uselist=False
    )


class BlogImage(Base):
    __tablename__ = "blog_images"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    blog_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("blogs.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    content_type: Mapped[str] = mapped_column(String(64), nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    alt_text: Mapped[str] = mapped_column(String(120), nullable=False)
    caption: Mapped[str] = mapped_column(String(180), nullable=False, default="")
    blog: Mapped[Blog] = relationship(back_populates="image")

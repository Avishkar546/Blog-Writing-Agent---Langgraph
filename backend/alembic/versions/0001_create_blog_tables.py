"""Create blog and generated image tables."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_create_blog_tables"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "blogs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("topic", sa.String(length=500), nullable=False),
        sa.Column("title", sa.String(length=100), nullable=False),
        sa.Column("audience", sa.String(length=80), nullable=False),
        sa.Column("tone", sa.String(length=40), nullable=False),
        sa.Column("blog_kind", sa.String(length=32), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("content_markdown", sa.Text(), nullable=False),
        sa.Column("plan", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_blogs"),
    )
    op.create_index("ix_blogs_created_at", "blogs", ["created_at"], unique=False)
    op.create_table(
        "blog_images",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("blog_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content_type", sa.String(length=64), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("alt_text", sa.String(length=120), nullable=False),
        sa.Column("caption", sa.String(length=180), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_blog_images"),
        sa.UniqueConstraint("blog_id", name="uq_blog_images_blog_id"),
        sa.ForeignKeyConstraint(["blog_id"], ["blogs.id"], ondelete="CASCADE", name="fk_blog_images_blog_id_blogs"),
    )


def downgrade() -> None:
    op.drop_table("blog_images")
    op.drop_index("ix_blogs_created_at", table_name="blogs")
    op.drop_table("blogs")

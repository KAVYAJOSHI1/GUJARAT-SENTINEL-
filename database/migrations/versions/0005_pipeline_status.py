"""pipeline_status: AI-pipeline self-reported metrics snapshot

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-05

Phase 7 -- one row per running AI pipeline service (keyed by service_id),
holding the latest AIPipeline.get_metrics() snapshot so the command-center
dashboard can show real processed-FPS / queue-depth / YOLO+OCR latency /
per-camera processing state instead of inferring pipeline liveness from
detection recency. The AI pipeline POSTs it every few seconds
(POST /api/v1/pipeline/status), the same way ingestion already pushes
per-camera health.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pipeline_status",
        sa.Column("service_id", sa.String(), primary_key=True),
        sa.Column("reported_at", sa.DateTime(), nullable=False),
        sa.Column("num_workers", sa.Integer(), nullable=True),
        sa.Column("processed_frames", sa.Integer(), nullable=True),
        sa.Column("processed_fps", sa.Float(), nullable=True),
        sa.Column("vehicles_detected", sa.Integer(), nullable=True),
        sa.Column("events_generated", sa.Integer(), nullable=True),
        sa.Column("events_delivered", sa.Integer(), nullable=True),
        sa.Column("events_dropped", sa.Integer(), nullable=True),
        sa.Column("event_queue_depth", sa.Integer(), nullable=True),
        sa.Column("event_queue_max_depth", sa.Integer(), nullable=True),
        sa.Column("yolo_p50_ms", sa.Float(), nullable=True),
        sa.Column("yolo_p95_ms", sa.Float(), nullable=True),
        sa.Column("ocr_p50_ms", sa.Float(), nullable=True),
        sa.Column("ocr_p95_ms", sa.Float(), nullable=True),
        sa.Column("cpu_percent", sa.Float(), nullable=True),
        sa.Column("rss_mb", sa.Float(), nullable=True),
        sa.Column("cameras_processing", sa.Integer(), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("pipeline_status")

"""phase 14 (1/7): vehicle_embeddings -- appearance Re-ID index

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-08

Phase 14 "Advanced Video Intelligence", commit 1 -- Vehicle Visual Re-ID.
Additive only. One new table, no change to any existing table.

  * vehicle_embeddings -- one appearance embedding per vehicle_event.
    embedding is a JSON float array (no pgvector on the postgis:15-3.3
    image); the repository does bounded brute-force cosine similarity.
    vehicle_event_id is unique -> re-indexing an event is idempotent.

The vector is produced by a pluggable backend (attribute baseline by
default, optional torch CNN, or a pipeline-supplied vector). Nothing about
the ingest / ANPR / tracking path changes; embeddings are computed
best-effort after the event is committed.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vehicle_embeddings",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "vehicle_event_id", sa.String(),
            sa.ForeignKey("vehicle_events.id"), nullable=False,
        ),
        sa.Column("plate_number_normalized", sa.String(), nullable=False),
        sa.Column("camera_id", sa.String(), sa.ForeignKey("cameras.id"), nullable=False),
        sa.Column("camera_code", sa.String(), nullable=True),
        sa.Column("track_id", sa.Integer(), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("vehicle_type", sa.String(), nullable=True),
        sa.Column("vehicle_color", sa.String(), nullable=True),
        sa.Column("embedding", sa.JSON(), nullable=False),
        sa.Column("dim", sa.Integer(), nullable=False),
        sa.Column("model_name", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False, server_default="attribute"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_vehicle_embeddings_id", "vehicle_embeddings", ["id"])
    op.create_unique_constraint(
        "uq_vehicle_embeddings_event", "vehicle_embeddings", ["vehicle_event_id"]
    )
    op.create_index(
        "ix_vehicle_embeddings_vehicle_event_id", "vehicle_embeddings", ["vehicle_event_id"]
    )
    op.create_index(
        "ix_vehicle_embeddings_plate_number_normalized",
        "vehicle_embeddings", ["plate_number_normalized"],
    )
    op.create_index("ix_vehicle_embeddings_camera_id", "vehicle_embeddings", ["camera_id"])
    op.create_index("ix_vehicle_embeddings_camera_code", "vehicle_embeddings", ["camera_code"])
    op.create_index("ix_vehicle_embeddings_timestamp", "vehicle_embeddings", ["timestamp"])
    op.create_index("ix_vehicle_embeddings_model_name", "vehicle_embeddings", ["model_name"])
    op.create_index(
        "ix_vehicle_embeddings_ts_model", "vehicle_embeddings", ["timestamp", "model_name"]
    )


def downgrade() -> None:
    op.drop_table("vehicle_embeddings")

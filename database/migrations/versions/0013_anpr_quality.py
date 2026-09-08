"""phase 15B: explicit ANPR status + failure reason + quality

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-08

Phase 15 commit 15B -- the ANPR pipeline now returns *why* a plate came
back UNKNOWN instead of a bare string. Additive columns on vehicle_events:

  * anpr_status           "OK" | "UNKNOWN"      (NOT NULL, default "OK")
  * anpr_failure_reason   NO_PLATE / LOW_RESOLUTION / BLUR / OCCLUDED /
                          OCR_DISAGREEMENT / INVALID_FORMAT / LOW_CONFIDENCE
                          (NULL on success)
  * anpr_quality_score    0-1 composite crop-quality score
  * plate_quality         0-1 plate-locator confidence

Backfill: every existing row is a successful read -> anpr_status "OK"
(the server_default handles it), anpr_failure_reason stays NULL.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "vehicle_events",
        sa.Column("anpr_status", sa.String(), nullable=False, server_default="OK"),
    )
    op.add_column("vehicle_events", sa.Column("anpr_failure_reason", sa.String(), nullable=True))
    op.add_column("vehicle_events", sa.Column("anpr_quality_score", sa.Float(), nullable=True))
    op.add_column("vehicle_events", sa.Column("plate_quality", sa.Float(), nullable=True))
    op.create_index("ix_vehicle_events_anpr_status", "vehicle_events", ["anpr_status"])
    op.create_index(
        "ix_vehicle_events_anpr_failure_reason", "vehicle_events", ["anpr_failure_reason"]
    )


def downgrade() -> None:
    op.drop_index("ix_vehicle_events_anpr_failure_reason", table_name="vehicle_events")
    op.drop_index("ix_vehicle_events_anpr_status", table_name="vehicle_events")
    op.drop_column("vehicle_events", "plate_quality")
    op.drop_column("vehicle_events", "anpr_quality_score")
    op.drop_column("vehicle_events", "anpr_failure_reason")
    op.drop_column("vehicle_events", "anpr_status")

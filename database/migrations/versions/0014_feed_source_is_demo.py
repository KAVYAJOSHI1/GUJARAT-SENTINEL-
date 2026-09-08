"""phase 15H: feed-source abstraction -- is_demo flags

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-09

Phase 15 commit 15H (§12) -- one explicit flag so seeded DEMO data is never
presented as government CCTV. Additive, defaulted false (every existing row
is real/mock, not demo).

  * cameras.is_demo         (NOT NULL default false, indexed)
  * vehicle_events.is_demo  (NOT NULL default false, indexed)

feed_source is DERIVED, not stored: DEMO (is_demo) > MOCK (code matches
^mock[_-]?cam) > REAL.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("cameras", sa.Column("is_demo", sa.Boolean(), nullable=False,
                                       server_default=sa.false()))
    op.add_column("vehicle_events", sa.Column("is_demo", sa.Boolean(), nullable=False,
                                              server_default=sa.false()))
    op.create_index("ix_cameras_is_demo", "cameras", ["is_demo"])
    op.create_index("ix_vehicle_events_is_demo", "vehicle_events", ["is_demo"])


def downgrade() -> None:
    op.drop_index("ix_vehicle_events_is_demo", table_name="vehicle_events")
    op.drop_index("ix_cameras_is_demo", table_name="cameras")
    op.drop_column("vehicle_events", "is_demo")
    op.drop_column("cameras", "is_demo")

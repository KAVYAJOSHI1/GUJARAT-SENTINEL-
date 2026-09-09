"""phase 18 Part H: vehicle_events.event_id for ingest idempotency

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-09

Adds a nullable, unique `event_id` column so a re-delivered AI detection
(the pipeline's retry-on-connection-error path re-POSTing an event whose
first attempt actually succeeded server-side but whose response was lost)
can be rejected as a duplicate instead of creating a second
`vehicle_events` row for the same detection. Additive; existing rows get
NULL (Postgres unique indexes permit any number of NULLs), so nothing
already in the table is affected.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("vehicle_events", sa.Column("event_id", sa.String(), nullable=True))
    op.create_index("ix_vehicle_events_event_id", "vehicle_events", ["event_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_vehicle_events_event_id", table_name="vehicle_events")
    op.drop_column("vehicle_events", "event_id")

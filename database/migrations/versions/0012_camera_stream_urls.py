"""phase 15A: camera browser-playable stream URLs

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-08

Phase 15 "Real Video Intelligence", commit 15A. Additive only.

  * cameras.hls_url    -- HLS (.m3u8) playback URL (widely compatible)
  * cameras.webrtc_url -- WHEP (WebRTC) playback URL (low latency)

Both NULL by default. They are populated by an operator / the registry
sync when a media gateway (e.g. MediaMTX) is deployed in front of the RTSP
feed. Nothing about RTSP ingestion changes; these are purely the
browser-facing playback sources the frontend player prefers before it
falls back to the mock clip / latest evidence snapshot.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("cameras", sa.Column("hls_url", sa.String(), nullable=True))
    op.add_column("cameras", sa.Column("webrtc_url", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("cameras", "webrtc_url")
    op.drop_column("cameras", "hls_url")

"""
vehicle_embeddings: one appearance embedding per vehicle_event (Phase 14 §1).

The embedding is produced by a pluggable backend (see
`app.services.ai.reid`):

  * "attribute"  (default, no ML deps)  -- a deterministic unit vector built
    from vehicle type + colour + a stable per-vehicle texture signature.
    A real, working baseline: identical plate strings embed identically,
    same type+colour embed close, different type/colour embed far.
  * "torch"      (optional)             -- ResNet-50 penultimate features on
    the stored vehicle crop. Activated only when torch/torchvision are
    importable (the AI pipeline container), never required by the backend.
  * pipeline-supplied                   -- if the ingest event already
    carries an `embedding[]` (an upgraded pipeline), it is stored verbatim.

Storage is a JSON float array + its dimension + the model name, so the
repository can do bounded brute-force cosine similarity without pgvector.
`vehicle_event_id` is unique -- re-indexing an event is idempotent.

Visual similarity is NOT identity. Nothing here asserts "same vehicle";
the API layer always labels a hit "VISUAL MATCH" with an explicit
similarity % and a capped confidence unless a deterministic plate match
also holds.
"""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import JSON, Column, Index
from sqlmodel import Field

from app.models.base import TimestampMixin, gen_uuid


class VehicleEmbedding(TimestampMixin, table=True):
    __tablename__ = "vehicle_embeddings"

    id: str = Field(default_factory=gen_uuid, primary_key=True, index=True)

    vehicle_event_id: str = Field(
        foreign_key="vehicle_events.id", nullable=False, unique=True, index=True
    )
    # denormalised copies of the source event's discriminants, so a
    # similarity scan is one table read (no join) and stays bounded.
    plate_number_normalized: str = Field(nullable=False, index=True)
    camera_id: str = Field(foreign_key="cameras.id", nullable=False, index=True)
    camera_code: Optional[str] = Field(default=None, nullable=True, index=True)
    track_id: Optional[int] = Field(default=None, nullable=True)
    timestamp: datetime = Field(nullable=False, index=True)

    vehicle_type: Optional[str] = Field(default=None, nullable=True)
    vehicle_color: Optional[str] = Field(default=None, nullable=True)

    # unit-normalised appearance vector
    embedding: List[float] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    dim: int = Field(nullable=False)
    model_name: str = Field(nullable=False, index=True)
    # where the vector came from: "attribute" | "torch" | "pipeline"
    source: str = Field(default="attribute", nullable=False)

    __table_args__ = (
        # windowed similarity scans read by time, optionally filtered by
        # camera / plate -- covering-ish composite for the common path.
        Index("ix_vehicle_embeddings_ts_model", "timestamp", "model_name"),
    )

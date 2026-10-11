import uuid
from datetime import datetime, timezone
import enum
from typing import TYPE_CHECKING
from sqlalchemy import String, DateTime, Enum as SAEnum, ForeignKey, Text, Boolean, Integer, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class LocationType(str, enum.Enum):
    """
    Configurable hierarchy levels for storage locations.
    Standard order: building -> floor -> room -> cabinet -> shelf -> bay -> box
    """
    BUILDING = "building"
    FLOOR = "floor"
    ROOM = "room"
    CABINET = "cabinet"
    SHELF = "shelf"
    BAY = "bay"
    BOX = "box"
    OTHER = "other"


# Permitted parent types for each location type
# Allows flexible hierarchy while enforcing intuitive structure
PERMITTED_PARENT_TYPES: dict[LocationType, set[LocationType] | None] = {
    # Building can be top-level (None parent) or inside an organization/campus (OTHER)
    LocationType.BUILDING: {LocationType.OTHER},
    # Floor can be under a building
    LocationType.FLOOR: {LocationType.BUILDING, LocationType.OTHER},
    # Room can be on a floor or directly inside a building
    LocationType.ROOM: {LocationType.FLOOR, LocationType.BUILDING, LocationType.OTHER},
    # Cabinet can be in a room, on a floor, or in a building
    LocationType.CABINET: {LocationType.ROOM, LocationType.FLOOR, LocationType.BUILDING, LocationType.OTHER},
    # Shelf can be in a cabinet, bay, or room
    LocationType.SHELF: {LocationType.CABINET, LocationType.BAY, LocationType.ROOM, LocationType.OTHER},
    # Bay can be in a room, cabinet, or floor
    LocationType.BAY: {LocationType.ROOM, LocationType.FLOOR, LocationType.CABINET, LocationType.OTHER},
    # Box can be on a shelf, in a cabinet, bay, room, etc.
    LocationType.BOX: {LocationType.SHELF, LocationType.CABINET, LocationType.BAY, LocationType.ROOM, LocationType.OTHER},
    # Other can be under any or top-level
    LocationType.OTHER: set(LocationType),
}


class StorageLocation(Base):
    """
    Storage Location model.
    Represents a physical container or location node in the organizational storage hierarchy.
    Supports recursive nesting (parent-child relationship).
    """
    __tablename__ = "storage_locations"

    __table_args__ = (
        Index("ix_storage_locations_department_status", "department", "is_active"),
        Index("ix_storage_locations_parent_id", "parent_id"),
    )

    # Internal UUID
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Unique location code, e.g. LOC-BLD-01, CAB-FIN-A3
    location_code: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
    )

    # Human-readable location name, e.g. "Main Archives Building", "Floor 2", "Cabinet A"
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    # Location type (building, floor, room, cabinet, shelf, bay, box, etc.)
    location_type: Mapped[LocationType] = mapped_column(
        SAEnum(
            LocationType,
            name="location_type",
            native_enum=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        index=True,
    )

    # Optional description or notes
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Owning department (consistent with EDRMS department model)
    department: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    # Optional parent location UUID for hierarchical organization
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("storage_locations.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    # Optional maximum capacity (direct physical files)
    max_capacity: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    # Active / Inactive status
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
    )

    # User who created the location
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # User who last modified the location
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )

    # Creation and update timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    # Self-referencing hierarchical relationships
    parent = relationship("StorageLocation", remote_side=[id], back_populates="children")
    children = relationship("StorageLocation", back_populates="parent", cascade="all, delete-orphan", passive_deletes=False)

    # Direct physical files residing at this location
    physical_files = relationship("PhysicalFile", back_populates="storage_location")

    # Audit creator/updater relationships
    created_by = relationship("User", foreign_keys=[created_by_id])
    updated_by = relationship("User", foreign_keys=[updated_by_id])

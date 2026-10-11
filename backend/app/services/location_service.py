"""
Storage Location Helper Utilities.
Constructs human-readable hierarchy paths and prevents cyclic relationships.
"""
import uuid
from sqlalchemy.orm import Session
from app.models.storage_location import StorageLocation, LocationType, PERMITTED_PARENT_TYPES


def get_location_path(db: Session, location: StorageLocation) -> str:
    """
    Constructs the human-readable hierarchical path string:
    e.g. "Main Building / Floor 2 / Records Room / Cabinet A / Shelf 3"
    """
    if not location:
        return ""

    parts = [location.name]
    curr = location
    visited = {curr.id}

    while curr.parent_id:
        if curr.parent_id in visited:
            # Cycle safeguard
            break
        parent = db.query(StorageLocation).filter(StorageLocation.id == curr.parent_id).first()
        if not parent:
            break
        visited.add(parent.id)
        parts.append(parent.name)
        curr = parent

    return " / ".join(reversed(parts))


def get_location_breadcrumbs(db: Session, location: StorageLocation) -> list[dict]:
    """
    Builds structured breadcrumb list from root down to current location.
    """
    if not location:
        return []

    crumbs = [{
        "id": location.id,
        "location_code": location.location_code,
        "name": location.name,
        "location_type": location.location_type,
    }]
    curr = location
    visited = {curr.id}

    while curr.parent_id:
        if curr.parent_id in visited:
            break
        parent = db.query(StorageLocation).filter(StorageLocation.id == curr.parent_id).first()
        if not parent:
            break
        visited.add(parent.id)
        crumbs.append({
            "id": parent.id,
            "location_code": parent.location_code,
            "name": parent.name,
            "location_type": parent.location_type,
        })
        curr = parent

    crumbs.reverse()
    return crumbs


def validate_parent_child_hierarchy(
    db: Session,
    child_type: LocationType,
    parent: StorageLocation | None,
    current_location_id: uuid.UUID | None = None,
) -> None:
    """
    Validates hierarchical rules:
    1. Location cannot be its own parent.
    2. Parent cannot be a descendant of current location (cycle prevention).
    3. Hierarchy type rules (PERMITTED_PARENT_TYPES).
    Raises ValueError with explanatory message on invalid relationship.
    """
    if parent is None:
        # Top-level locations: check if allowed
        # Building and Other can always be top-level. Others should preferably have a parent, but permitted.
        return

    if current_location_id and parent.id == current_location_id:
        raise ValueError("A storage location cannot be its own parent.")

    # Cycle check: traverse up from parent to root; current_location_id must not appear
    if current_location_id:
        curr = parent
        visited = {curr.id}
        while curr.parent_id:
            if curr.parent_id == current_location_id:
                raise ValueError("Circular hierarchy detected: cannot move a parent beneath one of its descendants.")
            if curr.parent_id in visited:
                break
            ancestor = db.query(StorageLocation).filter(StorageLocation.id == curr.parent_id).first()
            if not ancestor:
                break
            visited.add(ancestor.id)
            curr = ancestor

    # Hierarchy type rule check
    allowed_parents = PERMITTED_PARENT_TYPES.get(child_type)
    if allowed_parents is not None and parent.location_type not in allowed_parents:
        allowed_names = ", ".join(t.value for t in allowed_parents)
        raise ValueError(
            f"Invalid location hierarchy: '{child_type.value}' cannot be placed inside '{parent.location_type.value}'. "
            f"Permitted parent types: {allowed_names}."
        )

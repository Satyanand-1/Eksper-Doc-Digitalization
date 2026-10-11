"""
Notification API router for EDRMS.
Provides in-app notification retrieval, unread count tracking, and marking notifications as read.
"""
import uuid
import math
import logging
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.notification import Notification, utc_now
from app.schemas.notification import (
    PaginatedNotificationsResponse,
    NotificationItem,
    UnreadCountResponse,
    MarkNotificationReadResponse,
)

logger = logging.getLogger("edrms.notifications")

router = APIRouter(prefix="/api/v1/notifications", tags=["Notifications"])


@router.get(
    "",
    response_model=PaginatedNotificationsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get authenticated user's notifications",
    description="Returns a paginated list of notifications for the authenticated user, ordered newest-first. Supports filtering by unread-only status.",
)
def get_notifications(
    request: Request,
    page: Annotated[int, Query(ge=1, description="Page number (1-indexed)")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Page size limit (1-100)")] = 20,
    unread_only: Annotated[bool, Query(description="Filter to unread notifications only")] = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get notifications belonging exclusively to the authenticated user:
    - Strictly scoped to recipient_id == current_user.id at the database level.
    - Deterministic ordering: created_at desc, id desc.
    - Computes overall unread count for the user.
    """
    # 1. Total unread count for authenticated user
    unread_count = (
        db.query(func.count(Notification.id))
        .filter(
            Notification.recipient_id == current_user.id,
            Notification.is_read.is_(False),
        )
        .scalar()
        or 0
    )

    # 2. Base query filtered strictly to current_user
    query = db.query(Notification).filter(Notification.recipient_id == current_user.id)
    if unread_only:
        query = query.filter(Notification.is_read.is_(False))

    total = query.count()
    total_pages = math.ceil(total / page_size) if total > 0 else 0
    offset = (page - 1) * page_size

    notifications = (
        query.order_by(desc(Notification.created_at), desc(Notification.id))
        .offset(offset)
        .limit(page_size)
        .all()
    )

    items = [
        NotificationItem(
            id=n.id,
            recipient_id=n.recipient_id,
            notification_type=n.notification_type,
            title=n.title,
            message=n.message,
            document_id=n.document_id,
            workflow_id=n.workflow_id,
            is_read=n.is_read,
            read_at=n.read_at,
            created_at=n.created_at,
        )
        for n in notifications
    ]

    return PaginatedNotificationsResponse(
        items=items,
        total=total,
        unread_count=unread_count,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/unread-count",
    response_model=UnreadCountResponse,
    status_code=status.HTTP_200_OK,
    summary="Get unread notification count",
    description="Returns the total count of unread notifications for the authenticated user.",
)
def get_unread_count(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Lightweight endpoint returning caller's unread notification count.
    """
    unread_count = (
        db.query(func.count(Notification.id))
        .filter(
            Notification.recipient_id == current_user.id,
            Notification.is_read.is_(False),
        )
        .scalar()
        or 0
    )

    return UnreadCountResponse(unread_count=unread_count)


@router.post(
    "/{notification_id}/read",
    response_model=MarkNotificationReadResponse,
    status_code=status.HTTP_200_OK,
    summary="Mark notification as read",
    description="Marks the specified notification as read. Idempotent and restricted to the notification owner.",
)
def mark_notification_as_read(
    notification_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Mark notification as read:
    - User can only update their own notifications.
    - If notification belongs to someone else or does not exist, returns non-disclosing 404.
    - Idempotent: repeated calls succeed without altering the original read_at timestamp.
    """
    notification = (
        db.query(Notification)
        .filter(
            Notification.id == notification_id,
            Notification.recipient_id == current_user.id,
        )
        .first()
    )

    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notification with ID {notification_id} not found.",
        )

    if not notification.is_read:
        notification.is_read = True
        notification.read_at = utc_now()
        db.commit()
        db.refresh(notification)

    return MarkNotificationReadResponse(
        id=notification.id,
        is_read=notification.is_read,
        read_at=notification.read_at,
    )

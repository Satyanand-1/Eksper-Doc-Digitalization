import uuid
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
from app.models.notification import NotificationType


class NotificationItem(BaseModel):
    """
    Representation of an individual in-app notification.
    """
    id: uuid.UUID = Field(..., description="Notification unique identifier")
    recipient_id: uuid.UUID = Field(..., description="Recipient user unique identifier")
    notification_type: NotificationType = Field(..., description="Type of workflow event notification")
    title: str = Field(..., description="Notification headline")
    message: str = Field(..., description="Safe human-readable notification message")
    document_id: uuid.UUID | None = Field(None, description="Associated document unique identifier, if applicable")
    workflow_id: uuid.UUID | None = Field(None, description="Associated workflow unique identifier, if applicable")
    is_read: bool = Field(..., description="Read / unread state flag")
    read_at: datetime | None = Field(None, description="Timestamp when notification was marked as read (UTC)")
    created_at: datetime = Field(..., description="Notification creation timestamp (UTC)")

    model_config = ConfigDict(from_attributes=True)


class PaginatedNotificationsResponse(BaseModel):
    """
    Paginated list of user notifications including unread count summary.
    """
    items: list[NotificationItem] = Field(..., description="Notifications on current page")
    total: int = Field(..., description="Total matching notifications")
    unread_count: int = Field(..., description="Total unread notifications for authenticated user")
    page: int = Field(..., description="Current page number (1-indexed)")
    page_size: int = Field(..., description="Page size limit")
    total_pages: int = Field(..., description="Total available pages")

    model_config = ConfigDict(from_attributes=True)


class UnreadCountResponse(BaseModel):
    """
    Current unread notification count for the authenticated user.
    """
    unread_count: int = Field(..., description="Total count of unread notifications for the caller")

    model_config = ConfigDict(from_attributes=True)


class MarkNotificationReadResponse(BaseModel):
    """
    Response returned upon marking a notification as read.
    """
    id: uuid.UUID = Field(..., description="Notification unique identifier")
    is_read: bool = Field(..., description="Updated read state (always true)")
    read_at: datetime = Field(..., description="Timestamp when marked as read (UTC)")

    model_config = ConfigDict(from_attributes=True)

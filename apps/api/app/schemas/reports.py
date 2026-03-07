from datetime import date, datetime
from pydantic import BaseModel


class ReportGenerateRequest(BaseModel):
    category: str
    reporting_month: date


class ReportDTO(BaseModel):
    id: int
    category: str
    title: str
    reporting_month: date
    status: str
    generated_at: datetime
    file_path: str | None
    metadata: dict[str, object] | None = None


class ReportGenerateResponse(BaseModel):
    id: int
    category: str
    status: str
    reporting_month: date
    file_path: str | None
    metadata: dict[str, object] | None = None


class ReportExportMetadata(BaseModel):
    report_id: int
    format: str
    media_type: str
    file_path: str
    file_name: str


class ReportRecipientGroupCreate(BaseModel):
    name: str
    description: str | None = None
    report_category: str | None = None
    role_name: str | None = None
    organization_id: int | None = None
    delivery_channel: str = "file_drop"
    export_format: str = "pdf"
    max_attempts: int = 3
    retry_backoff_seconds: int = 300
    notify_on_failure: bool = True
    is_active: bool = True
    metadata: dict[str, object] | None = None


class ReportRecipientGroupUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    report_category: str | None = None
    role_name: str | None = None
    organization_id: int | None = None
    delivery_channel: str | None = None
    export_format: str | None = None
    max_attempts: int | None = None
    retry_backoff_seconds: int | None = None
    notify_on_failure: bool | None = None
    is_active: bool | None = None
    metadata: dict[str, object] | None = None


class ReportRecipientGroupDTO(BaseModel):
    id: int
    name: str
    description: str | None
    report_category: str | None
    role_name: str | None
    organization_id: int | None
    delivery_channel: str
    export_format: str
    max_attempts: int
    retry_backoff_seconds: int
    notify_on_failure: bool
    is_active: bool
    last_used_at: datetime | None
    metadata: dict[str, object] | None = None
    created_at: datetime
    updated_at: datetime


class ReportDistributionQueueResponse(BaseModel):
    report_id: int
    queued_count: int
    skipped_count: int
    group_count: int


class ReportDeliveryLogDTO(BaseModel):
    id: int
    report_id: int
    recipient_group_id: int
    recipient_user_id: int
    recipient_email: str
    recipient_role: str | None = None
    recipient_organization_id: int | None = None
    delivery_channel: str
    export_format: str
    status: str
    attempt_count: int
    max_attempts: int
    next_attempt_at: datetime | None = None
    dispatched_at: datetime
    delivered_at: datetime | None = None
    last_error: str | None = None
    notification_sent_at: datetime | None = None
    payload: dict[str, object] | None = None
    created_at: datetime
    updated_at: datetime


class ReportDeliveryProcessResponse(BaseModel):
    processed_count: int
    sent_count: int
    failed_count: int
    retrying_count: int
    deliveries: list[ReportDeliveryLogDTO]

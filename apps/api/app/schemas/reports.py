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


class ReportGenerateResponse(BaseModel):
    id: int
    category: str
    status: str
    reporting_month: date
    file_path: str | None


class ReportExportMetadata(BaseModel):
    report_id: int
    format: str
    media_type: str
    file_path: str
    file_name: str

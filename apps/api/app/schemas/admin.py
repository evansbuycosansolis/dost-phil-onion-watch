from datetime import datetime

from pydantic import BaseModel


class AdminSettingUpdate(BaseModel):
    key: str
    value: str


class AdminDocumentIngestionStatusDTO(BaseModel):
    latest_run_id: int | None
    latest_status: str
    num_chunks: int


class AdminJobStatusDTO(BaseModel):
    id: int
    job_name: str
    status: str
    correlation_id: str | None = None
    started_at: datetime
    finished_at: datetime | None


class AdminPipelineRunDTO(BaseModel):
    id: int
    status: str
    details: dict[str, object] | None = None


class AdminForecastDiagnosticsDTO(BaseModel):
    run_id: int | None
    selected_model_counts: dict[str, int]
    model_avg_score: dict[str, float]
    model_avg_holdout_mae: dict[str, float]
    municipalities_covered: int


class AdminOverviewDTO(BaseModel):
    users_count: int
    document_ingestion_status: AdminDocumentIngestionStatusDTO
    job_status: list[AdminJobStatusDTO]
    pipeline_runs: list[AdminPipelineRunDTO]
    report_distribution_status: dict[str, int]
    forecast_model_diagnostics: AdminForecastDiagnosticsDTO
    system_settings: dict[str, object]


class AdminJobRecordDTO(BaseModel):
    id: int
    job_name: str
    status: str
    correlation_id: str | None = None
    started_at: datetime
    finished_at: datetime | None
    message: str | None = None
    details: dict[str, object] | None = None


class AdminPipelineTriggerResponse(BaseModel):
    job_id: int
    status: str


class AdminSettingResponse(BaseModel):
    message: str
    key: str
    value: str

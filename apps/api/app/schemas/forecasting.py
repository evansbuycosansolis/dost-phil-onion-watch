from datetime import date, datetime

from pydantic import BaseModel, Field


class ForecastRunRequest(BaseModel):
    run_month: date | None = None


class ForecastRunResult(BaseModel):
    run_id: int
    status: str


class ForecastOutputDTO(BaseModel):
    id: int
    municipality_id: int
    period_start: date
    period_end: date
    next_month_supply_tons: float
    next_quarter_trend: float
    shortage_probability: float
    oversupply_probability: float
    confidence_score: float
    selected_model: str | None = None
    selected_model_score: float | None = None
    fallback_order: list[str] = Field(default_factory=list)


class ForecastModelCandidateDTO(BaseModel):
    model_name: str
    model_family: str
    is_available: bool
    prediction_next_month: float | None = None
    holdout_mae: float | None = None
    holdout_mape: float | None = None
    score: float | None = None
    rank: int | None = None
    selected: bool


class MunicipalityForecastDiagnosticDTO(BaseModel):
    municipality_id: int
    municipality_name: str
    selected_model: str | None = None
    selected_score: float | None = None
    fallback_order: list[str] = Field(default_factory=list)
    candidates: list[ForecastModelCandidateDTO]


class ForecastDiagnosticsDTO(BaseModel):
    run_id: int | None
    selected_model_counts: dict[str, int]
    model_avg_score: dict[str, float]
    model_avg_holdout_mae: dict[str, float]
    municipality_diagnostics: list[MunicipalityForecastDiagnosticDTO]


class ForecastRunDTO(BaseModel):
    id: int
    run_at: datetime
    run_month: date
    model_used: str
    status: str
    metrics: dict[str, object] | None = None


class ForecastLatestResponse(BaseModel):
    run: ForecastRunDTO | None
    outputs: list[ForecastOutputDTO]
    diagnostics: ForecastDiagnosticsDTO | None = None

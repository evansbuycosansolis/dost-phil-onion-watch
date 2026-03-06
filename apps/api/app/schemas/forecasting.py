from datetime import date, datetime
from pydantic import BaseModel


class ForecastRunRequest(BaseModel):
    run_month: date | None = None


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


class ForecastRunDTO(BaseModel):
    id: int
    run_at: datetime
    run_month: date
    model_used: str
    status: str
    outputs: list[ForecastOutputDTO]

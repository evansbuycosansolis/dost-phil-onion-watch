from datetime import date
from pydantic import BaseModel


class MunicipalSummary(BaseModel):
    municipality_id: int
    municipality_name: str
    production_tons: float
    stock_tons: float
    avg_farmgate_price: float


class ProvincialOverview(BaseModel):
    reporting_month: date
    total_harvest_volume_tons: float
    current_warehouse_stock_tons: float
    cold_storage_utilization_pct: float
    stock_release_volume_tons: float
    forecast_next_month_supply_tons: float
    active_alerts: int
    anomaly_hotspots: list[str]
    municipality_cards: list[MunicipalSummary]


class WarehouseOverviewRow(BaseModel):
    warehouse_id: int
    warehouse_name: str
    municipality_name: str
    location: str
    capacity_tons: float
    current_stock_tons: float
    utilization_pct: float
    last_update: date | None
    release_trend_tons: float
    anomaly_flag: bool

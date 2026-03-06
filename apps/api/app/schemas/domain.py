from datetime import date
from pydantic import BaseModel


class MunicipalityCreate(BaseModel):
    code: str
    name: str
    province: str = "Occidental Mindoro"
    region: str = "MIMAROPA"


class FarmerCreate(BaseModel):
    farmer_code: str
    full_name: str
    municipality_id: int
    barangay_id: int | None = None
    phone_number: str | None = None


class HarvestReportCreate(BaseModel):
    municipality_id: int
    farmer_id: int | None = None
    reporting_month: date
    harvest_date: date
    volume_tons: float
    quality_grade: str | None = None


class WarehouseCreate(BaseModel):
    municipality_id: int
    name: str
    location: str
    capacity_tons: float


class WarehouseStockReportCreate(BaseModel):
    warehouse_id: int
    municipality_id: int
    reporting_month: date
    report_date: date
    current_stock_tons: float
    inflow_tons: float = 0
    outflow_tons: float = 0


class PriceReportCreate(BaseModel):
    municipality_id: int
    report_date: date
    reporting_month: date
    price_per_kg: float
    market_id: int | None = None


class ImportRecordCreate(BaseModel):
    import_reference: str
    origin_country: str
    arrival_date: date
    reporting_month: date
    volume_tons: float
    status: str

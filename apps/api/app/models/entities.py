from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Role(Base, TimestampMixin):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)


class StakeholderOrganization(Base, TimestampMixin):
    __tablename__ = "stakeholder_organizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    organization_type: Mapped[str] = mapped_column(String(80), nullable=False)
    municipality_id: Mapped[int | None] = mapped_column(ForeignKey("municipalities.id"), nullable=True, index=True)


class Municipality(Base, TimestampMixin):
    __tablename__ = "municipalities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    province: Mapped[str] = mapped_column(String(120), default="Occidental Mindoro", nullable=False)
    region: Mapped[str] = mapped_column(String(120), default="MIMAROPA", nullable=False)


class Barangay(Base, TimestampMixin):
    __tablename__ = "barangays"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    municipality_id: Mapped[int] = mapped_column(ForeignKey("municipalities.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)


class Market(Base, TimestampMixin):
    __tablename__ = "markets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    municipality_id: Mapped[int] = mapped_column(ForeignKey("municipalities.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    market_type: Mapped[str] = mapped_column(String(40), nullable=False)


class Warehouse(Base, TimestampMixin):
    __tablename__ = "warehouses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    municipality_id: Mapped[int] = mapped_column(ForeignKey("municipalities.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    location: Mapped[str] = mapped_column(String(255), nullable=False)
    capacity_tons: Mapped[float] = mapped_column(Float, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ColdStorageFacility(Base, TimestampMixin):
    __tablename__ = "cold_storage_facilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    warehouse_id: Mapped[int | None] = mapped_column(ForeignKey("warehouses.id"), nullable=True, index=True)
    municipality_id: Mapped[int] = mapped_column(ForeignKey("municipalities.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    location: Mapped[str] = mapped_column(String(255), nullable=False)
    capacity_tons: Mapped[float] = mapped_column(Float, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    municipality_id: Mapped[int | None] = mapped_column(ForeignKey("municipalities.id"), nullable=True, index=True)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("stakeholder_organizations.id"), nullable=True, index=True)


class UserRole(Base, TimestampMixin):
    __tablename__ = "user_roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False, index=True)


class FarmerProfile(Base, TimestampMixin):
    __tablename__ = "farmer_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    farmer_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    municipality_id: Mapped[int] = mapped_column(ForeignKey("municipalities.id"), nullable=False, index=True)
    barangay_id: Mapped[int | None] = mapped_column(ForeignKey("barangays.id"), nullable=True, index=True)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("stakeholder_organizations.id"), nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String(40), nullable=True)


class FarmLocation(Base, TimestampMixin):
    __tablename__ = "farm_locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    farmer_id: Mapped[int] = mapped_column(ForeignKey("farmer_profiles.id"), nullable=False, index=True)
    municipality_id: Mapped[int] = mapped_column(ForeignKey("municipalities.id"), nullable=False, index=True)
    barangay_id: Mapped[int | None] = mapped_column(ForeignKey("barangays.id"), nullable=True)
    area_hectares: Mapped[float] = mapped_column(Float, nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)


class PlantingRecord(Base, TimestampMixin):
    __tablename__ = "planting_records"
    __table_args__ = (Index("ix_planting_records_expected_harvest_month", "expected_harvest_month"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    farmer_id: Mapped[int] = mapped_column(ForeignKey("farmer_profiles.id"), nullable=False, index=True)
    farm_location_id: Mapped[int] = mapped_column(ForeignKey("farm_locations.id"), nullable=False, index=True)
    planting_date: Mapped[date] = mapped_column(Date, nullable=False)
    expected_harvest_month: Mapped[date] = mapped_column(Date, nullable=False)
    variety: Mapped[str] = mapped_column(String(80), nullable=False)
    area_hectares: Mapped[float] = mapped_column(Float, nullable=False)


class HarvestReport(Base, TimestampMixin):
    __tablename__ = "harvest_reports"
    __table_args__ = (
        Index("ix_harvest_reports_reporting_month", "reporting_month"),
        Index("ix_harvest_reports_municipality_reporting", "municipality_id", "reporting_month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    farmer_id: Mapped[int | None] = mapped_column(ForeignKey("farmer_profiles.id"), nullable=True, index=True)
    municipality_id: Mapped[int] = mapped_column(ForeignKey("municipalities.id"), nullable=False, index=True)
    reporting_month: Mapped[date] = mapped_column(Date, nullable=False)
    harvest_date: Mapped[date] = mapped_column(Date, nullable=False)
    volume_tons: Mapped[float] = mapped_column(Float, nullable=False)
    quality_grade: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="submitted", nullable=False)


class YieldEstimate(Base, TimestampMixin):
    __tablename__ = "yield_estimates"
    __table_args__ = (
        Index("ix_yield_estimates_reporting_month", "reporting_month"),
        Index("ix_yield_estimates_municipality_reporting", "municipality_id", "reporting_month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    municipality_id: Mapped[int] = mapped_column(ForeignKey("municipalities.id"), nullable=False, index=True)
    reporting_month: Mapped[date] = mapped_column(Date, nullable=False)
    estimated_yield_tons: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)


class WarehouseStockReport(Base, TimestampMixin):
    __tablename__ = "warehouse_stock_reports"
    __table_args__ = (
        Index("ix_warehouse_stock_reports_reporting_month", "reporting_month"),
        Index("ix_warehouse_stock_reports_warehouse_reporting", "warehouse_id", "reporting_month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), nullable=False, index=True)
    municipality_id: Mapped[int] = mapped_column(ForeignKey("municipalities.id"), nullable=False, index=True)
    reporting_month: Mapped[date] = mapped_column(Date, nullable=False)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    current_stock_tons: Mapped[float] = mapped_column(Float, nullable=False)
    inflow_tons: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    outflow_tons: Mapped[float] = mapped_column(Float, default=0, nullable=False)


class ColdStorageStockReport(Base, TimestampMixin):
    __tablename__ = "cold_storage_stock_reports"
    __table_args__ = (
        Index("ix_cold_storage_stock_reports_reporting_month", "reporting_month"),
        Index("ix_cold_storage_stock_reports_facility_reporting", "cold_storage_facility_id", "reporting_month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cold_storage_facility_id: Mapped[int] = mapped_column(ForeignKey("cold_storage_facilities.id"), nullable=False, index=True)
    municipality_id: Mapped[int] = mapped_column(ForeignKey("municipalities.id"), nullable=False, index=True)
    reporting_month: Mapped[date] = mapped_column(Date, nullable=False)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    current_stock_tons: Mapped[float] = mapped_column(Float, nullable=False)
    utilization_pct: Mapped[float] = mapped_column(Float, nullable=False)


class StockReleaseLog(Base, TimestampMixin):
    __tablename__ = "stock_release_logs"
    __table_args__ = (Index("ix_stock_release_logs_reporting_month", "reporting_month"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), nullable=False, index=True)
    release_date: Mapped[date] = mapped_column(Date, nullable=False)
    reporting_month: Mapped[date] = mapped_column(Date, nullable=False)
    volume_tons: Mapped[float] = mapped_column(Float, nullable=False)
    destination_market_id: Mapped[int | None] = mapped_column(ForeignKey("markets.id"), nullable=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class TransportLog(Base, TimestampMixin):
    __tablename__ = "transport_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    origin_warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), nullable=False, index=True)
    destination_market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"), nullable=False, index=True)
    transport_date: Mapped[date] = mapped_column(Date, nullable=False)
    volume_tons: Mapped[float] = mapped_column(Float, nullable=False)
    vehicle_plate: Mapped[str | None] = mapped_column(String(40), nullable=True)


class DistributionLog(Base, TimestampMixin):
    __tablename__ = "distribution_logs"
    __table_args__ = (Index("ix_distribution_logs_reporting_month", "reporting_month"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    municipality_id: Mapped[int] = mapped_column(ForeignKey("municipalities.id"), nullable=False, index=True)
    market_id: Mapped[int | None] = mapped_column(ForeignKey("markets.id"), nullable=True, index=True)
    distribution_date: Mapped[date] = mapped_column(Date, nullable=False)
    reporting_month: Mapped[date] = mapped_column(Date, nullable=False)
    volume_tons: Mapped[float] = mapped_column(Float, nullable=False)


class FarmgatePriceReport(Base, TimestampMixin):
    __tablename__ = "farmgate_price_reports"
    __table_args__ = (
        Index("ix_farmgate_price_reports_report_date", "report_date"),
        Index("ix_farmgate_price_reports_reporting_month", "reporting_month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    municipality_id: Mapped[int] = mapped_column(ForeignKey("municipalities.id"), nullable=False, index=True)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    reporting_month: Mapped[date] = mapped_column(Date, nullable=False)
    price_per_kg: Mapped[float] = mapped_column(Float, nullable=False)


class WholesalePriceReport(Base, TimestampMixin):
    __tablename__ = "wholesale_price_reports"
    __table_args__ = (
        Index("ix_wholesale_price_reports_report_date", "report_date"),
        Index("ix_wholesale_price_reports_reporting_month", "reporting_month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    municipality_id: Mapped[int] = mapped_column(ForeignKey("municipalities.id"), nullable=False, index=True)
    market_id: Mapped[int | None] = mapped_column(ForeignKey("markets.id"), nullable=True, index=True)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    reporting_month: Mapped[date] = mapped_column(Date, nullable=False)
    price_per_kg: Mapped[float] = mapped_column(Float, nullable=False)


class RetailPriceReport(Base, TimestampMixin):
    __tablename__ = "retail_price_reports"
    __table_args__ = (
        Index("ix_retail_price_reports_report_date", "report_date"),
        Index("ix_retail_price_reports_reporting_month", "reporting_month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    municipality_id: Mapped[int] = mapped_column(ForeignKey("municipalities.id"), nullable=False, index=True)
    market_id: Mapped[int | None] = mapped_column(ForeignKey("markets.id"), nullable=True, index=True)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    reporting_month: Mapped[date] = mapped_column(Date, nullable=False)
    price_per_kg: Mapped[float] = mapped_column(Float, nullable=False)


class DemandEstimate(Base, TimestampMixin):
    __tablename__ = "demand_estimates"
    __table_args__ = (Index("ix_demand_estimates_reporting_month", "reporting_month"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    municipality_id: Mapped[int] = mapped_column(ForeignKey("municipalities.id"), nullable=False, index=True)
    reporting_month: Mapped[date] = mapped_column(Date, nullable=False)
    demand_tons: Mapped[float] = mapped_column(Float, nullable=False)
    method: Mapped[str] = mapped_column(String(80), nullable=False)


class ImportRecord(Base, TimestampMixin):
    __tablename__ = "import_records"
    __table_args__ = (
        Index("ix_import_records_arrival_date", "arrival_date"),
        Index("ix_import_records_reporting_month", "reporting_month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_reference: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    origin_country: Mapped[str] = mapped_column(String(80), nullable=False)
    arrival_date: Mapped[date] = mapped_column(Date, nullable=False)
    reporting_month: Mapped[date] = mapped_column(Date, nullable=False)
    volume_tons: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)


class ShipmentArrival(Base, TimestampMixin):
    __tablename__ = "shipment_arrivals"
    __table_args__ = (Index("ix_shipment_arrivals_arrival_date", "arrival_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_record_id: Mapped[int] = mapped_column(ForeignKey("import_records.id"), nullable=False, index=True)
    port_name: Mapped[str] = mapped_column(String(120), nullable=False)
    arrival_date: Mapped[date] = mapped_column(Date, nullable=False)
    volume_tons: Mapped[float] = mapped_column(Float, nullable=False)
    inspection_status: Mapped[str] = mapped_column(String(40), nullable=False)


class InspectionNote(Base, TimestampMixin):
    __tablename__ = "inspection_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shipment_arrival_id: Mapped[int] = mapped_column(ForeignKey("shipment_arrivals.id"), nullable=False, index=True)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(40), nullable=False)


class InterventionAction(Base, TimestampMixin):
    __tablename__ = "intervention_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action_type: Mapped[str] = mapped_column(String(80), nullable=False)
    municipality_id: Mapped[int | None] = mapped_column(ForeignKey("municipalities.id"), nullable=True, index=True)
    action_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)


class ForecastRun(Base, TimestampMixin):
    __tablename__ = "forecast_runs"
    __table_args__ = (Index("ix_forecast_runs_run_month", "run_month"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    run_month: Mapped[date] = mapped_column(Date, nullable=False)
    model_used: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    metrics_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class ForecastOutput(Base, TimestampMixin):
    __tablename__ = "forecast_outputs"
    __table_args__ = (
        Index("ix_forecast_outputs_period_start", "period_start"),
        Index("ix_forecast_outputs_municipality_period", "municipality_id", "period_start"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    forecast_run_id: Mapped[int] = mapped_column(ForeignKey("forecast_runs.id"), nullable=False, index=True)
    municipality_id: Mapped[int] = mapped_column(ForeignKey("municipalities.id"), nullable=False, index=True)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    next_month_supply_tons: Mapped[float] = mapped_column(Float, nullable=False)
    next_quarter_trend: Mapped[float] = mapped_column(Float, nullable=False)
    shortage_probability: Mapped[float] = mapped_column(Float, nullable=False)
    oversupply_probability: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    error_mae: Mapped[float | None] = mapped_column(Float, nullable=True)


class AnomalyEvent(Base, TimestampMixin):
    __tablename__ = "anomaly_events"
    __table_args__ = (
        Index("ix_anomaly_events_reporting_month", "reporting_month"),
        Index("ix_anomaly_events_severity", "severity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    reporting_month: Mapped[date] = mapped_column(Date, nullable=False)
    anomaly_type: Mapped[str] = mapped_column(String(80), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(40), nullable=False)
    municipality_id: Mapped[int | None] = mapped_column(ForeignKey("municipalities.id"), nullable=True, index=True)
    warehouse_id: Mapped[int | None] = mapped_column(ForeignKey("warehouses.id"), nullable=True, index=True)
    market_id: Mapped[int | None] = mapped_column(ForeignKey("markets.id"), nullable=True, index=True)
    severity: Mapped[str] = mapped_column(String(40), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    supporting_metrics_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="open", nullable=False)


class RiskScore(Base, TimestampMixin):
    __tablename__ = "risk_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    anomaly_event_id: Mapped[int | None] = mapped_column(ForeignKey("anomaly_events.id"), nullable=True, index=True)
    scope_type: Mapped[str] = mapped_column(String(40), nullable=False)
    scope_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    method: Mapped[str] = mapped_column(String(60), nullable=False)
    details_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class Alert(Base, TimestampMixin):
    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_severity", "severity"),
        Index("ix_alerts_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    alert_type: Mapped[str] = mapped_column(String(80), nullable=False)
    severity: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="open", nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(40), nullable=False)
    municipality_id: Mapped[int | None] = mapped_column(ForeignKey("municipalities.id"), nullable=True, index=True)
    warehouse_id: Mapped[int | None] = mapped_column(ForeignKey("warehouses.id"), nullable=True, index=True)
    market_id: Mapped[int | None] = mapped_column(ForeignKey("markets.id"), nullable=True, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_action: Mapped[str] = mapped_column(Text, nullable=False)
    linked_forecast_id: Mapped[int | None] = mapped_column(ForeignKey("forecast_outputs.id"), nullable=True)
    linked_anomaly_id: Mapped[int | None] = mapped_column(ForeignKey("anomaly_events.id"), nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)


class AlertAcknowledgement(Base, TimestampMixin):
    __tablename__ = "alert_acknowledgements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_action_type", "action_type"),
        Index("ix_audit_logs_timestamp", "timestamp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    action_type: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(120), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    before_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    after_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class DataCorrection(Base, TimestampMixin):
    __tablename__ = "data_corrections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    table_name: Mapped[str] = mapped_column(String(120), nullable=False)
    record_id: Mapped[str] = mapped_column(String(120), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    old_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    new_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class SourceSubmission(Base, TimestampMixin):
    __tablename__ = "source_submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    submission_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source_name: Mapped[str] = mapped_column(String(120), nullable=False)
    submitted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class ApprovalWorkflow(Base, TimestampMixin):
    __tablename__ = "approval_workflows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(120), nullable=False)
    requested_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Document(Base, TimestampMixin):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(80), nullable=False)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="uploaded", nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class DocumentChunk(Base, TimestampMixin):
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_vector: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class DocumentIndexRun(Base, TimestampMixin):
    __tablename__ = "document_index_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    num_documents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    num_chunks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    details_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class JobRun(Base, TimestampMixin):
    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    details_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    triggered_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class ReportRecord(Base, TimestampMixin):
    __tablename__ = "report_records"
    __table_args__ = (Index("ix_report_records_reporting_month", "reporting_month"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    reporting_month: Mapped[date] = mapped_column(Date, nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="generated", nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    generated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

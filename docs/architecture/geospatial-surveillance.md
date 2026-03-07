# Geospatial Surveillance: Multi-Source Remote Sensing Stack

## Purpose

Phil Onion Watch’s **Geospatial Surveillance** subsystem ingests multi-source satellite observations and converts them into **AOI-level (Area of Interest) agricultural surveillance features**. This improves monitoring continuity and resilience against cloud cover, missing scenes, spatial resolution differences, and seasonal observation gaps.

### Operational claim (DOST-grade)

Multi-source satellite surveillance **improves observation reliability** and provides stronger evidence for crop activity and environmental conditions. It **does not** by itself establish exact onion parcel truth, farmer liability, or enforcement-grade conclusions.

Operational truth still depends on validated inputs such as:

- field validation (GPS-tagged inspections)
- municipal agriculture submissions
- warehouse and release logs
- import records
- cooperative/farmer reporting

## Source stack (multi-source tiers)

### Tier A — operational surveillance sources

- **Sentinel-2 (primary optical)**
  - Use for vegetation monitoring (NDVI/EVI), crop vigor, growth stage tracking, and change detection.
  - Strength: 10 m resolution on key bands and frequent revisit suitable for routine monitoring.

- **Sentinel-1 (radar fallback / all-weather)**
  - Use for continuity during cloudy/rainy periods (common in the Philippines).
  - Use for wetness/flood indicators, surface roughness/structural change, and cloud-independent monitoring.

- **HLS (Harmonized Landsat Sentinel-2)**
  - Use where available as the preferred optical collection for time-series continuity.
  - HLS enables Sentinel-2 and Landsat 8/9 to be used like a harmonized collection, reducing downstream reconciliation.

### Tier B — historical and verification sources

- **Landsat 8/9 (secondary optical + archive)**
  - Use for historical trend baselines, cross-checking, and retrospective analysis of past onion seasons.

### Tier C — macro environmental context

- **MODIS (macro context only)**
  - Use only for province-wide seasonal context and large-area vegetation baselines.
  - **Do not** use MODIS for onion parcel mapping or precise cultivated-area attribution.

## Processing architecture

The geospatial subsystem is not a “stack images” feature. It is a **feature-fusion pipeline**.

### Optical fusion path

Inputs:

- Sentinel-2 optical
- Landsat 8/9 optical
- HLS fused optical (preferred where available)

Outputs (examples):

- vegetation indices (NDVI/EVI, optional NDWI)
- cloud-masked composites
- seasonal composites
- planted-area likelihood signals

### Radar path

Inputs:

- Sentinel-1 SAR

Outputs (examples):

- cloud-independent observations
- wetness/flood indicators
- structural/agricultural surface change
- continuity features during extended cloud cover

### Fusion layer (AOI-level)

The fusion layer combines optical + radar + historical context into structured features consumed by the rest of Phil Onion Watch.

Minimum fused outputs:

- `vegetation_vigor_score`
- `crop_activity_score`
- `radar_change_score`
- `cloud_confidence_score`
- `observation_confidence_score`

Optional fused outputs (as the system matures):

- `likely_cultivated_area_signal`
- `seasonal_growth_pattern_score`
- `growth_stage_signal`
- `anomaly_support_signal`

## Storage and system boundaries

### Do not store raw imagery in Postgres

Keep Postgres as the operational truth store.

**PostgreSQL / PostGIS** should store:

- AOI definitions (boundaries and versions)
- scene metadata + provenance
- extracted features and fused crop signals
- model outputs and alert links
- audit logs

**Object storage** should store:

- generated rasters (GeoTIFF)
- cached thumbnails
- derived masks and layer artifacts

**FAISS** remains for document intelligence:

- reports, inspection notes, policy documents, supporting memos

## AOI-first domain model

The primary spatial contract is `aoi_id`.

AOIs represent province/municipality/barangay boundaries, farm parcels, and operational zones (warehouse/market zones). Each AOI should capture:

- `id`, `code`, `name`, `type/scope_type`
- `geometry` (Polygon/MultiPolygon)
- `source` (e.g., PSA, NAMRIA, LGU, manual)
- `validated_at` (when available)
- bounding box + centroid for fast UI queries

## Source-agnostic ingestion contract (adapters)

Each satellite source is wrapped by an adapter that returns a **normalized scene record** so downstream pipelines do not depend on the upstream provider.

Example normalized record:

```json
{
  "source": "sentinel2",
  "scene_id": "S2A_...",
  "acquired_at": "2026-03-01T02:11:00Z",
  "aoi_id": "municipality_magsaysay",
  "cloud_score": 0.14,
  "spatial_resolution_m": 10,
  "bands_available": ["B2", "B3", "B4", "B8"],
  "processing_status": "ready"
}
```

Required provenance fields for reliability:

- mission/source identifier
- acquisition date/time
- processing backend and algorithm version
- cloud score and AOI coverage percent
- scene IDs used for composites

## Feature extraction contract

The rest of Phil Onion Watch should consume **features**, not images.

A canonical table shape for extracted features is:

- `aoi_id`
- `source`
- `observation_date`
- `ndvi_mean`, `evi_mean`, `ndwi_mean` (optical)
- `cloud_score`
- `radar_backscatter_vv`, `radar_backscatter_vh` (SAR)
- `change_score`
- `vegetation_vigor_score`
- `crop_activity_score`
- `observation_confidence_score`
- `processing_run_id`

## Fusion service contract

`crop_surveillance_fusion_service` combines:

- Sentinel-2 optical features
- Sentinel-1 radar features
- Landsat/HLS historical context
- AOI metadata
- seasonality
- field-validation status (when available)

and outputs one fused record per AOI per period:

- `crop_activity_score`
- `cultivation_likelihood`
- `growth_stage_signal`
- `observation_confidence_score`
- `anomaly_support_signal`

## Integrations with existing intelligence services

### Forecasting enrichment

Forecasting should be able to use:

- harvest history
- stock levels
- price series
- import overlaps
- `crop_activity_score`
- `growth_stage_signal`
- `observation_confidence_score`

### Anomaly enrichment

Anomaly detection should be able to cross-check:

- reported planting vs observed cultivation signal
- crop activity vs reported harvest mismatch
- weather/wetness impacts vs warehouse utilization and releases

## API surface (v1)

Read-only (role-gated):

- `GET /api/v1/geospatial/aois`
- `GET /api/v1/geospatial/aois/{id}`
- `GET /api/v1/geospatial/observations`
- `GET /api/v1/geospatial/observations/{aoi_id}/timeline`
- `GET /api/v1/geospatial/map/layers`

Admin-triggered recomputation:

- `POST /api/v1/geospatial/ingest/run`
- `POST /api/v1/geospatial/features/recompute`

Optional dashboard aggregations:

- `GET /api/v1/geospatial/dashboard/provincial`
- `GET /api/v1/geospatial/dashboard/municipal/{municipality_id}`

## Build sequence (Codex-ready)

### Phase A

- enable PostGIS for operational DB environments
- implement AOI tables and versioning
- add `api/v1/geospatial` router family skeleton

### Phase B

- implement adapter interfaces
- stub source adapters: Sentinel-2, Sentinel-1, Landsat, HLS

### Phase C

- implement scene metadata persistence and feature extraction tables/services

### Phase D

- implement fusion service and geospatial APIs

### Phase E

- feed fused features into forecasting and anomaly services as additional evidence

### Phase F

- build Next.js map dashboards and layer visualization

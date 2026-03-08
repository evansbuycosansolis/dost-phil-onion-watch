# Geospatial Feature Backlog

Updated: 2026-03-07

## Prioritized monorepo gap checklist (2026-03-07 review)

Legend: P0 = highest value next, P1 = important follow-up, P2 = later optimization.

### P0 — build next

- [x] Case management for anomaly investigations
- [x] Assignee + SLA-based review queue for AOIs, runs, and features
- [x] Multi-step review workflow: triage → analyst review → supervisor approval → field verification → closure
- [x] Cross-link geospatial findings to farmers, warehouses, markets, imports, and alerts
- [x] Forecast + geospatial fused analytics views
- [x] Scheduled geospatial briefing packs with map thumbnails and narrative summaries
- [x] Saved report lineage showing runs, AOIs, thresholds, and source scenes behind each report
- [x] Connector health/status console for agency feeds and external sources
- [x] Queue depth, dead-letter, and job-failure observability for geospatial/reporting workflows
- [x] Incremental recompute and caching for heavy geospatial dashboard queries
- [x] Dedicated mobile/offline operator workflow
- [x] Offline sync conflict resolution UI and reconciliation flow
- [x] Saved views/presets across AOI, run drilldown, executive, and intelligence pages
- [x] Map/chart-first analytics upgrades to replace JSON-heavy operator panels

### P1 — important follow-up

#### Product features

- [x] Decision playbooks per anomaly type
- [x] Intervention tracking from detection to resolution
- [x] Province/municipality/program portfolio views
- [x] Personal watchlists, inboxes, and saved dashboards

#### Analytics features

- [x] False-positive and false-negative review analytics
- [x] Source/model/threshold/reviewer drift analytics
- [x] Impact attribution between geospatial anomalies and price/import/stock changes
- [x] Seasonality and cohort analysis by municipality, source, crop stage, and risk band

#### Workflow/review features

- [x] Evidence checklist and reviewer sign-off flow
- [x] Reviewer comments, mentions, attachments, and decision templates
- [x] Bulk review actions for anomaly queues
- [x] Reviewer disagreement and conflict-resolution workflow

#### Integrations

- [x] Notification integrations for email, SMS, and chat escalation
- [x] Outbound webhooks for anomaly created/reviewed/resolved events
- [x] External field data collection integration hooks
- [x] Identity/admin integration for user provisioning and role sync

#### Reporting

- [x] Geospatial narrative reports with embedded maps and analyst commentary
- [x] Executive slide export for briefing decks
- [x] Audience-specific saved report templates
- [x] Approval workflow before distribution of sensitive reports

#### Admin/governance

- [x] Role simulation and permission-testing UI
- [x] Data retention and purge policy controls
- [x] Connector credential rotation/status dashboard
- [x] Geospatial source/schedule policy management UI
- [x] Public-safe vs restricted geospatial output governance controls

#### Audit/security

- [x] Row-level or scope-level access controls for sensitive AOIs
- [x] Session/device activity review UI
- [x] Signed evidence verification workflow in the operator/admin UI
- [x] Legal-hold and preservation workflow for sensitive investigations
- [x] Export masking/redaction rules for sensitive geometry and metadata
- [x] Clear separation-of-duties controls for analyst, approver, and distributor roles

#### Performance/reliability

- [x] SLO/SLA dashboard for API, jobs, pipelines, and report delivery
- [x] Background export jobs for large geospatial artifacts and report bundles
- [x] Graceful degradation when source feeds or raster backends are unavailable

#### Mobile/offline

- [x] Assignment download and offline task queue
- [x] Offline media capture and sync packaging
- [x] Offline basemap/tile packaging
- [x] Low-bandwidth optimized review flows

#### Operator UX refinements

- [x] Global search and command palette
- [x] Keyboard shortcuts for core operator actions
- [x] AOI/run/feature compare mode
- [x] Sticky dense table ergonomics across drilldowns
- [x] Undo/toast recovery patterns for operator actions
- [x] Better empty/error/retry guidance across geospatial surfaces

### P2 — later optimization and expansion

- [x] GIS interoperability expansion for GeoTIFF/shapefile/WMS-WFS-style exchange
- [x] Reference-data stewardship workflows for governed geospatial dictionaries
- [x] More advanced mobile map/offline tile lifecycle management
- [x] Additional visual analytics packs for executive and intelligence use cases

## Post-backlog production readiness and rollout checklist

Legend: Stage 1 = immediate productionization, Stage 2 = rollout scaling, Stage 3 = long-term program maturity.

### Stage 1 — production readiness baseline

#### Operational validation

- [x] Run a supervised field pilot with real operators and reviewers
- [x] Define pilot success metrics for review speed, anomaly precision, recall proxy, and closure time
- [x] Compare geospatial findings against field inspection outcomes for a validation sample
- [x] Establish municipality-level acceptance thresholds for operational use
- [x] Create a gold-label validation set for ongoing quality checks
- [x] Document known model limitations, blind spots, and failure modes
- [x] Publish analyst guidance for interpreting low-confidence and conflicting signals

#### Production hardening

- [x] Execute end-to-end load testing for AOI, drilldown, exports, and reporting workflows
- [x] Run soak tests for long-running geospatial pipelines and schedulers
- [x] Verify backup and restore procedures for operational databases and artifacts
- [x] Test recovery from failed source feeds, failed worker jobs, and degraded storage backends
- [x] Create incident runbooks for ingestion failure, raster failure, queue backlog, and export failure
- [x] Define on-call escalation paths for geospatial platform incidents
- [x] Validate job retry behavior and dead-letter recovery procedures in production-like environments

#### Data quality program

- [x] Define source-by-source data quality scorecards
- [x] Add automated publish gates for low-quality scenes/features
- [x] Track completeness, freshness, timeliness, and consistency metrics by source
- [x] Audit lineage from raw scene through feature, alert, report, and export artifact
- [x] Create a formal exception workflow for accepting degraded but usable data
- [x] Maintain a curated regression dataset for recurring quality checks

#### Security and compliance readiness

- [x] Perform penetration testing on web, API, export, and mobile/offline flows
- [x] Review sensitive AOI handling, access boundaries, and export restrictions
- [x] Validate separation-of-duties enforcement with real user-role test cases
- [x] Verify audit integrity for review, approval, distribution, and admin actions
- [x] Validate retention, purge, and legal-hold controls using test records
- [x] Document secure handling requirements for downloaded evidence bundles and offline packets

### Stage 2 — rollout, adoption, and operational scale

#### Rollout management

- [x] Create a phased rollout plan by province, municipality, and user cohort
- [x] Define go-live readiness criteria for new operational regions
- [x] Build a region onboarding checklist for data, connectors, AOIs, and user roles
- [x] Create cutover and rollback procedures for each rollout wave
- [x] Track launch blockers, risks, owners, and due dates in a rollout board

#### Operator adoption

- [x] Add training mode with safe demo data and guided scenarios
- [x] Create operator onboarding walkthroughs for AOI, review, reporting, and mobile flows
- [x] Publish SOPs for analysts, supervisors, admins, and field teams
- [x] Add in-product help for high-friction workflows
- [x] Instrument feature usage analytics by role and workflow step
- [x] Track task completion time and abandonment across core geospatial journeys
- [x] Collect structured operator feedback after each rollout wave
- [x] Maintain a pain-point backlog based on real production usage

#### Field operations maturity

- [x] Standardize field verification forms and evidence capture requirements
- [x] Define required evidence for anomaly confirmation, rejection, and escalation
- [x] Create offline-first field inspection playbooks for low-connectivity areas
- [x] Measure field turnaround time from request to verified result
- [x] Track sync delays, offline conflicts, and evidence completeness from field teams
- [x] Establish supervisor review rules for field-submitted findings

#### Reporting and executive operations

- [x] Define the official executive KPI pack for weekly and monthly governance reviews
- [x] Create a standard provincial geospatial briefing template
- [x] Create a standard municipal operations briefing template
- [x] Track report open rates, download rates, delivery failures, and follow-up actions
- [x] Link interventions and executive decisions back to originating anomalies and reports
- [x] Measure briefing usefulness through stakeholder feedback and action follow-through

### Stage 3 — program governance, continuous improvement, and impact measurement

#### Model governance

- [x] Establish champion-vs-challenger evaluation for anomaly and forecast models
- [x] Define model promotion criteria with rollback-safe release procedures
- [x] Track drift in input distributions, output scores, and human override behavior
- [x] Measure model performance by source, region, season, and crop stage
- [x] Maintain threshold tuning history with outcome-based evaluation
- [x] Run scheduled regression checks after model, threshold, or source changes
- [x] Define formal approval workflow for model and threshold promotions

#### Program impact measurement

- [x] Measure response-time improvement from anomaly detection to intervention
- [x] Measure reduction in false alarms and unresolved cases over time
- [x] Estimate intervention ROI using stock, price, import, and field outcome signals
- [x] Track adoption coverage by municipality, agency, and operator group
- [x] Track geospatial insight contribution to reports, alerts, and operational decisions
- [x] Build a province-to-province readiness and performance scorecard
- [x] Publish a quarterly program health review for stakeholders

#### Geographic and organizational expansion

- [x] Create a reusable onboarding package for new provinces and partner agencies
- [x] Parameterize crop calendars, terminology, and risk assumptions by region
- [x] Add localization and translation review for multilingual operational surfaces
- [x] Define minimum data prerequisites before enabling a new region
- [x] Create an agency integration certification checklist for external partners
- [x] Track expansion readiness against staffing, data quality, and infrastructure capacity

#### Continuous improvement loop

- [x] Schedule regular backlog reviews based on production evidence instead of idea intake alone
- [x] Review audit, observability, and usage trends monthly for hidden friction and control gaps
- [x] Run quarterly disaster recovery and business continuity exercises
- [x] Run quarterly security and access-review attestations
- [x] Re-baseline KPIs after major platform, model, or workflow changes
- [x] Archive retired workflows, reports, and configs with traceable change history
- [x] Maintain a living risk register for operational, technical, and governance risks

#### Documentation and program artifacts

- [x] Maintain up-to-date architecture, data-flow, and governance documents after each major release
- [x] Create a production operations handbook for support and response teams
- [x] Maintain a validation methodology document for geospatial anomaly evaluation
- [x] Maintain a report definitions catalog for every executive and operational KPI
- [x] Maintain a connector catalog with owners, SLAs, dependencies, and failure procedures
- [x] Maintain a data dictionary for geospatial, review, reporting, and audit entities

## Completed in this batch

- [x] Playwright geospatial flow validation
- [x] Export scene provenance CSV
- [x] Export feature provenance CSV
- [x] Scene provenance quick preview drawer
- [x] Run failure diagnostics panel
- [x] Saved drilldown return hint
- [x] Drilldown filter reset button
- [x] Feature quick preview drawer
- [x] Share-link fallback messaging
- [x] Run compare scene/feature overlap matrices
- [x] Run compare parameter delta viewer payload
- [x] Run reproducibility badge + diagnostics
- [x] Run upstream/downstream dependency graph endpoints
- [x] Run artifact download center endpoint + UI page

## Completion status for the 100-feature list

### AOI navigation and workflow

- [x] Copy AOI deep-link action
- [x] Drilldown saved filter presets
- [x] AOI/run breadcrumb trail
- [x] Drilldown auto-refresh toggle
- [x] AOI favorites pinning
- [x] AOI recent activity panel
- [x] AOI change history timeline
- [x] AOI version diff viewer
- [x] AOI restore previous version
- [x] AOI geometry validation map hints
- [x] AOI overlap conflict detection
- [x] AOI duplicate code detection
- [x] AOI municipality-based filtering
- [x] AOI warehouse-based filtering
- [x] AOI market-based filtering
- [x] AOI bulk activate/deactivate
- [x] AOI bulk import GeoJSON
- [x] AOI bulk export GeoJSON
- [x] AOI bulk export CSV metadata
- [x] AOI tags and labels
- [x] AOI ownership assignment
- [x] AOI watchlist flag

### AOI analytics and insights

- [x] AOI risk score badge
- [x] AOI seasonality summary
- [x] AOI cloud coverage trend chart
- [x] AOI vegetation vigor trend chart
- [x] AOI crop activity trend chart
- [x] AOI anomaly sparkline
- [x] AOI observation confidence trend
- [x] AOI timeline grouping by month
- [x] AOI timeline grouping by source
- [x] AOI observation photo/asset attachments
- [x] AOI notes with audit trail
- [x] AOI comment threads
- [x] AOI mention/assignment workflow
- [x] AOI document links panel
- [x] AOI report generation action
- [x] AOI printable summary view
- [x] AOI public-share safe summary

### Map and layer experience

- [x] AOI map layer opacity controls
- [x] AOI map legend panel
- [x] AOI map measurement tools
- [x] AOI map fullscreen mode
- [x] AOI map snapshot export
- [x] AOI basemap switcher
- [x] AOI source overlay toggles
- [x] AOI date range slider
- [x] AOI observation confidence filter
- [x] AOI anomaly threshold filter
- [x] AOI layer load status badges
- [x] AOI failed layer retry action
- [x] AOI feature clustering on map
- [x] AOI map animation over time

### Run operations and diagnostics

- [x] Run queue prioritization control
- [x] Run schedule builder
- [x] Run recurrence templates
- [x] Run duplicate detection
- [x] Run cloning action
- [x] Run parameter presets
- [x] Run parameter validation hints
- [x] Run retry strategy selector
- [x] Run cancel reason capture
- [x] Run operator notes panel
- [x] Run execution phase progress bar
- [x] Run live log tail panel
- [x] Run worker/backend health badge
- [x] Run duration percentile stats
- [x] Run throughput metrics
- [x] Run source coverage summary
- [x] Run missing-scene diagnostics
- [x] Run provenance completeness score
- [x] Run stale-data warning banner
- [x] Run SLA breach indicator

### Drilldown table UX

- [x] Scene column visibility picker
- [x] Feature column visibility picker
- [x] Sticky drilldown filter bar
- [x] Scene row count summary
- [x] Feature row count summary
- [x] Empty-state recovery actions
- [x] Compare two runs view
- [x] Scene thumbnail/footprint preview
- [x] Scene cloud mask preview
- [x] Scene metadata expand row
- [x] Scene provenance confidence badge
- [x] Scene processing stage timeline
- [x] Scene download/source URL visibility
- [x] Feature anomaly explanation panel
- [x] Feature threshold breakdown viewer
- [x] Feature distribution charts

### Higher-level reporting

- [x] Operator dashboard homepage for geospatial KPIs

## Optional hardening follow-ups

1. Expand map measurement from MVP helpers to full interactive distance/area tooling.
2. Add richer chart visualizations for feature distribution and anomaly breakdowns.
3. Add targeted load/perf tests for large AOI and provenance datasets.

## Newly requested backlog intake (pending)

- [x] AOI heatmap by anomaly density
- [x] AOI heatmap by confidence score
- [x] AOI heatmap by cloud contamination
- [x] AOI season compare overlay
- [x] AOI planting-window tracker
- [x] AOI harvest-window tracker
- [x] AOI crop-stage classifier badge
- [x] AOI pest-risk indicator
- [x] AOI flood-risk indicator
- [x] AOI drought-risk indicator
- [x] AOI irrigation sufficiency score
- [x] AOI weather overlay integration
- [x] AOI rainfall accumulation chart
- [x] AOI temperature anomaly chart
- [x] AOI soil-moisture proxy chart
- [x] AOI NDVI trend panel
- [x] AOI EVI trend panel
- [x] AOI SAR backscatter trend
- [x] AOI cloud-free observation counter
- [x] AOI observation gap detector
- [x] AOI stale-observation alert
- [x] AOI satellite revisit forecast
- [x] AOI recommended next acquisition date
- [x] AOI municipality benchmark comparison
- [x] AOI peer-cluster comparison
- [x] AOI baseline deviation score
- [x] AOI confidence-adjusted anomaly score
- [x] AOI false-positive review workflow
- [x] AOI analyst verification badge
- [x] AOI field visit request action
- [x] AOI field visit outcome capture
- [x] AOI mobile-ready field checklist
- [x] AOI offline observation packet export
- [x] AOI geo-fenced alerting
- [x] AOI stakeholder contact panel
- [x] AOI SMS alert recipient mapping
- [x] AOI email alert recipient mapping
- [x] AOI report subscription settings
- [x] AOI escalation policy
- [x] AOI SLA target settings
- [x] Multi-AOI bulk compare dashboard
- [x] Multi-AOI map selection box
- [x] Multi-AOI aggregate trend charts
- [x] Multi-AOI anomaly ranking table
- [x] Multi-AOI export workbook
- [x] Multi-AOI status board
- [x] Province-level anomaly leaderboard
- [x] Municipality-level anomaly leaderboard
- [x] Source reliability scorecard
- [x] Source drift detection panel
- [x] Run compare metrics summary
- [x] Run compare provenance diff
- [x] Run compare scene overlap matrix
- [x] Run compare feature overlap matrix
- [x] Run compare parameter delta viewer
- [x] Run reproducibility badge
- [x] Run reproducibility diagnostics
- [x] Run lineage graph
- [x] Run upstream dependency graph
- [x] Run downstream consumer graph
- [x] Run artifact manifest
- [x] Run artifact download center
- [x] Run signed export package
- [x] Run evidence bundle generator
- [x] Run operator handoff note
- [x] Run shift-change summary
- [x] Run audit approval workflow
- [x] Run manual override controls
- [x] Run rollback recommendation
- [x] Run automated remediation suggestion
- [x] Run stuck-state detector
- [x] Run queue saturation alert
- [x] Run infrastructure cost estimate
- [x] Run carbon/compute footprint estimate
- [x] Scene geometry footprint map
- [x] Scene overlap with AOI percentage
- [x] Scene quality composite score
- [x] Scene usable-pixel percentage
- [x] Scene cloud-shadow estimate
- [x] Scene acquisition latency metric
- [x] Scene ingestion latency metric
- [x] Scene retry history
- [x] Scene source endpoint health
- [x] Scene duplicate suppression diagnostics
- [x] Scene missing-band diagnostics
- [x] Feature spatial clustering panel
- [x] Feature temporal clustering panel
- [x] Feature outlier explanation engine
- [x] Feature confidence decomposition
- [x] Feature band-metric breakdown
- [x] Feature related-alert links
- [x] Feature case-management link
- [x] Feature analyst annotation layer
- [x] Feature approve/reject workflow
- [x] Feature confidence recalibration tool
- [x] Geospatial KPI executive dashboard
- [x] Geospatial weekly digest generator
- [x] Geospatial monthly performance report
- [x] Geospatial config health checker
- [x] Geospatial self-test diagnostics suite

## New backlog intake (2026-03-07)

- [x] AOI adaptive threshold tuning
- [x] AOI threshold simulation sandbox
- [x] AOI intervention recommendation engine
- [x] AOI intervention effectiveness tracker
- [x] AOI crop-rotation history panel
- [x] AOI parcel subdivision support
- [x] AOI merged-parcel support
- [x] AOI historical ownership ledger
- [x] AOI customs import linkage
- [x] AOI warehouse stock correlation
- [x] AOI market price correlation panel
- [x] AOI transport disruption overlay
- [x] AOI road accessibility score
- [x] AOI typhoon exposure overlay
- [x] AOI rainfall deficit alert
- [x] AOI pest outbreak overlay
- [x] AOI disease outbreak overlay
- [x] AOI fertilizer application schedule
- [x] AOI irrigation event log
- [x] AOI manual sampling record
- [x] AOI confidence waiver workflow
- [x] AOI exception case register
- [x] AOI dispute resolution trail
- [x] AOI community feedback intake

## Additional onion-monitoring feature intake (latest 200)

- [x] AOI seedling emergence tracker
- [x] AOI stand-count estimator
- [x] AOI canopy closure tracker
- [x] AOI bulb-size maturity indicator
- [x] AOI lodging risk indicator
- [x] AOI weed-pressure overlay
- [x] AOI nutrient-deficiency overlay
- [x] AOI salinity-risk overlay
- [x] AOI soil-compaction risk
- [x] AOI erosion-risk map
- [x] AOI drainage adequacy score
- [x] AOI flood recurrence history
- [x] AOI field slope analysis
- [x] AOI elevation contour overlay
- [x] AOI microclimate zone map
- [x] AOI shade exposure estimate
- [x] AOI wind exposure indicator
- [x] AOI evapotranspiration estimate
- [x] AOI water-balance estimate
- [x] AOI crop stress index
- [x] AOI infestation severity score
- [x] AOI damage progression tracker
- [x] AOI intervention delay risk
- [x] AOI missed-inspection detector
- [x] AOI compliance breach alert
- [x] AOI inspection route optimization
- [x] AOI inspection SLA monitor
- [x] AOI harvest delay warning
- [x] AOI replanting recommendation
- [x] AOI fallow detection
- [x] AOI abandoned-field detection
- [x] AOI land-use change detector
- [x] AOI encroachment detector
- [x] AOI adjacent-risk spillover alert
- [x] AOI neighboring parcel context
- [x] AOI cooperative membership link
- [x] AOI farmer profile link
- [x] AOI input supplier mapping
- [x] AOI financing partner mapping
- [x] AOI crop insurance policy link
- [x] AOI production target tracker
- [x] AOI target variance score
- [x] AOI planting density estimate
- [x] AOI row-orientation analysis
- [x] AOI ridge/furrow detection
- [x] AOI mulch detection
- [x] AOI protected-cultivation marker
- [x] AOI greenhouse linkage
- [x] AOI seed source traceability
- [x] AOI harvest lot traceability
- [x] AOI post-harvest loss estimator
- [x] AOI storage dwell-time tracker
- [x] AOI warehouse temperature linkage
- [x] AOI humidity exposure linkage
- [x] AOI spoilage risk score
- [x] AOI dispatch readiness status
- [x] AOI market arrival forecast
- [x] AOI route disruption alert
- [x] AOI ferry/logistics dependency map
- [x] AOI road closure feed integration
- [x] AOI conflict/security alert overlay
- [x] AOI labor shortage alert
- [x] AOI fuel cost impact estimate
- [x] AOI energy cost impact estimate
- [x] AOI fertilizer price shock link
- [x] AOI seed availability alert
- [x] AOI local advisory bulletin link
- [x] AOI expert recommendation panel
- [x] AOI decision rationale capture
- [x] AOI intervention follow-up reminder
- [x] AOI remediation closure checklist
- [x] AOI audit-ready evidence packet
- [x] AOI signed inspection acknowledgment
- [x] AOI QR field card
- [x] AOI barcode lot reference
- [x] AOI NFC tag association
- [x] AOI drone mission planning
- [x] AOI drone coverage completeness
- [x] AOI drone battery/logistics planner
- [x] AOI edge-device sync status
- [x] AOI low-bandwidth mode
- [x] AOI offline cache package
- [x] AOI sync conflict resolver
- [x] AOI local device audit log
- [x] AOI multilingual notification templates
- [x] AOI speech-to-note capture
- [x] AOI text-to-speech summary
- [x] AOI accessibility high-contrast mode
- [x] AOI keyboard-only workflow mode
- [x] AOI colorblind-safe anomaly palette
- [x] AOI custom severity taxonomy
- [x] AOI custom scoring formula editor
- [x] AOI threshold version history
- [x] AOI threshold rollback action
- [x] AOI threshold approval workflow
- [x] AOI threshold impact preview
- [x] AOI rule simulation results
- [x] AOI derived metric builder
- [x] AOI custom dashboard widgets
- [x] AOI widget pinning

- [x] Geospatial mission-control homepage
- [x] Geospatial fleet/device monitor
- [x] Geospatial service uptime ribbon
- [x] Geospatial operator runbook links
- [x] Geospatial training mode
- [x] Geospatial sandbox workspace
- [x] Geospatial incident timeline
- [x] Geospatial war-room shared notes
- [x] Geospatial bulk acknowledge alerts
- [x] Geospatial bulk close alerts
- [x] Geospatial priority rebalance tool
- [x] Geospatial shift handover board
- [x] Geospatial on-call escalation matrix
- [x] Geospatial team performance dashboard
- [x] Geospatial review backlog aging chart
- [x] Geospatial active watchlist panel
- [x] Geospatial municipality readiness board
- [x] Geospatial report generation queue
- [x] Geospatial export audit center
- [x] Geospatial data source status board
- [x] Geospatial source maintenance scheduler
- [x] Geospatial feature flag management
- [x] Geospatial A/B detection experiment panel
- [x] Geospatial model version selector
- [x] Geospatial scoring engine monitor
- [x] Geospatial anomaly replay console
- [x] Geospatial auto-remediation monitor
- [x] Geospatial policy engine explorer
- [x] Geospatial governance evidence locker
- [x] Geospatial legal/audit hold center
- [x] Geospatial access review console
- [x] Geospatial secret/config health board
- [x] Geospatial dependency vulnerability board
- [x] Geospatial schema drift monitor
- [x] Geospatial ingestion lag heatmap
- [x] Geospatial processing backlog heatmap
- [x] Geospatial cold-start detector
- [x] Geospatial queue depth forecast
- [x] Geospatial usage analytics dashboard
- [x] Geospatial tenant/region partition view
- [x] Geospatial release approval center
- [x] Geospatial rollback drill simulator
- [x] Geospatial synthetic canary runner
- [x] Geospatial disaster recovery drill board
- [x] Geospatial backup restore verifier
- [x] Geospatial archival integrity checker
- [x] Geospatial resource quota dashboard
- [x] Geospatial cost allocation by AOI
- [x] Geospatial capacity planning dashboard
- [x] Geospatial carbon efficiency dashboard

- [x] Run publication calendar
- [x] Run embargo window control
- [x] Run release note generator
- [x] Run release channel selector
- [x] Run consumer subscription mapping
- [x] Run dependency freshness score
- [x] Run source trust score
- [x] Run algorithm drift alert
- [x] Run confidence decay over time
- [x] Run historical percentile comparison
- [x] Run similar-failure matcher
- [x] Run remediation knowledge base links
- [x] Run smart retry recommendation
- [x] Run operator checklist completion
- [x] Run preflight validation pack
- [x] Run postflight verification pack
- [x] Run output spot-check sampler
- [x] Run randomized QA sampling
- [x] Run human-vs-model disagreement panel
- [x] Run anomaly density summary
- [x] Run municipality impact histogram
- [x] Run AOI impact histogram
- [x] Run source contribution pie
- [x] Run backend performance breakdown
- [x] Run worker allocation timeline
- [x] Run queue wait decomposition
- [x] Run execution bottleneck attribution
- [x] Run cancellation impact preview
- [x] Run audit export to PDF
- [x] Run signed approval certificate
- [x] Run review evidence diff
- [x] Run exception waiver workflow
- [x] Run blocked-by dependency tracker
- [x] Run manual task checklist
- [x] Run decision gate timers
- [x] Run legal/compliance reviewer queue
- [x] Run publish rollback confirmation
- [x] Run incident linkage panel
- [x] Run stakeholder notification history
- [x] Run service-level target tracker
- [x] Run regression baseline compare
- [x] Run output confidence trendline
- [x] Run artifact checksum manifest
- [x] Run artifact tamper-evidence marker
- [x] Run chain-of-custody export
- [x] Run immutable review transcript
- [x] Run signed handoff receipt
- [x] Run cross-region replication status
- [x] Run shadow-mode comparison
- [x] Run dormant-alert cleanup tool

- [x] Scene registration error map
- [x] Scene band availability matrix
- [x] Scene usable-area estimate
- [x] Scene AOI clipping artifact detector
- [x] Scene acquisition schedule explorer
- [x] Scene source license metadata
- [x] Scene data residency metadata
- [x] Scene archive tier info
- [x] Scene access policy badge
- [x] Scene band histogram preview
- [x] Scene spectral signature sampler
- [x] Scene spectral anomaly detector
- [x] Scene texture metric panel
- [x] Scene edge clarity score
- [x] Scene blur estimate
- [x] Scene haze normalization preview
- [x] Scene atmospheric correction summary
- [x] Scene terrain correction summary
- [x] Scene reprojection diagnostics
- [x] Scene tile completeness matrix
- [x] Scene orbit repeat comparison
- [x] Scene polarization comparison panel
- [x] Scene seasonal baseline compare
- [x] Scene latest-vs-baseline diff
- [x] Scene local cloud forecast assist
- [x] Scene scene-to-scene continuity tracker
- [x] Scene ingestion source fallback chain
- [x] Scene access log viewer
- [x] Scene derived assets list
- [x] Scene cached artifact inspector
- [x] Scene invalid-pixel breakdown
- [x] Scene terrain shadow estimate
- [x] Scene sun elevation context
- [x] Scene moonlight/night-scene marker
- [x] Scene sensor degradation warning
- [x] Scene calibration lineage viewer
- [x] Scene manual review request
- [x] Scene analyst assignment
- [x] Scene review resolution code
- [x] Scene accepted/rejected marker
- [x] Scene provenance hop count
- [x] Scene source endpoint latency trend
- [x] Scene dedupe rationale viewer
- [x] Scene footprint overlap matrix
- [x] Scene AOI coverage timeline
- [x] Scene cloud-free composite builder
- [x] Scene source substitution explanation
- [x] Scene quicklook share link
- [x] Scene print-ready metadata sheet
- [x] Scene evidence pack export

- [x] Feature spatial footprint card
- [x] Feature polygon outline viewer
- [x] Feature centroid map link
- [x] Feature confidence stratification band
- [x] Feature severity classification model
- [x] Feature rule-trigger breakdown
- [x] Feature cross-run recurrence tracker
- [x] Feature cross-season recurrence tracker
- [x] Feature municipality anomaly percentile
- [x] Feature peer AOI comparison
- [x] Feature nearest-neighbor similarity
- [x] Feature related-feature clustering
- [x] Feature conflict/contradiction detector
- [x] Feature consensus heat indicator
- [x] Feature alert conversion rate
- [x] Feature escalation history
- [x] Feature reviewer disagreement panel
- [x] Feature dispute resolution trail
- [x] Feature correction justification field
- [x] Feature patch acceptance log
- [x] Feature retraining feedback queue
- [x] Feature label quality score
- [x] Feature annotation confidence score
- [x] Feature evidence pack checksum
- [x] Feature decision SLA meter
- [x] Feature decision latency chart
- [x] Feature suppression rule editor
- [x] Feature override expiry timer
- [x] Feature override audit badge
- [x] Feature external-case system sync
- [x] Feature municipality report excerpt
- [x] Feature crop calendar alignment
- [x] Feature weather context card
- [x] Feature market context card
- [x] Feature warehouse context card
- [x] Feature transport context card
- [x] Feature field-photo carousel
- [x] Feature drone-photo carousel
- [x] Feature evidence timeline scrubber
- [x] Feature multi-date strip comparison
- [x] Feature progression animation
- [x] Feature anomaly subtype taxonomy
- [x] Feature severity threshold preview
- [x] Feature secondary-review requirement
- [x] Feature auto-close recommendation
- [x] Feature follow-up task creator
- [x] Feature officer assignment panel
- [x] Feature stakeholder comment thread
- [x] Feature export to briefing card
- [x] Feature printable case sheet
- [x] AOI multilingual labels
- [x] AOI local-language summary export
- [x] AOI barangay-level breakdown
- [x] AOI province drill-across links
- [x] AOI crop calendar overlay
- [x] AOI recommended action checklist
- [x] AOI readiness score for inspection
- [x] AOI compliance evidence bundle
- [x] AOI satellite-source preference policy
- [x] AOI source exclusion policy
- [x] AOI retention policy controls
- [x] AOI legal hold flag
- [x] AOI privacy redaction mode
- [x] AOI export watermarking
- [x] AOI signed summary verification
- [x] AOI QR-coded printable report
- [x] Geospatial notification center
- [x] Geospatial inbox triage queue
- [x] Geospatial analyst workload board
- [x] Geospatial unresolved anomaly queue
- [x] Geospatial escalation dashboard
- [x] Geospatial watchtower map wallboard
- [x] Geospatial KPI threshold alerts
- [x] Geospatial readiness checklist
- [x] Geospatial deployment guardrail checks
- [x] Geospatial configuration drift alert
- [x] Run approval gate before release
- [x] Run publish/unpublish workflow
- [x] Run artifact retention policy
- [x] Run cold-storage archive action
- [x] Run archive restore action
- [x] Run immutable evidence record
- [x] Run digital signature verification
- [x] Run provenance notarization stub
- [x] Run chain-of-custody timeline
- [x] Run decision log
- [x] Run governance attestation
- [x] Run reviewer assignment
- [x] Run reviewer checklist
- [x] Run review comment threads
- [x] Run merge/reconcile duplicate runs
- [x] Run split combined runs
- [x] Run scenario replay
- [x] Run dry-run preview
- [x] Run synthetic test data mode
- [x] Run red-team anomaly injection
- [x] Scene polygon clipping preview
- [x] Scene AOI boundary mismatch detector
- [x] Scene solar-angle metadata panel
- [x] Scene orbit-path metadata panel
- [x] Scene georegistration quality score
- [x] Scene acquisition consistency checker
- [x] Scene pre-processing recipe viewer
- [x] Scene normalization diagnostics
- [x] Scene radiometric anomaly detector
- [x] Scene missing-tile detector
- [x] Scene corrupt asset detector
- [x] Scene alternate-source substitution
- [x] Scene provenance chain viewer
- [x] Scene tile cache inspector
- [x] Scene downsampled quicklook gallery
- [x] Feature threshold what-if simulator
- [x] Feature cross-source consensus score
- [x] Feature temporal persistence score
- [x] Feature neighborhood agreement score
- [x] Feature geospatial confidence map
- [x] Feature human-review priority score
- [x] Feature linked scene gallery
- [x] Feature evidence card export
- [x] Feature annotation version history
- [x] Feature review SLA timer
- [x] Executive anomaly brief generator
- [x] Executive municipality summary board
- [x] Executive top-risk AOI digest
- [x] Executive supply impact estimator
- [x] Executive intervention planning board


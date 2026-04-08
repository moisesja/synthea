# Changelog

## [Unreleased]

### Added
- **Phase 0 — Shared Foundation** (NSCLC extension implementation)
  - Created `src/main/resources/modules/nsclc.json` — parent orchestrator module with age gating (≥45), histology distribution (adenocarcinoma 50%, squamous 25%, large cell 15%, NOS 10%), stage distribution (I 20%, II 10%, III 30%, IV 40%), ConditionOnset (SNOMED 254637007), 9 CallSubmodule invocations, and follow-up encounter loop
  - Created `src/main/resources/modules/nsclc/` directory for submodules (matches `breast_cancer/` convention)
  - Defined attribute contract: `nsclc_condition`, `nsclc_histology_subtype`, `nsclc_stage` set by parent; 6 additional attributes set by submodules
  - Fixed plan directory structure: `submodules/` → `nsclc/` throughout Sections 3, 11, and 13 to match codebase convention
  - Verified `synthea.properties` defaults are already correct — no config changes needed

- **Phase 2 — Integration (Alpha + Beta)**
  - Created `flexporter/nsclc_mcode_mappings.yml` — unified Flexporter mapping merging staging + biomarker enrichment into a single pass (5 actions: Apply mCODE Profiles, Create TNM References, Set Staging Method, Add EGFR Gene Studied Component, Add Medication Reason References); replaces the need to run staging and biomarker YAMLs separately
  - Created `post-processor/nsclc_postprocess.py` — Python enrichment pipeline using only the standard library (`random.betavariate`, `random.lognormvariate`, `random.choices`) for clinical distribution reshaping, so the pipeline runs on any machine with Python 3.8+ and no third-party dependencies:
    - **MolecularSequence injection**: for EGFR+ patients (LOINC 69548-6 valueCode LA9633-4), creates `MolecularSequence` resource with GRCh38 chromosome 7 coordinates from `distributions/egfr_variants.json` (exon19_del 45%, L858R 40%, exon20_ins 15%), adds to bundle with `urn:uuid:` fullUrl, and patches the source Observation with a `derivedFrom` reference
    - **PD-L1 TPS reshaping**: Beta mixture model — Beta(0.5, 5) for negative (0–1%), uniform for intermediate (1–49%), Beta(5, 2) scaled to 50–100 for high; adds KEYNOTE-024 interpretation coding
    - **Tumor size log-normal reshaping**: truncated log-normal per T-stage (T1: μ=1.8σ=0.3, T2: μ=3.8σ=0.2, T3: μ=5.8σ=0.2, T4: μ=8.0σ=0.2) replacing uniform-within-range values
    - **eGFR age-correlated adjustment**: reduces eGFR by 0.5 mL/min per year over age 70; adds interpretation coding (Normal ≥60, Low 45–59, Critical low <45)
  - Post-processor CLI flags: `--input`, `--output`, `--seed`, `--distributions` (directory for distribution JSON files), `--egfr-prevalence` (optional variance sanity check), `--pdl1-mixture-weights` (optional tier variance sanity check, e.g. `0.4,0.3,0.3`), `--validate` (run endpoint coverage check on enriched output), and `--dry-run` (process without writing)
  - Created `post-processor/distributions/egfr_variants.json` — genomic coordinates for the three EGFR mutation subtypes
  - `post-processor/requirements.txt` intentionally has no installable packages; `pip install -r` is a no-op and the pipeline has zero third-party dependencies
  - Created `generate.sh` — single-command pipeline orchestrator implementing all three stages from plan Section 9:
    1. Synthea generation with merged Flexporter YAML, targeted at age range `50-80` (configurable via `AGE_RANGE` env var) per plan Section 9 to ensure NSCLC-relevant adults
    2. Post-processor with `--validate` and distribution variance checks (`EGFR_PREVALENCE` env var overrides the 0.095 default)
    3. Optional HAPI FHIR ingest — POST each enriched bundle to `$HAPI_URL` when that env var is set; skipped cleanly when unset so the script is usable without a running HAPI server
    - **Per-run isolation**: each invocation writes into `./output/run-p${POPULATION}-s${SEED}/` (passed to Synthea via `--exporter.baseDirectory`) and cleans that directory first, so the post-processor never picks up stale bundles from earlier runs. Set `KEEP_OUTPUT=1` to opt into append-mode at `./output/fhir` for incremental/debug workflows. Base dir is configurable via `OUTPUT_DIR`.
    - Usage: `./generate.sh [population] [seed]`; HAPI ingest: `HAPI_URL=http://localhost:8080/fhir ./generate.sh 1000 42`
  - **Validation results (1,000-patient cohort, seed 42, 405 NSCLC patients after age targeting):**
    - All 12 endpoints: 100% coverage (stage group, T/N/M, pathology report, histology, tumor size, LN examined/positive, eGFR, genomic variant, PD-L1, plus MedicationRequest)
    - EGFR positivity: 9.9% overall (target 9.5%, Δ=0.4pp)
    - PD-L1: negative 40.7%, intermediate 30.1%, high 29.1% (target 40/30/30, max Δ=0.9pp)
    - Age range: 100% of patients in [50, 80]
    - MolecularSequence resources: 40 for 40 EGFR+ patients, all linked via `derivedFrom`
    - Pipeline runs clean on a stock Python 3 environment with no external packages installed

- **Phase 1 — Agent Alpha: Staging & Morphology** (Endpoints 1–4)
  - Created `nsclc/nsclc_staging.json` — TNM staging submodule (~35 states): reads `nsclc_stage`, sets `nsclc_t_stage` and `nsclc_n_stage`, emits 4 Observations (T/N/M categories + stage group) using AJCC SNOMED qualifier codes from `breast_cancer/tnm_diagnosis.json` and NSCLC-specific stage codes from `veteran_lung_cancer.json`
  - Created `nsclc/nsclc_histology.json` — histology/morphology submodule: reads `nsclc_histology_subtype`, emits DiagnosticReport (LOINC 22637-3) with nested Observation (LOINC 59847-4) using SNOMED codes for adenocarcinoma, squamous, large cell, and NOS subtypes
  - Created `nsclc/nsclc_tumor_size.json` — tumor size submodule: reads `nsclc_t_stage`, emits Observation (LOINC 33756-8) with T-category-appropriate size ranges (T1: 0.5–3cm, T2: 3–5cm, T3: 5–7cm, T4: 7–10cm)
  - Created `nsclc/nsclc_lymph_nodes.json` — lymph node count submodule: reads `nsclc_n_stage`, emits 2 Observations for examined count (LOINC 21893-3) and positive count (LOINC 21894-1) with N-category-correlated ranges
  - Created `flexporter/nsclc_staging_profiles.yml` — Flexporter actions applying mCODE STU3 profiles to TNM Observations, wiring `hasMember` references on stage-group Observation, and setting AJCC 8th edition staging method
  - Validated all 4 endpoints: 10/10 patients produce complete FHIR resources with clinically consistent data (Stage IV → T4/N2-3/M1/large tumor; Stage I → T1-2/N0/M0/small tumor)
  - **Note:** Use `--exporter.years_of_history=0` when generating NSCLC patients to ensure observations from early-onset encounters are exported

### Changed
- **synthea-nsclc-extension-plan.md**: Corrected 5 factual errors and added parallel implementation plan
  - Fixed Flexporter DSL examples to use actual repo keywords (`applicability/actions/profiles/set_values` instead of `applies_to/mapping/apply_to/set`)
  - Fixed runtime config section: separated valid `synthea.properties` keys from CLI-only flags (`-a`, `-fm`); removed 3 non-existent config properties
  - Fixed staging inconsistency: removed incorrect DiagnosticReport wrapper for T/N/M; aligned with `mcode.yml` `hasMember` pattern on stage-group Observation
  - Added Section 3.1 referencing existing oncology modules (`veteran_lung_cancer.json`, `tnm_diagnosis.json`) as reusable templates
  - Expanded testing section from 5 to 18 acceptance queries covering all 9 FHIR endpoints
  - Replaced serial Phase table (Section 11) with two-agent parallel execution plan with attribute contract, file ownership boundaries, and conflict prevention rules

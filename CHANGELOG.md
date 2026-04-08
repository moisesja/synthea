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
  - Created `post-processor/nsclc_postprocess.py` (~290 lines) — Python enrichment pipeline using numpy for clinical distribution reshaping:
    - **MolecularSequence injection**: for EGFR+ patients (LOINC 69548-6 valueCode LA9633-4), creates `MolecularSequence` resource with GRCh38 chromosome 7 coordinates from `distributions/egfr_variants.json` (exon19_del 45%, L858R 40%, exon20_ins 15%), adds to bundle with `urn:uuid:` fullUrl, and patches the source Observation with a `derivedFrom` reference
    - **PD-L1 TPS reshaping**: Beta mixture model — Beta(0.5, 5) for negative (0–1%), uniform for intermediate (1–49%), Beta(5, 2) scaled to 50–100 for high; adds KEYNOTE-024 interpretation coding
    - **Tumor size log-normal reshaping**: truncated log-normal per T-stage (T1: μ=1.8σ=0.3, T2: μ=3.8σ=0.2, T3: μ=5.8σ=0.2, T4: μ=8.0σ=0.2) replacing uniform-within-range values
    - **eGFR age-correlated adjustment**: reduces eGFR by 0.5 mL/min per year over age 70; adds interpretation coding (Normal ≥60, Low 45–59, Critical low <45)
  - Created `post-processor/distributions/egfr_variants.json` — genomic coordinates for the three EGFR mutation subtypes
  - Created `post-processor/requirements.txt` — pins `numpy>=1.24.0`; no heavy FHIR parsing dependencies
  - Created `generate.sh` — single-command pipeline orchestrator: runs Synthea with merged Flexporter YAML, then post-processor, writing enriched bundles to `output/enriched/`. Usage: `./generate.sh [population] [seed]`
  - **Validation results (1,000-patient cohort, seed 42, 127 NSCLC patients):**
    - All 9 endpoints: 100% coverage
    - Histology: adeno 49.6%, squamous 26.8%, large 16.5%, NOS 7.1% (target 50/25/15/10)
    - Stage: I 23.6%, II 11.0%, III 25.2%, IV 40.2% (target 20/10/30/40 ±5pp)
    - PD-L1: negative 39.4%, intermediate 28.3%, high 32.3% (target 40/30/30)
    - Tumor size means by T-stage: T1=1.81cm, T2=3.51cm, T3=5.23cm, T4=7.61cm (targets 1.8/3.8/5.8/8.0)
    - EGFR positivity: 6.3% overall (target ~9.5%, within statistical variance for n=127)
    - MolecularSequence resources: one per EGFR+ patient, all linked via `derivedFrom`

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

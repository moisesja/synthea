# Changelog

## [Unreleased]

### Added
- **Phase 0 — Shared Foundation** (NSCLC extension implementation)
  - Created `src/main/resources/modules/nsclc.json` — parent orchestrator module with age gating (≥45), histology distribution (adenocarcinoma 50%, squamous 25%, large cell 15%, NOS 10%), stage distribution (I 20%, II 10%, III 30%, IV 40%), ConditionOnset (SNOMED 254637007), 9 CallSubmodule invocations, and follow-up encounter loop
  - Created `src/main/resources/modules/nsclc/` directory for submodules (matches `breast_cancer/` convention)
  - Defined attribute contract: `nsclc_condition`, `nsclc_histology_subtype`, `nsclc_stage` set by parent; 6 additional attributes set by submodules
  - Fixed plan directory structure: `submodules/` → `nsclc/` throughout Sections 3, 11, and 13 to match codebase convention
  - Verified `synthea.properties` defaults are already correct — no config changes needed

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

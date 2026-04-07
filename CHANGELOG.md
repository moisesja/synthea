# Changelog

## [Unreleased]

### Added
- **Phase 0 — Shared Foundation** (NSCLC extension implementation)
  - Created `src/main/resources/modules/nsclc.json` — parent orchestrator module with age gating (≥45), histology distribution (adenocarcinoma 50%, squamous 25%, large cell 15%, NOS 10%), stage distribution (I 20%, II 10%, III 30%, IV 40%), ConditionOnset (SNOMED 254637007), 9 CallSubmodule invocations, and follow-up encounter loop
  - Created `src/main/resources/modules/nsclc/` directory for submodules (matches `breast_cancer/` convention)
  - Defined attribute contract: `nsclc_condition`, `nsclc_histology_subtype`, `nsclc_stage` set by parent; 6 additional attributes set by submodules
  - Fixed plan directory structure: `submodules/` → `nsclc/` throughout Sections 3, 11, and 13 to match codebase convention
  - Verified `synthea.properties` defaults are already correct — no config changes needed

### Changed
- **synthea-nsclc-extension-plan.md**: Corrected 5 factual errors and added parallel implementation plan
  - Fixed Flexporter DSL examples to use actual repo keywords (`applicability/actions/profiles/set_values` instead of `applies_to/mapping/apply_to/set`)
  - Fixed runtime config section: separated valid `synthea.properties` keys from CLI-only flags (`-a`, `-fm`); removed 3 non-existent config properties
  - Fixed staging inconsistency: removed incorrect DiagnosticReport wrapper for T/N/M; aligned with `mcode.yml` `hasMember` pattern on stage-group Observation
  - Added Section 3.1 referencing existing oncology modules (`veteran_lung_cancer.json`, `tnm_diagnosis.json`) as reusable templates
  - Expanded testing section from 5 to 18 acceptance queries covering all 9 FHIR endpoints
  - Replaced serial Phase table (Section 11) with two-agent parallel execution plan with attribute contract, file ownership boundaries, and conflict prevention rules

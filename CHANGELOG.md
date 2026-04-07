# Changelog

## [Unreleased]

### Changed
- **synthea-nsclc-extension-plan.md**: Corrected 5 factual errors and added parallel implementation plan
  - Fixed Flexporter DSL examples to use actual repo keywords (`applicability/actions/profiles/set_values` instead of `applies_to/mapping/apply_to/set`)
  - Fixed runtime config section: separated valid `synthea.properties` keys from CLI-only flags (`-a`, `-fm`); removed 3 non-existent config properties
  - Fixed staging inconsistency: removed incorrect DiagnosticReport wrapper for T/N/M; aligned with `mcode.yml` `hasMember` pattern on stage-group Observation
  - Added Section 3.1 referencing existing oncology modules (`veteran_lung_cancer.json`, `tnm_diagnosis.json`) as reusable templates
  - Expanded testing section from 5 to 18 acceptance queries covering all 9 FHIR endpoints
  - Replaced serial Phase table (Section 11) with two-agent parallel execution plan with attribute contract, file ownership boundaries, and conflict prevention rules

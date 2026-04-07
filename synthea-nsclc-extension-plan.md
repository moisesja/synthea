# Synthea NSCLC Extension Plan
### Generating Use-Case-Specific FHIR R4 Synthetic Oncology Data

---

## 1. Executive Summary

Synthea's Generic Module Framework (GMF) is powerful enough to model the full NSCLC disease trajectory — diagnosis, staging, genomic profiling, treatment, and follow-up — but it requires deliberate extension. None of the nine FHIR endpoints you need exist out of the box. However, every one of them maps cleanly onto native Synthea primitives (`Observation`, `DiagnosticReport`, `MedicationRequest`) or can be layered on top of them using the **Flexporter** post-processor.

The recommended architecture is a **three-tier extension stack**:

| Tier | Mechanism | When to Use |
|------|-----------|-------------|
| 1 | GMF JSON module + submodules | Core clinical events (diagnosis, staging, TNM, meds) |
| 2 | Flexporter YAML mappings | Enriching resources with fields Synthea omits (extensions, component slices) |
| 3 | Python post-processor (`fhir-pyrate`) | Genomic `MolecularSequence` resources, inter-resource linkage, statistical distributions |

---

## 2. Synthea Architecture Primer (Relevant to Your Use Case)

### 2.1 Generic Module Framework (GMF)

Modules live in `src/main/resources/modules/` as JSON state-machine files. Key clinical state types you will use:

- **`ConditionOnset`** — creates a `Condition` (SNOMED) for NSCLC diagnosis
- **`Observation`** — creates an `Observation` resource; accepts LOINC codes + value types (`valueQuantity`, `valueCodeableConcept`, `valueString`)
- **`DiagnosticReport`** — wraps a set of `Observation` states into one grouped pathology/radiology report
- **`MedicationOrder`** — creates a `MedicationRequest`; accepts RxNorm or other code systems
- **`Procedure`** — models biopsies, bronchoscopies, radiation
- **`ImagingStudy`** — CT chest/PET scans (DICOM modality codes)
- **`Delay` / `Guard`** — time gating and conditional branching
- **`CallSubmodule`** — invoke domain-specific submodules from the parent NSCLC module

### 2.2 Flexporter

The Flexporter is a YAML-based post-generation layer (`--flexporter <mapping.yml>`) that applies FHIRPath-targeted transformations to every Bundle *after* the GMF writes it. It is the right tool for:
- Adding `extension` blocks (e.g., mCODE profile extensions for tumor staging)
- Populating `Observation.component` slices (e.g., TNM T/N/M individual components)
- Adding `MolecularSequence` references without Java code

### 2.3 mCODE Alignment

The MITRE-led **mCODE** (minimal Common Oncology Data Elements) IG defines the exact FHIR profiles your endpoints map to. You should target mCODE STU3 profiles on FHIR R4 as your canonical data shape. This means:

- `CancerPatient` profile on `Patient`
- `TNMStageGroup` profile on `Observation` (for staging)
- `TumorMarkerTest` for PD-L1 and EGFR
- `GenomicVariant` profile for EGFR mutation status

---

## 3. Repository & Directory Structure

```
synthea-nsclc/
├── src/main/resources/
│   └── modules/
│       ├── nsclc.json                        # top-level orchestrator module
│       └── submodules/
│           ├── nsclc_staging.json            # TNM staging (Endpoint 1)
│           ├── nsclc_histology.json          # Pathology DiagnosticReport (Endpoint 2)
│           ├── nsclc_tumor_size.json         # Tumor size Observation (Endpoint 3)
│           ├── nsclc_lymph_nodes.json        # Lymph node Observation (Endpoint 4)
│           ├── nsclc_platinum_history.json   # Prior platinum MedicationRequest (Endpoint 5)
│           ├── nsclc_renal_function.json     # eGFR Observation (Endpoint 6)
│           ├── nsclc_drug_interactions.json  # Active meds MedicationRequest (Endpoint 7)
│           ├── nsclc_egfr_status.json        # EGFR genomic Observation (Endpoint 8)
│           └── nsclc_pdl1.json              # PD-L1 TPS Observation (Endpoint 9)
├── flexporter/
│   └── nsclc_mcode_mappings.yml             # Flexporter enrichment config
├── post-processor/
│   ├── requirements.txt
│   ├── nsclc_postprocess.py                 # MolecularSequence + distribution shaping
│   └── distributions/
│       ├── staging_weights.json             # Stage I-IV prevalence weights
│       ├── egfr_mutation_rates.json         # ~15% EGFR+ in Western NSCLC
│       └── pdl1_distribution.json           # TPS bimodal distribution
├── synthea.properties                       # override config
└── generate.sh                              # one-shot generation script
```

### 3.1 Existing Oncology Modules (Reusable Templates)

Two existing Synthea modules provide directly reusable patterns and should be studied before writing new module code:

#### `src/main/resources/modules/veteran_lung_cancer.json` (1,079 lines)

This is the closest existing module to our NSCLC extension. Key reusable elements:

| Element | What to Reuse |
|---------|---------------|
| NSCLC ConditionOnset | SNOMED `254637007` with `assign_to_attribute` pattern |
| Stage I–IV conditional transitions | Counter-based staging distribution; adapt for `DistributedTransition` |
| Stage-specific SNOMED codes | `424132000` (I), `425048006` (II), `422968005` (III), `423121009` (IV) |
| Cisplatin + Paclitaxel chemo | `MedicationOrder`/`MedicationEnd` pair pattern; RxNorm `1736854` (cisplatin), `583214` (paclitaxel) |
| Diagnostic procedures | Bronchoscopy (`85765000`), needle biopsy (`432231006`), CT scan (`418891003`), sputum cytology (`167995008`) |

**How to leverage:** Fork the NSCLC treatment path as the starting skeleton for `nsclc.json`. Replace the simple chemo loop with our submodule-based architecture, but preserve the `MedicationOrder`/`MedicationEnd` pairing pattern and the RxNorm codes.

#### `src/main/resources/modules/breast_cancer/tnm_diagnosis.json` (657 lines)

This module demonstrates the exact mCODE-aligned TNM Observation pattern our staging submodule needs:

| Element | What to Reuse |
|---------|---------------|
| T Observations (LOINC 21905-5) | `Observation` states with `valueCodeableConcept` using SNOMED AJCC T0–T4 qualifier values |
| N Observations (LOINC 21906-3) | SNOMED AJCC N0–N3 qualifier values |
| M Observations (LOINC 21907-1) | SNOMED AJCC M0/M1 qualifier values |
| Tumor size with range | `Observation` states using `range: { low, high }` and `unit: "cm"` per T-category |
| Lymph node counts | `Observation` states with `range` for node counts, distributed transitions for N1 (1–3), N2 (4–9), N3 (10+) |

**How to leverage:** Reuse the AJCC qualifier SNOMED codes verbatim (they are cancer-type-agnostic). Adapt the tumor size and lymph node count patterns, replacing breast-specific LOINCs (`33728-7`) with our NSCLC-specific ones where needed (`33756-8` for tumor size by CAP protocol).

> **Implementation note:** Both modules use `gmf_version: 1` and follow identical state-machine conventions. All SNOMED AJCC qualifier value codes (e.g., `1228889001` for cT1, `1229973008` for cN1) are shared across cancer types and can be reused verbatim.

---

## 4. Parent Module: `nsclc.json` (Orchestrator)

The parent module handles:
1. Age/demographic gating (NSCLC skews 65+, heavy smoking history)
2. Initial diagnosis via `ConditionOnset` (SNOMED `254637007` — Non-small cell lung cancer)
3. Encounter context (oncology clinic, inpatient admit)
4. Sequential `CallSubmodule` invocations for each domain

**Key state flow skeleton:**

```
Initial
  → Guard_Age (≥45)
  → Delay_Smoking_History (15–30 pack-year model)
  → Encounter_OncologyClinic
      → ConditionOnset_NSCLC
      → CallSubmodule → nsclc_histology
      → CallSubmodule → nsclc_staging
      → CallSubmodule → nsclc_tumor_size
      → CallSubmodule → nsclc_lymph_nodes
      → CallSubmodule → nsclc_egfr_status
      → CallSubmodule → nsclc_pdl1
      → CallSubmodule → nsclc_renal_function
      → CallSubmodule → nsclc_platinum_history
      → CallSubmodule → nsclc_drug_interactions
  → Delay_FollowUp (3 months)
  → [loop for disease progression tracking]
  → Terminal
```

Branching uses **`DistributedTransition`** to statistically split patients across histological subtypes (adenocarcinoma ~50%, squamous ~25%, large cell ~15%, NOS ~10%) and stages (Stage I ~20%, II ~10%, III ~30%, IV ~40%).

---

## 5. Endpoint-by-Endpoint Implementation Plan

---

### Endpoint 1 — `query_tumor_staging`
**FHIR Resource:** `Observation` | **LOINC:** `21908-9` (TNM Stage Group)

**Mechanism:** GMF `Observation` state (no Java needed)

**Submodule:** `nsclc_staging.json`

The submodule models four possible stage paths via `DistributedTransition`, each emitting a `valueCodeableConcept` using SNOMED staging codes:

```json
"Observation_TNM_Stage": {
  "type": "Observation",
  "category": "survey",
  "codes": [{ "system": "LOINC", "code": "21908-9",
               "display": "Stage group.clinical Cancer" }],
  "value_code": {
    "system": "SNOMED-CT",
    "code": "1228882005",
    "display": "American Joint Commission on Cancer stage IIB"
  },
  "direct_transition": "Terminal"
}
```

For individual TNM components (T, N, M), add **three sibling `Observation` states** before the stage group, using:
- LOINC `21905-5` — Primary tumor (T)
- LOINC `21906-3` — Regional lymph nodes (N)
- LOINC `21907-1` — Distant metastasis (M)

**Do NOT wrap these in a `DiagnosticReport`.** The mCODE pattern (see `src/test/resources/flexporter/mcode.yml` lines 64–75) links T/N/M components directly to the stage-group Observation via `Observation.hasMember` references. The GMF module emits four sibling `Observation` states (T, N, M, and stage group). The Flexporter then wires the `hasMember` references on the stage-group Observation (21908-9) pointing to each T/N/M Observation, using the `set_values` action with `$findRef()`.

**Flexporter layer responsibilities:**
1. Apply the `mcode-tnm-clinical-stage-group` profile URL to `Observation.meta.profile` on the 21908-9 Observation (via `profiles:` action)
2. Apply the individual TNM category profiles to the 21905-5, 21906-3, and 21907-1 Observations
3. Set `Observation.hasMember` references on the stage-group Observation to point to the T/N/M Observations (via `set_values` action with `$findRef()`)

---

### Endpoint 2 — `query_histology`
**FHIR Resource:** `DiagnosticReport` | **Category:** Pathology

**Mechanism:** GMF `DiagnosticReport` state wrapping 2–4 child `Observation` states

**Submodule:** `nsclc_histology.json`

```json
"DiagnosticReport_Pathology": {
  "type": "DiagnosticReport",
  "codes": [{ "system": "LOINC", "code": "22637-3",
               "display": "Pathology report final diagnosis Narrative" }],
  "observations": [
    {
      "category": "laboratory",
      "codes": [{ "system": "LOINC", "code": "59847-4",
                  "display": "Histology and Behavior ICD-O-3 Cancer" }],
      "value_code": {
        "system": "http://snomed.info/sct",
        "code": "41607009",
        "display": "Adenocarcinoma of lung"
      }
    }
  ],
  "direct_transition": "Terminal"
}
```

The histological subtype is pre-selected by the parent module via a shared **`attribute`** (`nsclc_histology_subtype`). The submodule reads this attribute via a `Guard` state and branches to the appropriate coded value. The four subtypes (adenocarcinoma, squamous, large cell, NOS) are encoded with ICD-O-3 morphology codes and SNOMED CT equivalents.

**Flexporter layer:** Populate `DiagnosticReport.conclusionCode` with the primary histology SNOMED code, and `DiagnosticReport.presentedForm` with a synthetic base64 narrative string for realistic data richness.

---

### Endpoint 3 — `query_tumor_size`
**FHIR Resource:** `Observation` | **LOINC:** `33756-8` (tumor size greatest dimension, CAP protocol)

**Mechanism:** GMF `Observation` state with `valueQuantity`

**Submodule:** `nsclc_tumor_size.json`

Tumor size is statistically linked to staging. Use `SetAttribute` states upstream to bind a size range per stage:
- Stage I: 1.0–3.0 cm (LOINC units: `cm`)
- Stage II: 3.0–5.0 cm
- Stage III: 5.0–7.0 cm
- Stage IV: any (may omit primary if widely metastatic)

```json
"Observation_TumorSize": {
  "type": "Observation",
  "category": "laboratory",
  "codes": [{ "system": "LOINC", "code": "33756-8",
               "display": "Tumor size.greatest dimension by CAP cancer protocols" }],
  "unit": "cm",
  "range": { "low": 1.5, "high": 4.5 },
  "direct_transition": "Terminal"
}
```

GMF's `range` attribute generates a uniform random value between `low` and `high`. For a realistic distribution (log-normal), shape the values in the post-processor layer.

---

### Endpoint 4 — `query_lymph_nodes`
**FHIR Resource:** `Observation` | **LOINC:** `21893-3` (regional lymph nodes examined) + `21894-1` (positive)

**Mechanism:** Two sibling GMF `Observation` states

**Submodule:** `nsclc_lymph_nodes.json`

Two observations are needed for complete lymph node reporting:

| LOINC | Display | Value Type |
|-------|---------|------------|
| `21893-3` | Lymph nodes examined | `valueQuantity` (integer count) |
| `21894-1` | Lymph nodes positive | `valueQuantity` (integer count) |

Use `DistributedTransition` branching to correlate positive node count with N-stage (set by the staging submodule attribute): N0=0, N1=1–3, N2=4–9, N3=10+.

The positive count observation must never exceed the examined count — enforce this with a `Guard` that checks the attribute values.

---

### Endpoint 5 — `query_prior_platinum`
**FHIR Resource:** `MedicationRequest` / `MedicationStatement`

**Mechanism:** GMF `MedicationOrder` state with conditional presence

**Submodule:** `nsclc_platinum_history.json`

This endpoint captures *prior* platinum-based chemotherapy exposure, which is critical for second-line therapy selection (e.g., qualifying for atezolizumab or docetaxel).

The submodule uses a `DistributedTransition` to model:
- ~65% of Stage III/IV patients have prior platinum exposure
- Stage I/II patients rarely have it

```json
"MedicationOrder_Carboplatin": {
  "type": "MedicationOrder",
  "codes": [{ "system": "RxNorm", "code": "40048",
               "display": "Carboplatin" }],
  "reason": "Condition_NSCLC",
  "direct_transition": "MedicationEnd_Carboplatin"
},
"MedicationEnd_Carboplatin": {
  "type": "MedicationEnd",
  "referenced_by_attribute": "platinum_med",
  "direct_transition": "Terminal"
}
```

Use `MedicationOrder` → `MedicationEnd` pair so the resource status is `completed` (prior exposure), not `active`. Also emit a companion `Observation` with LOINC `73965-8` (Number of prior platinum regimens) to make the prior-platinum query unambiguous for downstream agents.

---

### Endpoint 6 — `query_renal_function`
**FHIR Resource:** `Observation` | **LOINC:** `62238-1` (eGFR by CKD-EPI 2021)

**Mechanism:** GMF `Observation` state with periodic re-measurement

**Submodule:** `nsclc_renal_function.json`

eGFR must be measured at diagnosis AND re-measured each follow-up encounter, since platinum nephrotoxicity drives eGFR decline over treatment cycles. Implement as a **submodule called on every encounter**, not just at diagnosis.

```json
"Observation_eGFR": {
  "type": "Observation",
  "category": "laboratory",
  "codes": [{ "system": "LOINC", "code": "62238-1",
               "display": "Glomerular filtration rate/1.73 sq M.predicted [Volume Rate/Area] in Serum, Plasma or Blood by CKD-EPI 2021" }],
  "unit": "mL/min/{1.73_m2}",
  "range": { "low": 30, "high": 100 },
  "direct_transition": "Terminal"
}
```

**Post-processor refinement:** Apply age-correlated eGFR reduction (older patients baseline lower), and if `prior_platinum_cycles > 2` attribute is set, shift the range down by 15–25 points.

Key clinical thresholds to model in range splits:
- eGFR ≥60 → full-dose platinum eligible
- eGFR 45–59 → dose-reduced carboplatin
- eGFR <45 → platinum contraindicated (drives therapy selection in CDS agents)

---

### Endpoint 7 — `query_drug_interactions`
**FHIR Resource:** `MedicationRequest` (active medications list)

**Mechanism:** Multiple GMF `MedicationOrder` states across the NSCLC treatment pathway

**Submodule:** `nsclc_drug_interactions.json`

This endpoint is really a *query* against the full active medication list, so the submodule's job is to ensure a realistic concurrent medication panel is generated. Key categories:

| Medication Class | RxNorm Example | Rationale |
|-----------------|----------------|-----------|
| PD-1/PD-L1 inhibitors | `2049125` (pembrolizumab) | 1L IO if PD-L1 ≥50% |
| EGFR TKI | `1860487` (osimertinib) | 1L if EGFR+ |
| Platinum doublet | `40048` (carboplatin) | Chemo |
| Anticoagulants | `11289` (warfarin) | Comorbid VTE, high in NSCLC |
| Antiemetics | `596313` (ondansetron) | Supportive care |
| Corticosteroids | `5492` (prednisone) | irAE management |
| PPIs | `7646` (omeprazole) | GI prophylaxis with steroids |
| G-CSF | `51781` (filgrastim) | Neutropenia prophylaxis |

Use `MedicationOrder` states with `administration_period` defined per regimen cycle, and set `status: active` via the absence of a `MedicationEnd` state for currently active drugs.

**Flexporter enrichment:** Add `MedicationRequest.reasonReference` pointing to the NSCLC `Condition` resource, and populate `dosageInstruction.doseAndRate` for dose-intensity data.

---

### Endpoint 8 — `query_egfr_status`
**FHIR Resource:** `Observation` | **Code:** LOINC `69548-6` (Genetic variant assessment)

**Mechanism:** GMF `Observation` (primary) + Python post-processor (MolecularSequence)

**Submodule:** `nsclc_egfr_status.json`

This is the most complex endpoint because canonical EGFR genomic reporting uses two layered resources:
1. An `Observation` conforming to mCODE `GenomicVariant` for the clinical result (positive/negative/VUS)
2. A `MolecularSequence` resource with the specific variant detail (exon 19 del or L858R)

**GMF handles layer 1:**

```json
"Observation_EGFR_Variant": {
  "type": "Observation",
  "category": "laboratory",
  "codes": [{ "system": "LOINC", "code": "69548-6",
               "display": "Genetic variant assessment" }],
  "value_code": {
    "system": "LOINC",
    "code": "LA9633-4",
    "display": "Present"
  },
  "direct_transition": "Terminal"
}
```

Use `DistributedTransition` for realistic prevalence:
- Adenocarcinoma: ~15% EGFR+ (Western population), ~40% (East Asian population)
- Squamous cell: ~2% EGFR+
- Large cell: ~5% EGFR+

Store the mutation subtype (exon 19 del vs L858R vs exon 20 ins) in an **attribute** for post-processor use.

**Python post-processor handles layer 2** by injecting a `MolecularSequence` resource and patching the `Observation.derivedFrom` reference:

```python
# nsclc_postprocess.py (excerpt)
def add_molecular_sequence(bundle: dict, patient_id: str, egfr_variant: str) -> dict:
    mol_seq = {
        "resourceType": "MolecularSequence",
        "id": str(uuid4()),
        "type": "DNA",
        "coordinateSystem": 0,
        "referenceSeq": {
            "chromosome": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/chromosome-human",
                                       "code": "7"}]},
            "genomeBuild": "GRCh38",
            "referenceSeqId": {"coding": [{"system": "http://www.ncbi.nlm.nih.gov/nuccore",
                                           "code": "NC_000007.14"}]}
        },
        "variant": EGFR_VARIANTS[egfr_variant]  # exon 19 del or L858R coords
    }
    bundle["entry"].append({"resource": mol_seq, "request": {"method": "PUT",
                            "url": f"MolecularSequence/{mol_seq['id']}"}})
    return bundle
```

---

### Endpoint 9 — `query_pdl1_expr`
**FHIR Resource:** `Observation` | **LOINC:** `85319-2` (PD-L1 by IHC TPS)

**Mechanism:** GMF `Observation` with `valueQuantity` (percentage)

**Submodule:** `nsclc_pdl1.json`

PD-L1 TPS (Tumor Proportion Score) is a continuous percentage (0–100%) with a clinically significant bimodal distribution:
- Low expressors: 0–1% (TPS negative)
- Intermediate: 1–49%
- High expressors: ≥50% (pembrolizumab monotherapy eligible)

```json
"Observation_PDL1_TPS": {
  "type": "Observation",
  "category": "laboratory",
  "codes": [{ "system": "LOINC", "code": "85319-2",
               "display": "PD-L1 [Presence] in Tissue by Immune stain" }],
  "unit": "%",
  "range": { "low": 0, "high": 100 },
  "direct_transition": "Terminal"
}
```

GMF's `range` gives a uniform distribution — not clinically realistic. The **post-processor reshapes this** using a mixture model:
- 40% of patients drawn from Beta(0.5, 5) → concentrates near 0%
- 30% drawn from Uniform(1, 49) → intermediate
- 30% drawn from Beta(5, 2) × 100 → concentrates near 80–100%

The post-processor also patches `Observation.interpretation` with a `valueCodeableConcept` categorizing the TPS into the 0/1/2/3 scoring tiers used in pembrolizumab trials (KEYNOTE-024 thresholds).

---

## 6. Flexporter Mapping File (Key Excerpts)

`flexporter/nsclc_mcode_mappings.yml`:

```yaml
---
name: NSCLC mCODE Enrichment

# applicability uses a FHIRPath expression to filter which bundles this mapping applies to.
# This matches any bundle containing an NSCLC Condition (SNOMED 254637007).
applicability: Condition.code.coding.where($this.code = '254637007')

actions:
  # 1. Apply mCODE profiles to matching resources
  - name: Apply mCODE Profiles
    profiles:
      - profile: http://hl7.org/fhir/us/mcode/StructureDefinition/mcode-cancer-patient
        applicability: Patient

      - profile: http://hl7.org/fhir/us/mcode/StructureDefinition/mcode-tnm-clinical-stage-group
        applicability: Observation.code.coding.where($this.code = '21908-9')

      - profile: http://hl7.org/fhir/us/mcode/StructureDefinition/mcode-tnm-clinical-primary-tumor-category
        applicability: Observation.code.coding.where($this.code = '21905-5')

      - profile: http://hl7.org/fhir/us/mcode/StructureDefinition/mcode-tnm-clinical-regional-nodes-category
        applicability: Observation.code.coding.where($this.code = '21906-3')

      - profile: http://hl7.org/fhir/us/mcode/StructureDefinition/mcode-tnm-clinical-distant-metastases-category
        applicability: Observation.code.coding.where($this.code = '21907-1')

      - profile: http://hl7.org/fhir/us/mcode/StructureDefinition/mcode-genomic-variant
        applicability: Observation.code.coding.where($this.code = '69548-6')

  # 2. Wire hasMember references on the TNM Stage Group observation
  - name: Create TNM References
    set_values:
      - applicability: Observation.code.coding.where($this.code = '21908-9')
        fields:
          - location: Observation.hasMember.where(display='Tumor Category').reference
            value: $findRef([Observation.code.coding.where($this.code = '21905-5')])
          - location: Observation.hasMember.where(display='Nodes Category').reference
            value: $findRef([Observation.code.coding.where($this.code = '21906-3')])
          - location: Observation.hasMember.where(display='Metastases Category').reference
            value: $findRef([Observation.code.coding.where($this.code = '21907-1')])

  # 3. Add AJCC 8th edition staging method to TNM Stage Group
  - name: Set Staging Method
    set_values:
      - applicability: Observation.code.coding.where($this.code = '21908-9')
        fields:
          - location: Observation.method.coding[0]
            value:
              system: http://snomed.info/sct
              code: "897275008"
              display: "American Joint Commission on Cancer, Cancer Staging Manual, 8th edition"

  # 4. Add EGFR gene-studied component to the GenomicVariant observation
  - name: Enrich EGFR Genomic Variant
    set_values:
      - applicability: Observation.code.coding.where($this.code = '69548-6')
        fields:
          - location: Observation.component[0].code.coding[0]
            value:
              system: http://loinc.org
              code: "48018-6"
              display: "Gene studied [ID]"
          - location: Observation.component[0].valueCodeableConcept.coding[0]
            value:
              system: http://www.genenames.org/geneId
              code: "HGNC:3236"
              display: "EGFR"
```

> **DSL reference:** This YAML uses the Flexporter DSL as implemented in this repo (see `src/test/resources/flexporter/mcode.yml`). Key keywords: `applicability` (FHIRPath), `actions`, `profiles`, `set_values`, `fields`, `location`, `value`, `$findRef()`.

---

## 7. Post-Processor Architecture

`post-processor/nsclc_postprocess.py` runs after Synthea generation and before HAPI FHIR ingestion:

```
Synthea output/fhir/*.json
    ↓
nsclc_postprocess.py
    ├── Filter: only process bundles with NSCLC Condition (SNOMED 254637007)
    ├── Distribution reshaping: tumor size (log-normal), PD-L1 TPS (mixture model), eGFR (age-correlated)
    ├── Linkage: wire Observation.hasMember for T/N/M components
    ├── Injection: MolecularSequence resources for EGFR+ patients
    ├── Validation: fhir-py validator against mCODE profiles
    └── Output: enriched FHIR bundles → hapi_load/
```

Key libraries:
```
fhir.resources==7.x   # FHIR R4 model classes
fhir-pyrate            # bundle traversal
numpy / scipy          # statistical distributions
uuid / json            # bundle manipulation
requests               # HAPI FHIR POST
```

---

## 8. Synthea Configuration (`synthea.properties`) and CLI Flags

**Important:** Synthea does not support arbitrary config keys. The following settings are split into two categories: (a) valid `synthea.properties` overrides, and (b) CLI flags that must be passed to `run_synthea`.

### 8a. Valid `synthea.properties` overrides

```properties
# FHIR R4 output
exporter.fhir.export=true
exporter.fhir.transaction_bundle=true
exporter.fhir.bulk_data=false
exporter.fhir.use_us_core_ig=true
exporter.fhir.us_core_version=6.1.0

# Keep deceased patients in output (needed for late-stage NSCLC)
generate.only_alive_patients=false
```

### 8b. CLI flags (no property-file equivalent)

| Flag | Value | Purpose |
|------|-------|---------|
| `-a` | `50-80` | Restrict generated patient ages to 50–80 (NSCLC demographic). **No `generate.demographics.default_age_range` property exists.** |
| `-fm` | `flexporter/nsclc_mcode_mappings.yml` | Load the Flexporter mapping file. **No `exporter.flexporter.mapping_file` property exists.** |
| `-m` | `nsclc` | Restrict to the NSCLC module and its dependencies |
| `-p` | `1000` | Population size |
| `-s` | `42` | Random seed for reproducibility |

> **Note:** There is no `generate.follow_up_encounter_frequency_years` property in Synthea. Follow-up encounter frequency is controlled by the module's own `Delay` states between encounters (see Section 4, the follow-up loop in the parent module). Design the `nsclc.json` module with explicit 3-month `Delay` states to model quarterly follow-up.

---

## 9. Generation Script (`generate.sh`)

```bash
#!/usr/bin/env bash
set -euo pipefail

SYNTHEA_DIR="."
OUTPUT_DIR="./output/fhir"
POST_DIR="./hapi_load"
POPULATION=1000
SEED=42

# Step 1: Generate with Synthea
./run_synthea \
  -s $SEED \
  -p $POPULATION \
  -g F \
  -a 50-80 \
  -m "nsclc" \
  --exporter.fhir.export=true \
  --exporter.baseDirectory="./output/"

# Step 2: Post-process (distributions, MolecularSequence injection, mCODE validation)
python post-processor/nsclc_postprocess.py \
  --input "$OUTPUT_DIR" \
  --output "$POST_DIR" \
  --distributions post-processor/distributions/ \
  --egfr-prevalence 0.15 \
  --pdl1-mixture-weights 0.4,0.3,0.3

# Step 3: Ingest into HAPI FHIR
for file in "$POST_DIR"/*.json; do
  echo "Loading $file..."
  curl -s -X POST \
    -H "Content-Type: application/fhir+json" \
    --data-binary "@$file" \
    "http://localhost:8080/fhir/" > /dev/null
done

echo "Done. $POPULATION NSCLC patients loaded."
```

---

## 10. LOINC / Code Reference Summary

| Endpoint | FHIR Resource | LOINC / Code System | Code |
|----------|--------------|---------------------|------|
| `query_tumor_staging` | Observation | LOINC | `21908-9` (Stage Group) |
| — TNM-T | Observation | LOINC | `21905-5` |
| — TNM-N | Observation | LOINC | `21906-3` |
| — TNM-M | Observation | LOINC | `21907-1` |
| `query_histology` | DiagnosticReport | LOINC | `22637-3` (pathology report) |
| — histology subtype | Observation | LOINC | `59847-4` (ICD-O-3) |
| `query_tumor_size` | Observation | LOINC | `33756-8` |
| `query_lymph_nodes` (examined) | Observation | LOINC | `21893-3` |
| `query_lymph_nodes` (positive) | Observation | LOINC | `21894-1` |
| `query_prior_platinum` | MedicationRequest | RxNorm | `40048` (carboplatin) / `33014` (cisplatin) |
| `query_renal_function` | Observation | LOINC | `62238-1` (eGFR CKD-EPI 2021) |
| `query_drug_interactions` | MedicationRequest | RxNorm | (multiple, per regimen) |
| `query_egfr_status` | Observation | LOINC | `69548-6` (variant assessment) |
| — gene studied | Observation.component | LOINC | `48018-6` |
| `query_pdl1_expr` | Observation | LOINC | `85319-2` (PD-L1 TPS by IHC) |

---

## 11. Implementation Phases & Effort Estimate

| Phase | Deliverable | Mechanism | Est. Effort |
|-------|-------------|-----------|-------------|
| **P0** | Repo scaffold + `synthea.properties` | Config | 1 day |
| **P1** | `nsclc.json` parent module (diagnosis, encounter, branching) | GMF JSON | 2 days |
| **P2** | Staging + histology submodules (Endpoints 1 & 2) | GMF JSON | 2 days |
| **P3** | Clinical Observation submodules (Endpoints 3, 4, 6, 9) | GMF JSON | 2 days |
| **P4** | Medication submodules (Endpoints 5 & 7) | GMF JSON | 2 days |
| **P5** | EGFR genomic Observation submodule (Endpoint 8, layer 1) | GMF JSON | 1 day |
| **P6** | Flexporter YAML enrichment mappings | Flexporter YAML | 2 days |
| **P7** | Python post-processor (MolecularSequence, distributions) | Python | 3 days |
| **P8** | End-to-end generation + HAPI ingestion + query validation | Integration | 2 days |
| **Total** | 1,000-patient NSCLC FHIR R4 dataset | | **~15 days** |

---

## 12. Gotchas & Known Limitations

**1. GMF `range` is uniform, not clinical.** All continuous values (tumor size, eGFR, PD-L1) will be uniform random without the post-processor reshaping step. Do not skip this layer for realistic data.

**2. No `MolecularSequence` in GMF.** Synthea has no native support for this resource type. The Python post-processor injection is mandatory for mCODE-conformant genomic reporting.

**3. `MedicationOrder` status is always `active` unless a `MedicationEnd` state exists.** For prior-platinum modeling (completed treatment), you must pair every `MedicationOrder` with a `MedicationEnd` state and a `Delay` between them.

**4. `CallSubmodule` shares the parent encounter context.** All `Observation` states in submodules will be bound to the parent encounter — which is correct behavior for lab results but requires your query logic to filter by encounter date if you add follow-up re-measurements.

**5. Flexporter is experimental.** The YAML mapping DSL has limitations around array element injection. Complex `component[]` slice construction (e.g., EGFR gene studied component) may require falling back to the Python post-processor.

**6. mCODE profile validation.** HAPI FHIR R4 validates against base FHIR, not mCODE IG profiles, by default. To enforce mCODE conformance, configure HAPI with the mCODE NPM package or run FHIR Validator CLI separately (`validator_cli.jar -ig hl7.fhir.us.mcode#3.0.0`).

---

## 13. Recommended Testing Strategy

1. **Unit test each submodule in isolation** using `./run_synthea -p 10 -m submodules/nsclc_staging` and inspect the output FHIR bundle
2. **Validate LOINC codes** against the LOINC browser before wiring — particularly ensure eGFR code `62238-1` vs the older `33914-3` (MDRD) distinction
3. **Query smoke tests** for all 9 endpoints after HAPI ingestion:
   ```
   # Endpoint 1: query_tumor_staging
   GET /fhir/Observation?code=21908-9&patient=[id]                          # stage group
   GET /fhir/Observation?code=21905-5&patient=[id]                          # T category
   GET /fhir/Observation?code=21906-3&patient=[id]                          # N category
   GET /fhir/Observation?code=21907-1&patient=[id]                          # M category

   # Endpoint 2: query_histology
   GET /fhir/DiagnosticReport?code=22637-3&patient=[id]                     # pathology report

   # Endpoint 3: query_tumor_size
   GET /fhir/Observation?code=33756-8&patient=[id]                          # tumor size (CAP)

   # Endpoint 4: query_lymph_nodes
   GET /fhir/Observation?code=21893-3&patient=[id]                          # lymph nodes examined
   GET /fhir/Observation?code=21894-1&patient=[id]                          # lymph nodes positive

   # Endpoint 5: query_prior_platinum
   GET /fhir/MedicationRequest?code=40048&patient=[id]&status=completed     # carboplatin
   GET /fhir/MedicationRequest?code=33014&patient=[id]&status=completed     # cisplatin

   # Endpoint 6: query_renal_function
   GET /fhir/Observation?code=62238-1&patient=[id]                          # eGFR

   # Endpoint 7: query_drug_interactions
   GET /fhir/MedicationRequest?patient=[id]&status=active                   # active medications

   # Endpoint 8: query_egfr_status
   GET /fhir/Observation?code=69548-6&patient=[id]                          # EGFR variant

   # Endpoint 9: query_pdl1_expr
   GET /fhir/Observation?code=85319-2&patient=[id]                          # PD-L1 TPS
   ```
4. **Distribution validation**: after generating 1,000 patients, assert ~15% are EGFR+, ~30% have PD-L1 ≥50%, staging distribution matches SEER data

---

*This plan targets FHIR R4 / mCODE STU3. Adjust profile URLs if targeting mCODE STU4 or US Core 7.x.*

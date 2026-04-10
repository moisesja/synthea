# Synthea<sup>TM</sup> Patient Generator ![Build Status](https://github.com/synthetichealth/synthea/workflows/.github/workflows/ci-build-test.yml/badge.svg?branch=master) [![codecov](https://codecov.io/gh/synthetichealth/synthea/branch/master/graph/badge.svg)](https://codecov.io/gh/synthetichealth/synthea)

Synthea<sup>TM</sup> is a Synthetic Patient Population Simulator. The goal is to output synthetic, realistic (but not real), patient data and associated health records in a variety of formats.

Read our [wiki](https://github.com/synthetichealth/synthea/wiki) and [Frequently Asked Questions](https://github.com/synthetichealth/synthea/wiki/Frequently-Asked-Questions) for more information.

Currently, Synthea<sup>TM</sup> features include:

- Birth to Death Lifecycle
- Configuration-based statistics and demographics (defaults with Massachusetts Census data)
- Modular Rule System
  - Drop in [Generic Modules](https://github.com/synthetichealth/synthea/wiki/Generic-Module-Framework)
  - Custom Java rules modules for additional capabilities
- Primary Care Encounters, Emergency Room Encounters, and Symptom-Driven Encounters
- Conditions, Allergies, Medications, Vaccinations, Observations/Vitals, Labs, Procedures, CarePlans
- Formats
  - HL7 FHIR (R4, STU3 v3.0.1, and DSTU2 v1.0.2)
  - Bulk FHIR in ndjson format (set `exporter.fhir.bulk_data = true` to activate)
  - C-CDA (set `exporter.ccda.export = true` to activate)
  - CSV (set `exporter.csv.export = true` to activate)
  - CPCDS (set `exporter.cpcds.export = true` to activate)
- Rendering Rules and Disease Modules with Graphviz

## Developer Quick Start

These instructions are intended for those wishing to examine the Synthea source code, extend it or build the code locally. Those just wishing to run Synthea should follow the [Basic Setup and Running](https://github.com/synthetichealth/synthea/wiki/Basic-Setup-and-Running) instructions instead.

### Installation

**System Requirements:**
Synthea<sup>TM</sup> requires Java JDK 17 or newer. We strongly recommend using a Long-Term Support (LTS) release of Java, 17 or 25, as issues may occur with more recent non-LTS versions.

To clone the Synthea<sup>TM</sup> repo, then build and run the test suite:

```
git clone https://github.com/synthetichealth/synthea.git
cd synthea
./gradlew build check test
```

### Changing the default properties

The default properties file values can be found at `src/main/resources/synthea.properties`.
By default, synthea does not generate CCDA, CPCDA, CSV, or Bulk FHIR (ndjson). You'll need to
adjust this file to activate these features. See the [wiki](https://github.com/synthetichealth/synthea/wiki)
for more details, or use our [guided customizer tool](https://synthetichealth.github.io/spt/#/customizer).

### Generate Synthetic Patients

Generating the population one at a time...

```
./run_synthea
```

Command-line arguments may be provided to specify a state, city, population size, or seed for randomization.

```
run_synthea [-s seed] [-p populationSize] [state [city]]
```

Full usage info can be printed by passing the `-h` option.

```
$ ./run_synthea -h

> Task :run
Usage: run_synthea [options] [state [city]]
Options: [-s seed]
         [-cs clinicianSeed]
         [-p populationSize]
         [-r referenceDate as YYYYMMDD]
         [-g gender]
         [-a minAge-maxAge]
         [-o overflowPopulation]
         [-c localConfigFilePath]
         [-d localModulesDirPath]
         [-i initialPopulationSnapshotPath]
         [-u updatedPopulationSnapshotPath]
         [-t updateTimePeriodInDays]
         [-f fixedRecordPath]
         [-k keepMatchingPatientsPath]
         [--config*=value]
          * any setting from src/main/resources/synthea.properties

Examples:
run_synthea Massachusetts
run_synthea Alaska Juneau
run_synthea -s 12345
run_synthea -p 1000
run_synthea -s 987 Washington Seattle
run_synthea -s 21 -p 100 Utah "Salt Lake City"
run_synthea -g M -a 60-65
run_synthea -p 10 --exporter.fhir.export=true
run_synthea --exporter.baseDirectory="./output_tx/" Texas
```

Some settings can be changed in `./src/main/resources/synthea.properties`.

Synthea<sup>TM</sup> will output patient records in C-CDA and FHIR formats in `./output`.

### Synthea<sup>TM</sup> GraphViz

Generate graphical visualizations of Synthea<sup>TM</sup> rules and modules.

```
./gradlew graphviz
```

### Concepts and Attributes

Generate a list of concepts (used in the records) or attributes (variables on each patient).

```
./gradlew concepts
./gradlew attributes
```

## NSCLC Synthetic Data Generation

This fork extends Synthea with a Non-Small Cell Lung Cancer (NSCLC) module that generates clinically realistic FHIR R4 bundles with mCODE-aligned oncology data across 9 endpoints: TNM staging, histology, tumor size, lymph node counts, medications, eGFR, genomic variants (EGFR), and PD-L1 expression.

### Prerequisites

- Java JDK 17 or newer (for Synthea)
- Python 3.8+ (for the post-processor; no third-party packages required)

### Quick Start

Generate 100 NSCLC patients:

```bash
./generate.sh 100 42
```

The pipeline runs three steps:

1. **Synthea generation** with the NSCLC module and Flexporter mCODE mappings
2. **Post-processing** for MolecularSequence injection and clinical distribution reshaping
3. **Optional HAPI FHIR ingest** (when `HAPI_URL` is set)

Output is written to an isolated per-run directory:

```
output/run-p100-s42/
├── fhir/       # Raw Synthea bundles
└── enriched/   # Post-processed bundles
```

### Environment Variables

| Variable          | Default    | Description                                   |
| ----------------- | ---------- | --------------------------------------------- |
| `AGE_RANGE`       | `50-80`    | Patient age range for NSCLC-relevant adults   |
| `SEED`            | `42`       | Second positional arg; controls randomization |
| `EGFR_PREVALENCE` | `0.095`    | Expected EGFR+ rate for variance check        |
| `OUTPUT_DIR`      | `./output` | Base output directory                         |
| `KEEP_OUTPUT`     | `0`        | Set to `1` for append mode (reuse output dir) |
| `HAPI_URL`        | _(unset)_  | FHIR server base URL for bundle ingest        |

### Loading into a FHIR Server

Synthea exports Practitioner and Organization resources into separate sidecar files. These **must be loaded before** patient bundles:

```bash
FHIR_URL="http://localhost:8080/fhir"
RUN_DIR="output/run-p100-s42"

# 1. Load Organization resources
curl -X POST -H "Content-Type: application/fhir+json" \
  --data-binary @"$RUN_DIR/fhir/hospitalInformation"*.json "$FHIR_URL"

# 2. Load Practitioner resources
curl -X POST -H "Content-Type: application/fhir+json" \
  --data-binary @"$RUN_DIR/fhir/practitionerInformation"*.json "$FHIR_URL"

# 3. Load enriched patient bundles
for f in "$RUN_DIR/enriched/"*.json; do
  curl -X POST -H "Content-Type: application/fhir+json" \
    --data-binary @"$f" "$FHIR_URL"
done
```

Or use the built-in ingest step:

```bash
HAPI_URL=http://localhost:8080/fhir ./generate.sh 100 42
```

> **Note:** The automated `HAPI_URL` ingest loads enriched bundles only. If your FHIR server requires Practitioner/Organization resources to resolve conditional references, load the sidecar files manually first as shown above.

### Querying NSCLC Data from a FHIR Server

Once bundles are loaded, use these FHIR REST queries to retrieve NSCLC clinical data for a given patient:

#### Tumor Staging

```
GET /Observation?code=21908-9&patient={id}&_sort=-date&_count=1
```

LOINC **21908-9** — _Stage group.clinical Cancer_. Returns the most recent clinical stage as an mCODE TNM Stage Group Observation with `valueCodeableConcept` containing the AJCC stage (e.g., Stage IIA, Stage IV).

#### Histology

```
GET /DiagnosticReport?code=11529-5&patient={id}&_sort=-date&_count=1
```

LOINC **11529-5** — _Surgical pathology study_. Returns the pathology report as a DiagnosticReport. Parse `conclusion` for the histological subtype (adenocarcinoma, squamous cell, large cell, or NOS).

#### Tumor Size

```
GET /Observation?code=21889-1&patient={id}&_sort=-date&_count=1
```

LOINC **21889-1** — _Size Tumor_. Returns the tumor size as an mCODE Tumor Size Observation. The measured value is in `valueQuantity` with units of `cm`.

#### Lymph Nodes

```
GET /Observation?code=21894-1&patient={id}&_sort=-date&_count=1
GET /Observation?code=21893-3&patient={id}&_sort=-date&_count=1
```

LOINC **21894-1** — _Regional lymph nodes examined_. Total number of lymph nodes sampled (`valueQuantity`).

LOINC **21893-3** — _Regional lymph nodes positive_. Number of nodes with metastatic involvement (`valueQuantity`). Always ≤ examined count.

# License

Copyright 2017-2025 The MITRE Corporation

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

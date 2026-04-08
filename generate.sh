#!/usr/bin/env bash
set -euo pipefail

# NSCLC Synthetic Data Generation Pipeline
#
# Usage: ./generate.sh [population] [seed]
#
# Environment variables:
#   HAPI_URL         If set, POST each enriched bundle to this FHIR server
#                    (e.g. HAPI_URL=http://localhost:8080/fhir ./generate.sh)
#   AGE_RANGE        Override the default NSCLC age range (default: 50-80)
#   EGFR_PREVALENCE  Expected cohort EGFR+ rate for post-processor variance
#                    check (default: 0.095 — adeno 50% × 15% + squamous 25%
#                    × 2% + large 15% × 5% + NOS 10% × 5%)
#   OUTPUT_DIR       Base output directory (default: ./output). Each run
#                    writes into a per-run subdirectory so runs stay isolated
#                    and the post-processor never sees stale bundles.
#   KEEP_OUTPUT      When set to 1, reuse $OUTPUT_DIR/fhir in place (append
#                    mode) instead of creating a fresh per-run subdirectory.

POPULATION=${1:-100}
SEED=${2:-42}
AGE_RANGE=${AGE_RANGE:-50-80}
EGFR_PREVALENCE=${EGFR_PREVALENCE:-0.095}
OUTPUT_DIR=${OUTPUT_DIR:-./output}

if [[ "${KEEP_OUTPUT:-0}" == "1" ]]; then
  RUN_DIR="$OUTPUT_DIR"
  FHIR_DIR="$OUTPUT_DIR/fhir"
  ENRICHED_DIR="$OUTPUT_DIR/enriched"
  echo "=== NSCLC Generation Pipeline (append mode) ==="
else
  # Per-run isolated directory keyed on seed + population to avoid
  # mixing bundles from previous runs into the post-processor input.
  RUN_DIR="$OUTPUT_DIR/run-p${POPULATION}-s${SEED}"
  FHIR_DIR="$RUN_DIR/fhir"
  ENRICHED_DIR="$RUN_DIR/enriched"
  rm -rf "$RUN_DIR"
  mkdir -p "$RUN_DIR"
  echo "=== NSCLC Generation Pipeline ==="
fi

echo "Population: $POPULATION | Seed: $SEED | Age: $AGE_RANGE"
echo "Run dir:    $RUN_DIR"
echo

# Step 1: Generate with Synthea + merged Flexporter
echo "Step 1: Running Synthea with Flexporter..."
./run_synthea \
  -s "$SEED" \
  -p "$POPULATION" \
  -a "$AGE_RANGE" \
  -m nsclc \
  -fm flexporter/nsclc_mcode_mappings.yml \
  --exporter.baseDirectory="$RUN_DIR/"

echo

# Step 2: Post-process (MolecularSequence injection, distribution reshaping)
echo "Step 2: Running post-processor..."
python3 post-processor/nsclc_postprocess.py \
  --input "$FHIR_DIR" \
  --output "$ENRICHED_DIR" \
  --seed "$SEED" \
  --distributions post-processor/distributions/ \
  --egfr-prevalence "$EGFR_PREVALENCE" \
  --pdl1-mixture-weights 0.4,0.3,0.3 \
  --validate

echo

# Step 3: Optional HAPI FHIR ingest (only when HAPI_URL is set)
if [[ -n "${HAPI_URL:-}" ]]; then
  echo "Step 3: Loading bundles into HAPI FHIR at $HAPI_URL"
  loaded=0
  failed=0
  for file in "$ENRICHED_DIR"/*.json; do
    if curl -sf -X POST \
        -H "Content-Type: application/fhir+json" \
        --data-binary "@$file" \
        "$HAPI_URL" > /dev/null; then
      loaded=$((loaded + 1))
    else
      failed=$((failed + 1))
      echo "  FAILED: $(basename "$file")"
    fi
  done
  echo "  Loaded $loaded bundles, $failed failures"
  echo
else
  echo "Step 3: HAPI ingest skipped (set HAPI_URL to enable)"
  echo
fi

echo "=== Done. $POPULATION patients generated ==="
echo "  Raw bundles:      $FHIR_DIR/"
echo "  Enriched bundles: $ENRICHED_DIR/"

#!/usr/bin/env bash
set -euo pipefail

# NSCLC Synthetic Data Generation Pipeline
# Usage: ./generate.sh [population] [seed]

POPULATION=${1:-100}
SEED=${2:-42}
OUTPUT_DIR="./output"
ENRICHED_DIR="./output/enriched"

echo "=== NSCLC Generation Pipeline ==="
echo "Population: $POPULATION | Seed: $SEED"
echo

# Step 1: Generate with Synthea + merged Flexporter
echo "Step 1: Running Synthea with Flexporter..."
./run_synthea \
  -s "$SEED" \
  -p "$POPULATION" \
  -m nsclc \
  -fm flexporter/nsclc_mcode_mappings.yml

echo

# Step 2: Post-process (MolecularSequence injection, distribution reshaping)
echo "Step 2: Running post-processor..."
python3 post-processor/nsclc_postprocess.py \
  --input "$OUTPUT_DIR/fhir" \
  --output "$ENRICHED_DIR" \
  --seed "$SEED"

echo
echo "=== Done. $POPULATION patients generated ==="
echo "  Raw bundles:      $OUTPUT_DIR/fhir/"
echo "  Enriched bundles: $ENRICHED_DIR/"

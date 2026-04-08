#!/usr/bin/env python3
"""NSCLC FHIR Bundle Post-Processor.

Enriches Synthea-generated FHIR R4 bundles with:
  A. MolecularSequence injection for EGFR+ patients
  B. PD-L1 TPS distribution reshaping (Beta mixture model)
  C. Tumor size log-normal reshaping
  D. eGFR age-correlated adjustment + interpretation coding
"""

import argparse
import glob
import json
import math
import os
import sys
import uuid
from datetime import datetime, date

import numpy as np


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
EGFR_VARIANTS_PATH = os.path.join(SCRIPT_DIR, "distributions", "egfr_variants.json")

EGFR_MUTATION_WEIGHTS = {"exon19_del": 0.45, "L858R": 0.40, "exon20_ins": 0.15}

# Tumor size log-normal parameters (mu, sigma) per T-stage range
TUMOR_SIZE_PARAMS = {
    # (range_low, range_high): (log_mu, log_sigma)
    (0.5, 3.0): (math.log(1.8), 0.3),   # T1
    (3.0, 5.0): (math.log(3.8), 0.2),   # T2
    (5.0, 7.0): (math.log(5.8), 0.15),  # T3
    (7.0, 10.0): (math.log(8.0), 0.15), # T4
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_resources(bundle, resource_type, loinc_code=None):
    """Yield (index, resource) tuples matching type and optional LOINC code."""
    for i, entry in enumerate(bundle.get("entry", [])):
        r = entry.get("resource", {})
        if r.get("resourceType") != resource_type:
            continue
        if loinc_code is None:
            yield i, r
            continue
        for coding in r.get("code", {}).get("coding", []):
            if coding.get("code") == loinc_code:
                yield i, r
                break


def get_patient_birth_year(bundle):
    """Return patient birth year from the Patient resource, or None."""
    for _, r in find_resources(bundle, "Patient"):
        bd = r.get("birthDate", "")
        if bd:
            try:
                return int(bd[:4])
            except ValueError:
                pass
    return None


def is_nsclc_bundle(bundle):
    """Check if bundle contains an NSCLC Condition (SNOMED 254637007)."""
    for _, r in find_resources(bundle, "Condition"):
        for coding in r.get("code", {}).get("coding", []):
            if coding.get("code") == "254637007":
                return True
    return False


def make_uuid():
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# A. MolecularSequence Injection
# ---------------------------------------------------------------------------

def inject_molecular_sequence(bundle, egfr_variants, rng):
    """For EGFR+ patients, inject a MolecularSequence and link it."""
    injected = 0
    for i, obs in find_resources(bundle, "Observation", "69548-6"):
        # Check if EGFR Present
        vc = obs.get("valueCodeableConcept", {})
        codes = [c.get("code") for c in vc.get("coding", [])]
        if "LA9633-4" not in codes:
            continue

        # Pick mutation subtype
        subtypes = list(EGFR_MUTATION_WEIGHTS.keys())
        weights = list(EGFR_MUTATION_WEIGHTS.values())
        subtype = rng.choice(subtypes, p=weights)
        variant_coords = egfr_variants[subtype]

        # Create MolecularSequence resource
        mol_id = make_uuid()
        mol_seq = {
            "resourceType": "MolecularSequence",
            "id": mol_id,
            "type": "dna",
            "coordinateSystem": 0,
            "patient": obs.get("subject", {}),
            "referenceSeq": {
                "chromosome": {
                    "coding": [{
                        "system": "http://terminology.hl7.org/CodeSystem/chromosome-human",
                        "code": "7",
                        "display": "Chromosome 7"
                    }]
                },
                "genomeBuild": "GRCh38",
                "referenceSeqId": {
                    "coding": [{
                        "system": "http://www.ncbi.nlm.nih.gov/nuccore",
                        "code": "NC_000007.14",
                        "display": "Homo sapiens chromosome 7, GRCh38.p14"
                    }]
                }
            },
            "variant": [{
                "start": variant_coords["start"],
                "end": variant_coords["end"],
                "observedAllele": variant_coords["observedAllele"],
                "referenceAllele": variant_coords["referenceAllele"]
            }]
        }

        # Add to bundle
        bundle["entry"].append({
            "fullUrl": f"urn:uuid:{mol_id}",
            "resource": mol_seq,
            "request": {"method": "POST", "url": "MolecularSequence"}
        })

        # Patch Observation.derivedFrom
        if "derivedFrom" not in obs:
            obs["derivedFrom"] = []
        obs["derivedFrom"].append({
            "reference": f"urn:uuid:{mol_id}",
            "display": f"EGFR {subtype} MolecularSequence"
        })
        injected += 1

    return injected


# ---------------------------------------------------------------------------
# B. PD-L1 TPS Distribution Reshaping
# ---------------------------------------------------------------------------

def reshape_pdl1(bundle, rng):
    """Reshape PD-L1 TPS values using Beta distributions per category."""
    reshaped = 0
    for _, obs in find_resources(bundle, "Observation", "85319-2"):
        vq = obs.get("valueQuantity", {})
        current_val = vq.get("value")
        if current_val is None:
            continue

        current_val = float(current_val)

        # Determine category from current value and reshape
        if current_val <= 1.0:
            # Negative: Beta(0.5, 5) scaled to [0, 1]
            new_val = float(rng.beta(0.5, 5)) * 1.0
            tier_code, tier_display = "LA9634-2", "Negative"
        elif current_val < 50.0:
            # Intermediate: keep as-is (uniform 1-49 is reasonable)
            new_val = current_val
            tier_code, tier_display = "LA9633-4", "Low positive"
        else:
            # High: Beta(5, 2) scaled to [50, 100]
            new_val = 50.0 + float(rng.beta(5, 2)) * 50.0
            tier_code, tier_display = "LA9633-4", "Positive"

        vq["value"] = round(new_val, 1)

        # Add interpretation
        obs["interpretation"] = [{
            "coding": [{
                "system": "http://loinc.org",
                "code": tier_code,
                "display": tier_display
            }]
        }]
        reshaped += 1

    return reshaped


# ---------------------------------------------------------------------------
# C. Tumor Size Log-Normal Reshaping
# ---------------------------------------------------------------------------

def reshape_tumor_size(bundle, rng):
    """Reshape tumor sizes using truncated log-normal per T-stage range."""
    reshaped = 0
    for _, obs in find_resources(bundle, "Observation", "33756-8"):
        vq = obs.get("valueQuantity", {})
        current_val = vq.get("value")
        if current_val is None:
            continue

        current_val = float(current_val)

        # Determine T-stage range from current value
        params = None
        for (lo, hi), p in TUMOR_SIZE_PARAMS.items():
            if lo <= current_val <= hi + 0.5:  # small tolerance
                params = (lo, hi, p[0], p[1])
                break

        if params is None:
            continue

        lo, hi, mu, sigma = params
        # Truncated log-normal: resample until within range (max 50 attempts)
        for _ in range(50):
            new_val = float(rng.lognormal(mu, sigma))
            if lo <= new_val <= hi:
                break
        else:
            new_val = max(lo, min(hi, new_val))

        vq["value"] = round(new_val, 2)
        reshaped += 1

    return reshaped


# ---------------------------------------------------------------------------
# D. eGFR Age-Correlated Adjustment
# ---------------------------------------------------------------------------

def adjust_egfr(bundle, rng):
    """Apply age-correlated eGFR adjustment and add interpretation."""
    birth_year = get_patient_birth_year(bundle)
    adjusted = 0

    for _, obs in find_resources(bundle, "Observation", "62238-1"):
        vq = obs.get("valueQuantity", {})
        current_val = vq.get("value")
        if current_val is None:
            continue

        current_val = float(current_val)

        # Age-correlated shift for patients 70+
        if birth_year:
            # Use observation effectiveDateTime to compute age at measurement
            eff = obs.get("effectiveDateTime", "")
            if eff:
                try:
                    obs_year = int(eff[:4])
                    age = obs_year - birth_year
                    if age > 70:
                        shift = 0.5 * (age - 70)
                        current_val = max(15.0, current_val - shift)
                except ValueError:
                    pass

        vq["value"] = round(current_val, 1)

        # Add interpretation based on clinical thresholds
        if current_val >= 60:
            interp_code, interp_display = "N", "Normal"
        elif current_val >= 45:
            interp_code, interp_display = "L", "Low"
        else:
            interp_code, interp_display = "LL", "Critical low"

        obs["interpretation"] = [{
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
                "code": interp_code,
                "display": interp_display
            }]
        }]
        adjusted += 1

    return adjusted


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def process_bundle(filepath, egfr_variants, rng):
    """Process a single FHIR bundle file. Returns stats dict."""
    with open(filepath) as f:
        bundle = json.load(f)

    if not is_nsclc_bundle(bundle):
        return None

    stats = {
        "mol_seq_injected": inject_molecular_sequence(bundle, egfr_variants, rng),
        "pdl1_reshaped": reshape_pdl1(bundle, rng),
        "tumor_reshaped": reshape_tumor_size(bundle, rng),
        "egfr_adjusted": adjust_egfr(bundle, rng),
    }

    return bundle, stats


def main():
    parser = argparse.ArgumentParser(description="NSCLC FHIR Bundle Post-Processor")
    parser.add_argument("--input", required=True, help="Input directory with FHIR bundles")
    parser.add_argument("--output", required=True, help="Output directory for enriched bundles")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)
    rng = np.random.default_rng(args.seed)

    # Load EGFR variant coordinates
    with open(EGFR_VARIANTS_PATH) as f:
        egfr_variants = json.load(f)

    # Process all bundle files
    files = sorted(glob.glob(os.path.join(args.input, "*.json")))
    nsclc_count = 0
    total_stats = {"mol_seq_injected": 0, "pdl1_reshaped": 0,
                   "tumor_reshaped": 0, "egfr_adjusted": 0}

    for filepath in files:
        basename = os.path.basename(filepath)
        result = process_bundle(filepath, egfr_variants, rng)

        if result is None:
            # Non-NSCLC bundle — copy as-is
            with open(filepath) as f:
                bundle = json.load(f)
            with open(os.path.join(args.output, basename), "w") as f:
                json.dump(bundle, f, indent=2)
            continue

        bundle, stats = result
        nsclc_count += 1
        for k in total_stats:
            total_stats[k] += stats[k]

        with open(os.path.join(args.output, basename), "w") as f:
            json.dump(bundle, f, indent=2)

    print(f"Processed {len(files)} bundles ({nsclc_count} NSCLC patients)")
    print(f"  MolecularSequence injected: {total_stats['mol_seq_injected']}")
    print(f"  PD-L1 TPS reshaped:         {total_stats['pdl1_reshaped']}")
    print(f"  Tumor sizes reshaped:        {total_stats['tumor_reshaped']}")
    print(f"  eGFR adjusted:               {total_stats['egfr_adjusted']}")


if __name__ == "__main__":
    main()

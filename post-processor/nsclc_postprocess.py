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
import random
import sys
import uuid


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DISTRIBUTIONS_DIR = os.path.join(SCRIPT_DIR, "distributions")

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
        subtype = rng.choices(subtypes, weights=weights, k=1)[0]
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
            new_val = rng.betavariate(0.5, 5) * 1.0
            tier_code, tier_display = "LA9634-2", "Negative"
        elif current_val < 50.0:
            # Intermediate: keep as-is (uniform 1-49 is reasonable)
            new_val = current_val
            tier_code, tier_display = "LA9633-4", "Low positive"
        else:
            # High: Beta(5, 2) scaled to [50, 100]
            new_val = 50.0 + rng.betavariate(5, 2) * 50.0
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
            new_val = rng.lognormvariate(mu, sigma)
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


def parse_weight_list(value):
    """Parse a comma-separated list of floats (e.g. '0.4,0.3,0.3')."""
    try:
        weights = [float(x) for x in value.split(",")]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid weight list '{value}': {exc}")
    if len(weights) != 3:
        raise argparse.ArgumentTypeError(
            "--pdl1-mixture-weights requires 3 values (negative,intermediate,high)")
    total = sum(weights)
    if not (0.99 <= total <= 1.01):
        raise argparse.ArgumentTypeError(
            f"--pdl1-mixture-weights must sum to 1.0 (got {total})")
    return weights


def main():
    parser = argparse.ArgumentParser(
        description="NSCLC FHIR Bundle Post-Processor",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--input", required=True,
                        help="Input directory with FHIR bundles")
    parser.add_argument("--output", required=True,
                        help="Output directory for enriched bundles")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed")
    parser.add_argument("--distributions", default=DEFAULT_DISTRIBUTIONS_DIR,
                        help="Directory containing distribution JSON files (e.g. egfr_variants.json)")
    parser.add_argument("--egfr-prevalence", type=float, default=None,
                        help="Optional expected EGFR+ prevalence — if set, logs a warning when observed rate deviates by >0.05")
    parser.add_argument("--pdl1-mixture-weights", type=parse_weight_list, default=None,
                        help="Optional expected PD-L1 tier weights (neg,intermediate,high) — logs a warning when observed distribution deviates by >0.05 per tier")
    parser.add_argument("--validate", action="store_true",
                        help="Run endpoint coverage validation on enriched bundles after processing")
    parser.add_argument("--dry-run", action="store_true",
                        help="Do not write enriched bundles; only process and report stats")
    args = parser.parse_args()

    if not args.dry_run:
        os.makedirs(args.output, exist_ok=True)
    rng = random.Random(args.seed)

    # Load EGFR variant coordinates from --distributions directory
    egfr_variants_path = os.path.join(args.distributions, "egfr_variants.json")
    if not os.path.isfile(egfr_variants_path):
        print(f"ERROR: egfr_variants.json not found in {args.distributions}", file=sys.stderr)
        sys.exit(1)
    with open(egfr_variants_path) as f:
        egfr_variants = json.load(f)

    # Process all bundle files
    files = sorted(glob.glob(os.path.join(args.input, "*.json")))
    nsclc_count = 0
    total_stats = {"mol_seq_injected": 0, "pdl1_reshaped": 0,
                   "tumor_reshaped": 0, "egfr_adjusted": 0}
    pdl1_tier_counts = {"negative": 0, "intermediate": 0, "high": 0}
    egfr_present_count = 0

    for filepath in files:
        basename = os.path.basename(filepath)
        result = process_bundle(filepath, egfr_variants, rng)

        if result is None:
            # Non-NSCLC bundle — copy through unchanged
            if not args.dry_run:
                with open(filepath) as f:
                    bundle = json.load(f)
                with open(os.path.join(args.output, basename), "w") as f:
                    json.dump(bundle, f, indent=2)
            continue

        bundle, stats = result
        nsclc_count += 1
        for k in total_stats:
            total_stats[k] += stats[k]

        # Collect EGFR and PD-L1 tier observations for variance checks
        for _, obs in find_resources(bundle, "Observation", "69548-6"):
            vals = [c.get("code") for c in obs.get("valueCodeableConcept", {}).get("coding", [])]
            if "LA9633-4" in vals:
                egfr_present_count += 1
        for _, obs in find_resources(bundle, "Observation", "85319-2"):
            v = obs.get("valueQuantity", {}).get("value")
            if v is None:
                continue
            if v <= 1.0:
                pdl1_tier_counts["negative"] += 1
            elif v < 50.0:
                pdl1_tier_counts["intermediate"] += 1
            else:
                pdl1_tier_counts["high"] += 1

        if not args.dry_run:
            with open(os.path.join(args.output, basename), "w") as f:
                json.dump(bundle, f, indent=2)

    print(f"Processed {len(files)} bundles ({nsclc_count} NSCLC patients)")
    print(f"  MolecularSequence injected: {total_stats['mol_seq_injected']}")
    print(f"  PD-L1 TPS reshaped:         {total_stats['pdl1_reshaped']}")
    print(f"  Tumor sizes reshaped:        {total_stats['tumor_reshaped']}")
    print(f"  eGFR adjusted:               {total_stats['egfr_adjusted']}")

    # Optional distribution sanity checks
    if nsclc_count > 0 and args.egfr_prevalence is not None:
        observed = egfr_present_count / nsclc_count
        delta = abs(observed - args.egfr_prevalence)
        marker = "OK" if delta <= 0.05 else "WARN"
        print(f"  [{marker}] EGFR+ observed {observed:.1%} vs expected {args.egfr_prevalence:.1%} (Δ={delta:.1%})")

    if nsclc_count > 0 and args.pdl1_mixture_weights is not None:
        tiers = ["negative", "intermediate", "high"]
        for tier, expected in zip(tiers, args.pdl1_mixture_weights):
            observed = pdl1_tier_counts[tier] / nsclc_count
            delta = abs(observed - expected)
            marker = "OK" if delta <= 0.05 else "WARN"
            print(f"  [{marker}] PD-L1 {tier}: observed {observed:.1%} vs expected {expected:.1%} (Δ={delta:.1%})")

    # Optional endpoint coverage validation
    if args.validate and not args.dry_run:
        print()
        validate_endpoints(args.output)


def validate_endpoints(output_dir):
    """Validate the 9 NSCLC endpoints across enriched bundles."""
    endpoints = [
        ("EP1 TNM stage group", "Observation", "21908-9"),
        ("EP1 T category",      "Observation", "21905-5"),
        ("EP1 N category",      "Observation", "21906-3"),
        ("EP1 M category",      "Observation", "21907-1"),
        ("EP2 pathology report","DiagnosticReport", "22637-3"),
        ("EP2 histology",       "Observation", "59847-4"),
        ("EP3 tumor size",      "Observation", "33756-8"),
        ("EP4 LN examined",     "Observation", "21893-3"),
        ("EP4 LN positive",     "Observation", "21894-1"),
        ("EP6 eGFR",            "Observation", "62238-1"),
        ("EP8 genomic variant", "Observation", "69548-6"),
        ("EP9 PD-L1 TPS",       "Observation", "85319-2"),
    ]
    counts = {name: 0 for name, _, _ in endpoints}
    has_meds = 0
    has_mol_seq = 0
    nsclc_total = 0

    for filepath in sorted(glob.glob(os.path.join(output_dir, "*.json"))):
        with open(filepath) as f:
            bundle = json.load(f)
        if not is_nsclc_bundle(bundle):
            continue
        nsclc_total += 1
        for name, rtype, code in endpoints:
            for _ in find_resources(bundle, rtype, code):
                counts[name] += 1
                break
        for _, _ in find_resources(bundle, "MedicationRequest"):
            has_meds += 1
            break
        for _, _ in find_resources(bundle, "MolecularSequence"):
            has_mol_seq += 1
            break

    print(f"=== Endpoint Coverage ({nsclc_total} NSCLC bundles) ===")
    all_ok = True
    for name, _, _ in endpoints:
        n = counts[name]
        pct = 100 * n / nsclc_total if nsclc_total else 0
        mark = "OK  " if n == nsclc_total else "FAIL"
        if n != nsclc_total:
            all_ok = False
        print(f"  [{mark}] {name:<22} {n}/{nsclc_total} ({pct:.0f}%)")
    print(f"  [OK  ] MedicationRequest      {has_meds}/{nsclc_total}")
    print(f"  [INFO] MolecularSequence      {has_mol_seq}/{nsclc_total} (EGFR+ subset)")
    if not all_ok:
        sys.exit(2)


if __name__ == "__main__":
    main()

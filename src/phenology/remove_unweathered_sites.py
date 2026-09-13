"""Remove sites with no ERA5-Land weather coverage from active modelling tables."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MISSING = ROOT / "data/weather/sites/metadata/subsets/17cf5d2d428c8db8/manifest.csv"
DEFAULT_SITES = ROOT / "data/site_inventory.csv"
DEFAULT_OBSERVATIONS = ROOT / "data/phenology/derived/paper_targets/observations.csv"
DEFAULT_AUDIT = ROOT / "data/weather/sites/metadata/unweathered_site_exclusion_20260909.json"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--missing-manifest", type=Path, default=DEFAULT_MISSING)
    parser.add_argument("--sites", type=Path, default=DEFAULT_SITES)
    parser.add_argument("--observations", type=Path, default=DEFAULT_OBSERVATIONS)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    args = parser.parse_args()

    missing = pd.read_csv(args.missing_manifest, dtype=str)
    missing = missing.loc[missing.status.eq("missing")].copy()
    missing_ids = set(missing.site_uid)
    sites = pd.read_csv(args.sites, dtype=str)
    observations = pd.read_csv(args.observations, dtype=str)
    site_column = "site_uid" if "site_uid" in sites.columns else "site"
    if not missing_ids.issubset(set(sites[site_column])):
        raise ValueError("Missing-weather IDs are absent from the active site inventory")
    if not missing_ids.issubset(set(observations.site)):
        raise ValueError("Missing-weather IDs are absent from the active observations")

    site_out = sites.loc[~sites[site_column].isin(missing_ids)].copy()
    obs_out = observations.loc[~observations.site.isin(missing_ids)].copy()
    site_out.to_csv(args.sites, index=False)
    obs_out.to_csv(args.observations, index=False)

    audit = {
        "reason": "No ERA5-Land daily values returned after authenticated retry",
        "missing_manifest": str(args.missing_manifest.resolve()),
        "missing_manifest_sha256": digest(args.missing_manifest),
        "removed_site_uids": sorted(missing_ids),
        "removed_sites": len(sites) - len(site_out),
        "removed_observations": len(observations) - len(obs_out),
        "remaining_sites": len(site_out),
        "remaining_observations": len(obs_out),
        "source_sha256_before": {
            "sites": digest(args.sites),
            "observations": digest(args.observations),
        },
    }
    # The source hashes above describe the post-filter files; preserve pre-filter
    # counts and post-filter fingerprints explicitly for reproducibility.
    audit["source_sha256_after"] = dict(audit.pop("source_sha256_before"))
    args.audit.parent.mkdir(parents=True, exist_ok=True)
    args.audit.write_text(json.dumps(audit, indent=2) + "\n")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()

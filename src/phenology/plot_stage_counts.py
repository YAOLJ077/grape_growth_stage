"""Render counts of four phenology stages in developmental order."""
import collections
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'fig/phen_data'
SOURCE = ROOT / "data/phenology/derived/paper_targets/observations.csv"


def main():
    groups = collections.defaultdict(list)
    with SOURCE.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            assert len(row["BBCH"]) == 2 and row["BBCH"].isdigit()
            assert row['BBCH'] in {'07', '65', '81', '89'}
            groups[row["BBCH"]].append(row)
    rows = []
    for stage, observations in sorted(groups.items(), key=lambda item: int(item[0])):
        rows.append(dict(BBCH=stage, count=len(observations),
                         n_sites=len({r["site"] for r in observations}),
                         n_years=len({r["Date"][:4] for r in observations}),
                         n_countries=len({r["country"] for r in observations if r["country"]}),
                         first_date=min(r["Date"] for r in observations),
                         last_date=max(r["Date"] for r in observations)))
    assert rows
    source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    qc = json.loads(SOURCE.with_name("quality.json").read_text())
    total = sum(row["count"] for row in rows)
    assert total == qc['combined']['rows'] and source_hash == qc['combined']['sha256']
    assert hashlib.sha256((ROOT / qc['source']).read_bytes()).hexdigest() == qc['source_sha256'], 'Paper targets are stale'
    with (OUT / "stage_counts.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    quality = dict(source=str(SOURCE.relative_to(ROOT)), source_sha256=source_hash,
                   observations=total, stages=len(rows),
                   stage_order=[r["BBCH"] for r in rows],
                   x_axis="Observed BBCH stages; categorical positions in numeric order",
                   y_axis="Number of retained observation rows; linear scale with zero baseline",
                   additional_filters="All rows of the four-stage combined file; all countries; partial sequences retained",
                   quality_policy=qc['inherited_qc'], target_policy=qc['policy'],
                   inventory_source=qc['source'], inventory_sha256=qc['source_sha256'])
    with tempfile.TemporaryDirectory(prefix="grape-stage-counts-") as temporary:
        payload = Path(temporary) / "counts.json"
        payload.write_text(json.dumps(rows))
        subprocess.run(["swift", "-module-cache-path", "/tmp/grape-workflow-swift-cache",
                        str(Path(__file__).with_name("draw_plot.swift")), str(payload), str(OUT)], check=True)
    (OUT / "plot_quality.json").write_text(json.dumps(quality, indent=2) + "\n")
    print(f"Verified {total:,} observations across {len(rows)} BBCH stages.")


if __name__ == "__main__":
    main()

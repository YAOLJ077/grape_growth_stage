# Four-target phenology screening, version 3

The revised four-target inventory retains **75,738 observations** from **77,313 exact unique direct-source target observations** dated 1951 onward. The **1,575 quarantined records** preserve their original fields and exclusion evidence. Relative to the previous full-inventory target selection (75,233 observations), 503 records are removed and 1,008 are restored. This separately versioned inventory does not replace the frozen model-training cohort or the all-stage inventory.

## Calendar and interval rules

All limits are inclusive project screening choices, not universal physiological bounds. Dates and stage codes are never repaired, clipped or inferred.

| Target | Eligible calendar dates |
|---|---|
| BBCH07, beginning of budburst | February 1–June 15 |
| BBCH65, full flowering | April 1–July 31 |
| BBCH81, beginning of veraison | June 1–October 15 |
| BBCH89, maturity/harvest | July 15–November 15 |

| Earlier → later stage | Minimum days | Maximum days | Basis |
|---|---:|---:|---|
| 07 → 65 | 20 | 120 | Adjacent-stage screening choice |
| 65 → 81 | 30 | 120 | Adjacent-stage screening choice |
| 81 → 89 | 10 | 90 | Adjacent-stage screening choice |
| 07 → 81 | 50 | 240 | Sum of adjacent bounds |
| 65 → 89 | 40 | 210 | Sum of adjacent bounds |
| 07 → 89 | 60 | 330 | Sum of adjacent bounds |

Comparisons require exact source-qualified site, reported variety label and calendar year. Empty variety labels form their own groups. Each date needs at least one compatible counterpart at every other observed target stage. All failures within a pass are quarantined simultaneously; survivors are rechecked until stable. Missing stages impose no requirement, although a cross-stage interval remains testable when both of its endpoints exist. Quarantining both unsupported endpoints acknowledges that the erroneous endpoint is unknown. Repeated dates with compatible counterparts remain separate observations.

The reassessment uses only four-target chronology. The older screen also used non-target stages in separate developmental branches. Consequently, restored observations reflect changes in comparison scope as well as revised calendar windows and the 07→65 upper bound. BBCH09 remains distinct and is not a substitute for BBCH07.

## Source quality and conflicting reports

DWD quality uses the highest available control level for each exact observation. An incorrect-date flag (QB8) excludes it. At that level, a no-objection, corrected or confirmed flag (QB1/2/3) resolves doubt; otherwise QB5 excludes it as doubtful. Corrected and confirmed observations are not discarded merely because a correction occurred. Records with no quality metadata remain explicitly unverified rather than being assigned a fabricated quality level.

Where station, reported maturity-class label, year, BBCH, original object identifier and original phase identifier all agree, one accepted annual date at QN≥7 takes precedence over a conflicting immediate date at QN<7. Other equally controlled dates are not resolved arbitrarily. This is an explicit source-precedence policy; it does not prove that every immediate report was a revision of the same plant observation. Definitions follow the [DWD annual grapevine documentation](https://opendata.dwd.de/climate_environment/CDC/observations_germany/phenology/annual_reporters/vine/historical/DESCRIPTION_obsgermany-phenology-annual_reporters-vine-historical_en.pdf).

| Exclusion rule | Unique records carrying the rule |
|---|---:|
| Provider doubtful date | 140 |
| Higher-quality annual report precedence | 403 |
| Calendar window | 292 |
| Adjacent-stage interval | 737 |
| Derived cross-stage interval | 9 |

Rule memberships overlap for interval exclusions; they must not be summed as unique observations. Earlier quality and calendar exclusions take precedence over later interval screening.

## Evidence and limitations

The [INRAE/IFV scale](https://rdf.codex.cati.inrae.fr/ppd-res/grapevine) supports stage interpretation, not calendar thresholds. [Costa et al. (2019)](https://doi.org/10.3390/agronomy9040210) report observed BBCH65 dates as early as April 22 and BBCH81 dates as early as June 19 in the Douro region. These observations motivate broader European screening margins, but do not validate individual restored observations in this collection. Two original February budburst-to-flowering pairs span 108 days; these are descriptive records, not independently validated reference events. The 120-day upper bound retains broad room for such early development.

No model prediction, residual or fitted parameter enters the cleaning code. The screening review followed inspection of model results, so subsequent score comparisons are post hoc sensitivity analyses. The thresholds must not be adjusted to improve test scores or applied to clip predictions.

The retained inventory still has 2,049 site–variety–year–stage groups with multiple dates, including 68 with spans exceeding 30 days. These are review flags, not proof of errors: source labels can pool plants or cultivars, and BBCH89 can represent managed harvest. Their dates remain in [retained_repeated_dates.csv](retained_repeated_dates.csv). The revised data therefore remain screened observations, not a claim of individually verified biological truth.

## Files and verification

- [observations.csv](observations.csv): unchanged seven-column retained observations.
- [quarantine.jsonl.gz](quarantine.jsonl.gz): excluded original records, hashes and rule/date evidence.
- [provenance.jsonl.gz](provenance.jsonl.gz): all 118,597 source occurrences contributing target records, linked to exact event hashes.
- [membership_changes.csv](membership_changes.csv): removal and restoration relative to the previous phenology-only target inventory.
- [exclusions_by_dimension_rule.csv](exclusions_by_dimension_rule.csv): counts by country, source, BBCH, year and rule.
- [summary.json](summary.json): rules, source hashes, output hashes and counts.
- [verification.json](verification.json): independent field, partition, provenance and 104,138 retained endpoint-support checks.
- [Final population reconstruction](../../../../src/data_preparation/README.md): weather-eligible subset and original partitions.

Reproduction from the repository root requires verified original input objects and a new output directory:

```sh
.venv/bin/python src/phenology/prepare_target_qc_v3.py --output /path/to/new_qc_directory
.venv/bin/python src/phenology/verify_target_qc_v3.py /path/to/new_qc_directory
.venv/bin/python -m pytest -q src/phenology/test_target_qc_v3.py src/validation/test_verify.py
```

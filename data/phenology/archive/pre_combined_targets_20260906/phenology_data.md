# High-confidence BBCH grapevine phenology data

## Dataset

`phenology_data.csv` contains 259,998 distinct seven-field grapevine records
with direct source BBCH codes from the full available country collection.
Inferred conversions, unmapped phases and chronology-v2 screening failures are
excluded. The table has exactly
these columns:

```text
site,variety,country,lat,lon,Date,BBCH
```

Records span 1951-03-14 to 2026-06-24 and contain 4,244 source-qualified site
identifiers across 13 identified countries, with no missing country values.
Source-qualified sites are not necessarily independent physical sites: networks
can report the same location under different identifiers. Dates must be on or
after 1951-01-01. No France–Germany, four-stage, weather-availability or
modelling-tier filter is applied. The study-period cutoff does not verify daily
weather availability or preceding-year chilling inputs for individual records.
High confidence refers to the BBCH conversion provenance, not validation of every
source observation, cultivar assignment or event date. The consolidated table
is an observation inventory, not a final modelling cohort.

## Paper target subsets

The active paper scope uses all countries represented by eligible target-stage
observations. Two phenology-only exports are derived without changing
`phenology_data.csv`:

| Export | Target | Rows | Source-qualified sites | Coordinate pairs | Countries | Date range |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `derived/paper_targets/primary.csv` | BBCH07, 65 and 81 | 70,694 | 3,106 | 2,950 | 11 | 1951-04-15–2026-06-23 |
| `derived/paper_targets/maturity_secondary.csv` | BBCH89 | 4,539 | 828 | 809 | 6 | 1951-09-07–2022-10-01 |

The primary stage counts are 25,303 BBCH07, 26,657 BBCH65 and 18,734 BBCH81
records. The intended sequence is 07→65→81, but a site or year is retained when
any one primary stage is present; no complete sequence is required. BBCH09 is
not substituted for BBCH07, and BBCH89 is analyzed separately as an operational
maturity/harvest endpoint.

Both files retain `site,variety,country,lat,lon,Date,BBCH`. Missing variety labels
and repeated accepted observations are preserved exactly as represented in the
cleaned inventory. Non-target stages remain valid inventory records rather than
exclusions. Historical France–Germany derived products remain unchanged and do
not define the active all-country paper scope.

These exports establish phenological eligibility, not final modelling
eligibility. Weather matching, cultivar or plant identity, and reconciliation of
source-qualified identifiers into independent physical sites remain downstream
tasks. Their counts therefore must not be reported as the final analysis sample.

## Column definitions

| Column | Definition and storage |
| --- | --- |
| `site` | Text identifier: `COUNTRY:tempo:site_id`, `DE:dwd:site_id`, or `COUNTRY:pep725:provider_id:s_id`. Original identifier strings and leading zeros are preserved. `XX` marks an unknown country within the identifier only. |
| `variety` | Reported cultivar label, or the reported DWD maturity-group label when that is the available classification. Empty when unavailable. The redundant `Vitis vinifera` prefix is removed from PEP725 cultivar text; spelling, case and cultivar synonyms are otherwise preserved. |
| `country` | Two-letter country code; empty for unknown source attribution. TEMPO country names and PEP725 provider metadata determine the codes. Countries are not inferred from coordinates. |
| `lat` | Source latitude in decimal degrees, WGS84. No rounding or DEM substitution is applied. |
| `lon` | Source longitude in decimal degrees, WGS84. No rounding or DEM substitution is applied. |
| `Date` | Source event date in ISO `YYYY-MM-DD` format. Historical dates retain the source calendar representation; no historical calendar conversion or date imputation is applied. |
| `BBCH` | Valid, direct source BBCH code stored as two characters, including `00`, `05` and `07`. Never empty in this filtered export. Inferred mappings do not qualify. |

CSV encoding is UTF-8 with a comma delimiter and LF line endings. `site` and
`BBCH` require text types on import to preserve leading zeros. Empty fields
represent missing values, not zero. DWD labels such as “Weinrebe, frühe Reife”
describe maturity groups rather than identified cultivars; the truncated source
label “Weinrebe, mittelspäte Reife (bevorz” is retained without inventing its ending.

## Sources and reconciliation

One representation of each source collection is included. The selected-country
PEP725 processed table is already contained in the full PEP725 extract and is not
appended a second time. Derived BBCH, site–year, modelling and summary tables are
alternative representations of these observations, not additional observations.
Older DWD release snapshots are not appended over the canonical complete DWD
table, which assembles the selected annual and immediate reporter releases.

| Input relative to `data/phenology/` | Source rows | Non-grape excluded | Inferred BBCH excluded | Unmapped BBCH excluded | Pre-1951 excluded | Chronology QC excluded | Eligible duplicates removed | Output rows |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `processed/france_grape_phenology_complete.csv` | 555,791 | 9 | 0 | 0 | 12,599 | 30,351 | 391,220 | 121,612 |
| `processed/germany_grape_phenology_complete.csv` | 93,510 | 0 | 50,668 | 7,836 | 0 | 487 | 2,825 | 31,694 |
| `raw/france_tempo/tempo_other_countries_observations_joined.csv` | 28,451 | 25,462 | 0 | 0 | 2,763 | 0 | 0 | 226 |
| `raw/pep725/pep725_20260701_0.csv` | 145,276 | 0 | 29,196 | 5,854 | 2,132 | 1,628 | 0 | 106,466 |
| **Total** | **823,028** | **25,471** | **79,864** | **13,690** | **17,494** | **32,466** | **394,045** | **259,998** |

Chronology QC operates on unique seven-field records and quarantines 11,034 of
them. The 32,466 source occurrences above include all duplicates of those
quarantined records; the disjoint source-level statuses reconcile to 823,028.

The France and Germany canonical files are Git LFS pointers in this checkout.
Their full contents were downloaded into `.source_cache/` and verified against
the pointer byte counts and SHA256 hashes. The original pointers, raw files,
processed tables and existing derived products remain unchanged. Full input
and output checksums are recorded in `phenology_data_quality.json`.

## Processing steps

1. **Resolve and verify inputs.** Read the four source tables listed above.
   Detect Git LFS pointers before CSV parsing; require checksum-verified full
   contents when pointers are present. Failure to obtain a required source
   prevents a partial dataset from being labelled complete.
2. **Retain grapevine records across all countries.** Require a source taxon
   matching `Vitis vinifera`. Nine peach observations in the France table and
   25,462 non-grape observations in the auxiliary TEMPO table are excluded.
   All grapevine providers are eligible, subject to the BBCH-confidence and
   observation-date filters below.
3. **Build source-qualified site identifiers.** Combine country, source namespace
   and original site identifier; include PEP725 provider ID. Preserve station
   identifier strings, including DWD leading zeros. No cross-network station
   matching or coordinate-based site merging is performed.
4. **Standardize country and variety fields.** Resolve country from source
   metadata. Trim whitespace and explicit missing-value sentinels. Preserve
   reported varieties and maturity groups, without substituting a cultivar for
   an unspecified grapevine or translating maturity classes into varieties.
5. **Normalize coordinates and dates.** Preserve valid source precision and
   ISO dates, including records before 1951. Check coordinate bounds, finite
   numbers and calendar validity. Invalid values would become empty fields
   with audit counts, rather than fabricated values; none were found in this run.
6. **Filter BBCH confidence.** Normalize valid direct source BBCH codes to two
   digits and retain only these high-conversion-confidence records. Exclude all
   inferred repository mappings and all unmapped phases before deduplication.
   The old mapping lookup is retained only to classify exclusions in the audit;
   none of its inferred values enters the output. A directly coded record remains
   eligible even if a matching inferred record appeared earlier in the input.
7. **Apply the study-period cutoff.** Retain normalized dates on or after
   1951-01-01. Exclude earlier dates after BBCH-confidence filtering and before
   deduplication; record `excluded_before_1951` and the original date in the
   provenance. Missing or invalid dates cannot qualify and receive a separate
   exclusion status; none occur among otherwise eligible rows in this run.
8. **Remove only exact output duplicates.** Deduplicate on all seven normalized
   output fields. Retain different dates, varieties and sites, even within the
   same site–year–BBCH combination. No minimum-date or median-date aggregation
   is applied. Multiple source records can become identical after reducing the
   schema; this is seven-field deduplication, not proof of biological identity.
9. **Screen chronology and phase intervals.** Apply policy `chronology-v2` in
   `phenology_qc.py`, as defined in the root `AGENTS.md`. Seasonal windows precede
   individual-record temporal-support checks within site × variety × year.
   Quarantine unsupported records simultaneously and recheck remaining stage
   pairs until stable. Quarantine both endpoints when no compatible pair exists;
   retain unrelated stages and do not infer missing event dates.
10. **Export and reconcile.** Sort deterministically by country, site, date, BBCH,
   variety and coordinates. Check the exact column order, unique output rows,
   valid nonempty values and source-count reconciliation. Preserve one compressed
   provenance record for every input row, including duplicates and exclusions.

## BBCH confidence rules

| Source | Eligible evidence | Action |
| --- | --- | --- |
| TEMPO France | Valid source `bbch_code` | Retain and normalize to two digits |
| Auxiliary TEMPO | Valid source BBCH `stage_code` | Retain and normalize to two digits |
| DWD | Valid populated `bbch_code` | Retain; do not fill missing codes from phase IDs |
| PEP725 | Integer `phase_id` between 0 and 99 | Retain the directly coded BBCH stage |
| All sources | Inferred or unavailable BBCH | Exclude from the observation CSV; preserve provenance |

DWD stages 4, 30, 31, 32 and 40 lacking direct BBCH, and PEP725 stages 100, 201
and 205, are excluded rather than assigned inferred codes. DWD bleeding stage 2
and PEP725 phases 250 and 380 are also excluded. Consequently, the questionable
PEP725 205-to-95 colouring-to-leaf-fall conversion does not appear in the output.
Direct BBCH89 observations remain eligible; a phase is not excluded merely
because other sources previously used an inferred mapping to that same code.
BBCH07 and BBCH09 remain distinct. Confidence filtering does not use dates or
phenology-model predictions to infer a stage.

The all-year high-confidence snapshot contained 288,464 unique rows. The inclusive
1951 cutoff removes 17,432 unique records and 463 site identifiers with no remaining
observations, leaving 271,032 records and 4,252 source-qualified sites. The
17,494 pre-1951 exclusions in the source reconciliation include 62 repeated
seven-field records. Source exclusion counts precede deduplication and therefore
differ from counts removed from the former unique-row export.

## Quality checks

### Chronology-v2 screening

The complete rule specification, stage branches and scientific qualifications
are in `../../AGENTS.md`, under **Chronology and interval QC**. The main phase
intervals are 20–100 days for BBCH07/09→65, 30–120 days for BBCH65→81, and
10–90 days for BBCH81→89. These thresholds are project screening choices;
literature cultivar means and empirical percentiles are not universal limits.

| Screening outcome | Unique records |
| --- | ---: |
| Pre-QC inventory | 271,032 |
| Outside stage-specific seasonal window | 983 |
| Unsupported chronological stage order | 9,368 |
| Unsupported major phase interval | 740 |
| Union quarantined | 11,034 |
| Retained | 259,998 |

Rule counts overlap for records failing multiple pair checks and cannot be
summed. Quarantine removes 4.1% of records and eight source-qualified site IDs.
Country exclusions are FR 8,926; DE 1,869; AT 108; SK 56; BA 32; HR 19;
CH 12; ME 8; and ES 4. Source exclusions are TEMPO 8,926, PEP725 1,628 and
DWD 480. Year, stage, country and source breakdowns are in
`phenology_data_quality.json`. No exclusion is based on model error or temperature.

Quarantine denotes failure of the screen, not proof of incorrect source data.
Missing cultivar identity, pooled observations from multiple plants, management
effects and extreme climates can generate conflicts. Within-stage dates are
not averaged or collapsed. Dormancy and senescence have no blanket seasonal
or chronology filter; passing QC therefore does not validate every BBCH stage.
Sensitivity analyses require the quarantined population, especially for
warm-climate transfer and climate-change interpretation.

| Check | Result |
| --- | ---: |
| Exact seven-field duplicates remaining | 0 |
| Missing site, latitude, longitude or date | 0 |
| Missing variety | 176,904 |
| Missing country | 0 |
| Observations before 1951-01-01 | 0 |
| Missing or inferred BBCH in output | 0 |
| DWD rows containing maturity-group labels rather than identified varieties | 31,134 |
| Invalid nonempty dates or coordinates | 0 |
| Future-dated observations relative to 2026-09-06 | 0 |
| Source-qualified sites with multiple coordinate pairs | 0 |
| Possible cross-source coincidence keys | 17,374 |
| Retained records failing chronology-v2 checks | 0 |

Missing varieties remain an explicit limitation for cultivar-specific analyses.
The confidence filter changes source and stage coverage; absence of inferred
events must not be interpreted as biological absence of the event.
Unknown country attribution is not inferred from coordinates. The 107 formerly
included records at `XX:tempo:24233` all precede 1951 and are now excluded.

Possible cross-source coincidences are combinations of country, coordinates
rounded to four decimal places for this diagnostic only, date and BBCH that
occur in more than one source system. This diagnostic does not use cultivar;
coincident events can involve different varieties or nearby sites. DWD records
redistributed through PEP725 may also overlap the direct DWD collection. These
records remain source-separated because an authoritative station/cultivar
crosswalk is unavailable. They are not established duplicate pairs, and the
4,244 identifiers must not be interpreted as 4,244 independent physical sites.
Cross-network entity resolution is required before spatial model splitting.

## Country coverage

| Country | Code | Records | Source-qualified sites |
| --- | --- | ---: | ---: |
| Austria | AT | 8,758 | 560 |
| Bosnia and Herzegovina | BA | 179 | 5 |
| Switzerland | CH | 2,292 | 98 |
| Czechia | CZ | 94 | 3 |
| Germany | DE | 117,394 | 1,465 |
| Spain | ES | 1,106 | 43 |
| France | FR | 121,710 | 1,996 |
| Croatia | HR | 3,691 | 6 |
| Luxembourg | LU | 183 | 1 |
| Montenegro | ME | 37 | 2 |
| Sweden | SE | 11 | 4 |
| Slovenia | SI | 971 | 6 |
| Slovakia | SK | 3,572 | 55 |

## Reproduction and provenance

From the repository root:

```sh
python3 data/phenology/fetch_phenology_inputs.py
python3 data/phenology/organize_phenology.py
python3 data/phenology/select_modeling_targets.py
python3 -m unittest discover -s data/phenology -p 'test_*.py'
```

The downloader is unnecessary when both complete canonical tables or verified
cached copies are already present. It uses the configured GitHub credential for
this repository, without printing credentials, and downloads only the two
required LFS objects. The transformation and tests use Python's standard library.

- `phenology_data.csv`: the single consolidated observation table.
- `phenology_data_quality.json`: input hashes, counts, mappings, completeness,
  country coverage and output checksums.
- `phenology_data_provenance.jsonl.gz`: one audit record per input row, with source
  path, logical record number and original observation ID when available.
  Included grape records carry their source stage, direct mapping status,
  licence and output-event hash. BBCH exclusions carry their reason and a
  candidate-event hash, not a claim of inclusion. Date exclusions additionally
  carry the source date; non-grape exclusions include
  their source taxon. Logical record numbers exclude the CSV header.
- `phenology_data_checks.ipynb`: independent CSV and provenance checks.
- `phenology_data_quarantine.jsonl.gz`: one record per QC exclusion containing
  the original seven fields, event hash, policy version, rule IDs, dates and
  counterpart evidence. Its event hash links to every contributing source
  occurrence marked `excluded_chronology_qc` in the provenance sidecar.
- `derived/paper_targets/primary.csv`: all-country phenology-only BBCH07/65/81
  targets.
- `derived/paper_targets/maturity_secondary.csv`: phenology-only BBCH89
  secondary target.
- `derived/paper_targets/quality.json`: subset counts, coverage and validation
  metadata written by `select_modeling_targets.py`.

All five notebook code cells executed sequentially with Python 3, including
complete CSV validity checks and reconciliation of all 823,028 provenance records.
The 18 normalization, confidence, date-cutoff and chronology tests passed. The saved notebook includes the actual
outputs; execution used a standard-library runner because Jupyter is not installed
in this environment. The cells require no IPython-specific features or packages.

An output-event hash is SHA256 of the UTF-8 JSON array of its seven string values,
using `ensure_ascii=False` and separators `(',', ':')`. Thus one output row can be
traced to all corresponding source observations, even after exact duplicates
are collapsed. Missing values are not imputed, and no observation data are
reconstructed from file names or plotted summaries.

## Attribution

Source licences and provider attribution remain applicable to the consolidated
records; the CSV does not have a newly assigned uniform licence. The PEP725
extract includes CC BY 4.0, CC BY-NC 4.0 and CC0 1.0 records. Source licence labels
are preserved in the provenance sidecar. The requirements and citation supplied
with the PEP725 extract are in `raw/pep725/README.txt`, including the acknowledgement
“Data were provided by the members of the PEP725 project” and the Templ et al.
(2018) PEP725 reference, DOI `10.1007/s00484-018-1512-8`. TEMPO and DWD attribution
remain linked through the original complete tables and provenance records.

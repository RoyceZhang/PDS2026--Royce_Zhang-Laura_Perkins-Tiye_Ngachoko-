> This product uses the Census Bureau Data API but is not endorsed or certified by the Census Bureau.

# Opioid policy evaluation: county-year data

This folder contains Royce's cleaning and integration contribution for the FL
and WA policy project. It supplies a five-state 2006–2015 panel for subsequent
pre-post and difference-in-differences analysis. It does not contain the team's
final plots, regressions, or stakeholder report.

## Contents

| Location | Files |
|---|---|
| `20-Python_Code/` | `clean_arcos.py`, `clean_mortality.py`, `merge_data.py`, `validate_data.py`, `build_crosswalk.py`, `pipeline_utils.py` |
| `10-Clean_Data/` | ARCOS county/drug tables, strict and D1 mortality tables, strict and D1 merged panels, crosswalk, and three covariate inputs |
| `00-Source_Data/nber.csv` | Existing NBER county reference used by the crosswalk script |
| `30-Exported_Files/data_quality_report.md` | Actual coverage, matching, validation, and limitations |
| `data_dictionary.md` | All 49 merged columns, units, sources, and missingness |
| `GIT_COMMIT_AND_PR.md` | Commit commands, PR title/body, and Git LFS instructions |

No raw ARCOS ZIP, raw course mortality files, temporary checkpoints, old partial
panels, or run logs are included. There are no required external audit JSON files.
Generated Parquet files contain provenance in their `pds_pipeline` metadata.
The original complete work remains separate from this submission folder.

## Data and units

- States: Arizona, Florida, North Carolina, South Carolina, Washington.
- Unit: one county-year; text `fips` contains five digits, including leading zeros.
- Both merged panels preserve **267 counties × 10 years = 2,670 rows**, 49 columns.
- ARCOS outputs contain 2,650 observed county-years and 32,076 county-year-drug
  rows across 14 drugs. Shipments proxy availability, not patient prescriptions.
- The patient-facing S-sales recipient list is explicit in `clean_arcos.py`.
  Distributors, reverse distributors, laboratories, manufacturers, mail-order,
  and central-fill recipients are excluded from the local supply definition.
- MME uses the supplied transaction total. A 100,000-row source sample matched
  `CALC_BASE_WT_IN_GM * 1000 * MME_Conversion_Factor` within numerical tolerance.
  Raw dates are ISO `YYYY-MM-DD`. Drug names and missing-aware counts are retained.
- Population/race and SNAP inputs were prepared in Laura's ACS branch. PEP is
  used because it covers small counties for the full study period. Hispanic
  ethnicity overlaps race; do not add it to race-alone totals. SNAP is July
  recipients. LAUS was prepared by Tiye; the actual 506,757-byte local file
  matched the Git LFS object's SHA-256. These three inputs are included unchanged.
- Shares are fractions, LAUS rates are percentages, and mortality rates are
  deaths per 100,000 persons. No complete-case deletion or zero imputation occurs.

## Mortality endpoint decision

The assigned source reports drug-overdose categories D1 (unintentional,
X40–X44), D2 (suicide, X60–X64), D3 (homicide, X85), and D4 (undetermined,
Y10–Y14) separately. D9 and alcohol/non-drug categories are excluded. These
counts do not identify opioid involvement. The extract omits both small and
zero counts, so an absent category is unknown, not a confirmed zero.

- `mortality_county_year.parquet` and `merged_county_year.parquet`: strict
  all-intents totals require all four components. None are complete in this
  extract, so generic `overdose_deaths` remains NaN for all 2,670 county-years.
- Files ending `_unintentional.parquet`: explicit D1-only alternatives with
  **1,095 observed unintentional drug-overdose counts**. They retain missing
  county-years and include the definition column. This endpoint is not yet a
  final group decision.
- Component counts and the sum of reported components remain in both versions.
  The latter is a lower bound and must not be presented as an exact total.

Twenty county-years lack an eligible shipment observation. One Lee County,
FL, 2010 shipment sum has a missing MME measurement, exposed by its observed-
record count. Three unmatched aggregates represent 23 transactions without a
buyer county. See the quality report; conservative readiness flags remain false.

## Reproduce from the included aggregates

Python 3.10+ and the packages in `requirements.txt` are required. Run from the
project root:

```bash
python -m pip install -r requirements.txt
python 20-Python_Code/build_crosswalk.py
python 20-Python_Code/merge_data.py
python 20-Python_Code/validate_data.py --self-test
python 20-Python_Code/validate_data.py
```

These commands do not open the raw ARCOS ZIP. The default merger writes both
strict and D1 panels. `--endpoint strict` or `--endpoint unintentional` writes
only the explicitly selected version, preserving its filename suffix.

To regenerate from raw inputs kept outside Git, set `ARCOS_INPUT` and
`MORTALITY_DIR` to your own local paths, then run:

```bash
python 20-Python_Code/clean_mortality.py --input-dir "$MORTALITY_DIR"
python 20-Python_Code/clean_arcos.py --input "$ARCOS_INPUT"
python 20-Python_Code/merge_data.py
python 20-Python_Code/validate_data.py
```

The ARCOS script streams the ZIP member without fully extracting it. For a
small test, add `--max-chunks 1 --output-dir /tmp/pds-arcos-sample`; sample
provenance prevents those outputs being used as a full-source input. The
full run previously read 759,908,394 records in about 28.5 minutes. This lean
package reuses its real aggregates. The new raw-reading path was tested on
synthetic data, not by repeating the 245.7 GB stream. Real mortality cleaning,
crosswalk construction, and both complete merges were rerun with these scripts;
all seven corresponding datasets matched the earlier validated values.

The shared helper handles identifiers and Parquet metadata. Keep it beside the
five main scripts. There is no separate recipient-derivation or audit-file step.

## Remaining team work

FL's assigned policy year is 2010 and WA's is 2012. Preserve 2006–2015 in the
master; WA's final window, the intervention year's classification, mortality
endpoint, and control assignments remain group choices. At least three control
states per treated state are required. No treatment/post indicators or final
models are imposed here. Income and BEA RPP remain unresolved design items.

Copy this folder's contents into the existing team repository, retaining
teammates' files. Intermediate Parquet files should be committed through Git
LFS, not by browser drag-and-drop. See `GIT_COMMIT_AND_PR.md`.

# Data quality report

## Actual datasets

- Both merged panels: **2,670 rows × 49 columns**.
- ARCOS county-year table: 2,650 rows; county-year-drug table:
  32,076 rows, 14 drugs.
- Original ARCOS full stream: 759,908,394 records;
  approximately 28.5 minutes. The lean
  package reuses those real aggregates; it did not repeat the raw ZIP scan.

| State | Counties | Panel rows | Missing shipment totals | D1 observed |
|---|---:|---:|---:|---:|
| AZ | 15 | 150 | 0 | 86 |
| FL | 67 | 670 | 3 | 349 |
| NC | 100 | 1000 | 17 | 354 |
| SC | 46 | 460 | 0 | 149 |
| WA | 39 | 390 | 0 | 157 |

## Checks passed

Five-digit text FIPS, unique county-year/drug keys, lowercase columns, valid
state/FIPS agreement, positive denominators, unchanged panel row counts,
drug/county quantities and observation-count reconciliation, rate formulas,
race-alone sums, and LAUS labor-force identity passed. Hispanic ethnicity was
not added to race-alone totals. Missing unemployment rates:
0; missing SNAP counts:
0.

## Missing and unmatched shipments

Transaction-weighted FIPS match: 99.99997032%;
net-MME match: 99.99999875%.
3 unmatched groups represent
23 source transactions. Their aggregate
values are retained in the ARCOS Parquet metadata; no county was guessed.
The source records lack buyer county names.

County-years without an eligible shipment observation remain NaN:
- Glades County, FL: 2006, 2007, 2008
- Camden County, NC: 2006, 2007, 2008, 2009, 2010, 2011, 2012, 2013, 2014, 2015
- Hyde County, NC: 2006, 2007, 2008, 2009, 2010, 2011, 2012

1 county-year shipment sum is incomplete. Lee County, FL, 2010
has one missing transaction MME/base-weight value: its total sums 110,284 of
110,285 observed transaction records. Observation-count columns retain this
distinction. Missing dosage units are not replaced with zero or interpreted
as exhaustive pill counts. No complete-case deletion was performed.

## Mortality limitation

Strict all-intents totals observed: 0.
The source omits small and zero counts separately for D1–D4. An omitted category
cannot be assumed zero, so exact totals remain NaN when components are missing.
The reported-component sum is a lower bound, not an exact total.

The explicitly labeled D1 alternative has 1,095
observed unintentional **drug-overdose** counts. It is a separate endpoint and
has not been selected as the group's final outcome. These data are not
opioid-specific. Suppression-related selection remains a modeling concern.

## Validation scope

Real crosswalk and mortality cleaning were rerun with these lean scripts.
Both merged panels were rebuilt from the packaged inputs and compared against
the previous validated 49-column outputs. The lean ARCOS raw-reading path was
checked on synthetic data, including multiple chunks, negative/missing values,
recipient filtering, exact county aliases, and sample-file rejection. The real
ARCOS quantities were reused unchanged from the original full-source run.

No raw ZIP, checkpoints, run logs, or external JSON audits are required by the
submission. Provenance is embedded in Parquet. The data remain subject to the
missingness and endpoint decisions above; validation does not imply that all
outcomes are complete or that the final statistical analysis is finished.

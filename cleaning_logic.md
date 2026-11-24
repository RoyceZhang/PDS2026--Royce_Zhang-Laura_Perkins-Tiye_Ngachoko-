# ARCOS Cleaning Logic

## Goal
Transform raw ARCOS transaction data into a county-year panel for opioid shipment analysis.

## Input
- Source file: `arcos_all.zip` (contains `arcos_all.tsv`)
- Processing mode: chunked reading to handle very large data safely

## Core Steps
1. Keep only required columns:
   - Buyer state, buyer county, transaction date, drug name
   - Shipment quantity fields: base weight, dosage unit, MME
2. Standardize geography:
   - Uppercase state and county values
   - Normalize county names (remove suffixes like COUNTY/PARISH)
   - Keep 50 states + DC by default
3. Filter opioid records:
   - Match drug names against an opioid keyword list (for example: oxycodone, hydrocodone, fentanyl, methadone)
4. Parse and clean values:
   - Convert transaction date to year
   - Convert shipment metrics to numeric values
   - Drop rows missing key identifiers (state/county/year)
5. Aggregate to county-year:
   - Group by state, county, year
   - Summarize:
     - shipment_records (count of transactions)
     - opioid_calc_base_wt_gm (sum)
     - opioid_dosage_unit (sum)
     - opioid_mme (sum)
6. Export final dataset:
   - CSV output (default)
   - Optional Parquet output

## Output Schema
- state
- county
- year
- shipment_records
- opioid_calc_base_wt_gm
- opioid_dosage_unit
- opioid_mme

## Notes
- The script prints chunk progress during execution.
- Output files are written after all chunks are processed.

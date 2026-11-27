"""Check the submission datasets and regenerate the concise quality report."""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from clean_arcos import reconcile
from pipeline_utils import ROOT, RACES, check_keys, read_metadata, read_table


def validate(directory, report_path):
    county = read_table(directory / "arcos_county_year.parquet")
    drug = read_table(directory / "arcos_county_year_drug.parquet")
    panel = read_table(directory / "merged_county_year.parquet")
    d1 = read_table(directory / "merged_county_year_unintentional.parquet")
    metadata = read_metadata(directory / "arcos_county_year.parquet")
    if metadata.get("scope") != "full_input" or metadata.get("buyer_scope") != "patient-facing":
        raise ValueError("A full-input patient-facing ARCOS dataset is required.")
    check_keys(county)
    check_keys(drug, ("fips", "year", "drug_name"))
    reconcile(drug, county)
    for frame in [panel, d1]:
        check_keys(frame)
        if len(frame) != 2670 or frame.fips.nunique() != 267:
            raise ValueError("Unexpected five-state county-year coverage.")
        if not frame.population.gt(0).all():
            raise ValueError("Invalid population denominator.")
        for result, expected in [(frame.mme_per_capita, frame.total_mme / frame.population),
                                 (frame.overdose_death_rate, frame.overdose_deaths / frame.population * 100000),
                                 (frame.snap_rate, frame.snap_recipients / frame.population)]:
            np.testing.assert_allclose(result, expected, equal_nan=True)
        for race in RACES:
            np.testing.assert_allclose(frame[race + "_share"], frame[race + "_pop"] / frame.population)
        race_total = frame[[r + "_pop" for r in RACES if r != "hispanic"]].sum(axis=1)
        np.testing.assert_allclose(race_total, frame.population)
        np.testing.assert_allclose(frame.labor_force, frame.employed + frame.unemployed)
    np.testing.assert_allclose(d1.overdose_deaths, d1.unintentional_overdose_deaths, equal_nan=True)
    np.testing.assert_allclose(panel.overdose_deaths, panel[[r + "_overdose_deaths" for r in
                               ["unintentional", "suicide", "homicide", "undetermined"]]].sum(axis=1, min_count=4), equal_nan=True)
    missing = panel.loc[panel.total_mme.isna(), ["state", "county", "year"]]
    incomplete = panel.loc[panel.total_mme_observed_records.lt(panel.shipment_records), ["county", "year", "shipment_records", "total_mme_observed_records"]]
    coverage = "\n".join(f"| {state} | {g.fips.nunique()} | {len(g)} | {g.total_mme.isna().sum()} | {g.unintentional_overdose_deaths.notna().sum()} |"
                         for state, g in panel.groupby("state"))
    absence = "\n".join(f"- {county_name}, {state}: {', '.join(str(int(y)) for y in group.year)}"
                         for (state, county_name), group in missing.groupby(["state", "county"]))
    report = f"""# Data quality report

## Actual datasets

- Both merged panels: **{len(panel):,} rows × {len(panel.columns)} columns**.
- ARCOS county-year table: {len(county):,} rows; county-year-drug table:
  {len(drug):,} rows, {drug.drug_name.nunique()} drugs.
- Original ARCOS full stream: {metadata.get('source_records', 0):,} records;
  approximately {metadata.get('elapsed_seconds', 0) / 60:.1f} minutes. The lean
  package reuses those real aggregates; it did not repeat the raw ZIP scan.

| State | Counties | Panel rows | Missing shipment totals | D1 observed |
|---|---:|---:|---:|---:|
{coverage}

## Checks passed

Five-digit text FIPS, unique county-year/drug keys, lowercase columns, valid
state/FIPS agreement, positive denominators, unchanged panel row counts,
drug/county quantities and observation-count reconciliation, rate formulas,
race-alone sums, and LAUS labor-force identity passed. Hispanic ethnicity was
not added to race-alone totals. Missing unemployment rates:
{panel.unemployment_rate.isna().sum()}; missing SNAP counts:
{panel.snap_recipients.isna().sum()}.

## Missing and unmatched shipments

Transaction-weighted FIPS match: {metadata['matched_transaction_fraction']:.8%};
net-MME match: {metadata['matched_net_mme_fraction']:.8%}.
{metadata.get('unmatched_groups', 0)} unmatched groups represent
{metadata.get('unmatched_records', 0)} source transactions. Their aggregate
values are retained in the ARCOS Parquet metadata; no county was guessed.
The source records lack buyer county names.

County-years without an eligible shipment observation remain NaN:
{absence}

{len(incomplete)} county-year shipment sum is incomplete. Lee County, FL, 2010
has one missing transaction MME/base-weight value: its total sums 110,284 of
110,285 observed transaction records. Observation-count columns retain this
distinction. Missing dosage units are not replaced with zero or interpreted
as exhaustive pill counts. No complete-case deletion was performed.

## Mortality limitation

Strict all-intents totals observed: {panel.overdose_deaths.notna().sum()}.
The source omits small and zero counts separately for D1–D4. An omitted category
cannot be assumed zero, so exact totals remain NaN when components are missing.
The reported-component sum is a lower bound, not an exact total.

The explicitly labeled D1 alternative has {d1.overdose_deaths.notna().sum():,}
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
"""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report)
    print(f"Validated {panel.shape}; drug rows={len(drug):,}; wrote {report_path.name}.")


def self_test():
    """Exercise edge cases without opening the real ARCOS archive."""
    import tempfile
    from types import SimpleNamespace
    from clean_arcos import process
    from clean_mortality import clean_mortality
    from merge_data import load_arcos
    from pipeline_utils import write_parquet

    raw = pd.DataFrame({
        "BUYER_STATE": ["AZ"] * 3 + ["FL"] * 5,
        "BUYER_COUNTY": ["Apache"] * 3 + ["Saint Johns", "Saint Johns", None, "Saint Johns", "Saint Johns"],
        "BUYER_BUS_ACT": ["RETAIL PHARMACY"] * 4 + ["DISTRIBUTOR", "PRACTITIONER", "PRACTITIONER", "PRACTITIONER"],
        "TRANSACTION_CODE": ["S"] * 6 + ["R", "S"],
        "DRUG_NAME": ["OXYCODONE", "OXYCODONE", "MORPHINE"] + ["HYDROCODONE"] * 5,
        "TRANSACTION_DATE": ["2006-01-02"] * 7 + ["bad"],
        "MME": [100, -20, np.nan, 200, 1000, 5, 50, 50],
        "DOSAGE_UNIT": [10, -2, np.nan, 20, 100, 1, 5, 5],
        "CALC_BASE_WT_IN_GM": [0.1, -0.02, np.nan, 0.2, 1, 0.005, 0.05, 0.05],
    })
    crosswalk = pd.DataFrame({"fips": ["04001", "12109"], "state": ["AZ", "FL"],
                              "county": ["Apache County", "St. Johns County"], "county_key": ["APACHE", "STJOHNS"]})
    args = SimpleNamespace(states=["AZ", "FL"], start_year=2006, end_year=2006, date_format="%Y-%m-%d", max_chunks=None)
    drug, county, metadata = process([raw], args, crosswalk)
    split_drug, split_county, _ = process([raw.iloc[:1], raw.iloc[1:4], raw.iloc[4:]], args, crosswalk)
    pd.testing.assert_frame_equal(drug, split_drug, check_dtype=False)
    pd.testing.assert_frame_equal(county, split_county, check_dtype=False)
    assert county.set_index("fips").loc["04001", "total_mme"] == 80
    assert county.set_index("fips").loc["12109", "total_mme"] == 200
    assert drug.loc[drug.drug_name.eq("MORPHINE"), "total_mme"].isna().all()
    assert metadata["unmatched_records"] == 1
    try:
        check_keys(pd.concat([county, county]))
    except ValueError:
        pass
    else:
        raise AssertionError("Duplicate keys were accepted.")
    with tempfile.TemporaryDirectory() as temp:
        directory = Path(temp)
        sample = directory / "sample.parquet"
        write_parquet(county, sample, {"scope": "sample", "buyer_scope": "patient-facing"})
        try:
            load_arcos(sample)
        except ValueError:
            pass
        else:
            raise AssertionError("Sample data were accepted as a full run.")
        source = pd.DataFrame({"County Code": ["04001", "12109"], "Year": ["2006", "2006"],
                               "Drug/Alcohol Induced Cause Code": ["D1", "D1"], "Deaths": ["12", "20"]})
        source.to_csv(directory / "mortality.txt", sep="\t", index=False)
        population = crosswalk[["fips"]].copy(); population["year"] = 2006
        deaths, _, _ = clean_mortality(directory, population, 2006, 2006)
        assert deaths.overdose_deaths.isna().all()
        assert deaths.overdose_deaths_reported_lower_bound.tolist() == [12, 20]
    print("Focused self-checks passed: chunks, recipients, aliases, missing/negative values, duplicate keys, mortality, and sample rejection.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "10-Clean_Data")
    parser.add_argument("--report", type=Path, default=ROOT / "30-Exported_Files/data_quality_report.md")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    else:
        validate(args.data_dir, args.report)

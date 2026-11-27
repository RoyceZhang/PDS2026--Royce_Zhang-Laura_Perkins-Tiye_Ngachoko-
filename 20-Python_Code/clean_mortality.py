"""Clean assigned mortality files; omitted categories remain missing."""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline_utils import ROOT, STATES, check_keys, fips_string, read_table, write_parquet

CAUSES = {
    "D1": "unintentional_overdose_deaths",
    "D2": "suicide_overdose_deaths",
    "D3": "homicide_overdose_deaths",
    "D4": "undetermined_overdose_deaths",
}


def clean_mortality(source_dir, population, start=2006, end=2015):
    base = population.rename(columns={"county_fips": "fips"})[["fips", "year"]].copy()
    base["fips"] = fips_string(base.fips)
    base = base[base.year.between(start, end)].copy()
    check_keys(base)
    frames, source_audit = [], []
    for path in sorted(Path(source_dir).glob("*.txt")):
        raw = pd.read_csv(path, sep="\t", dtype="string")
        required = ["County Code", "Year", "Drug/Alcohol Induced Cause Code", "Deaths"]
        if not set(required).issubset(raw.columns):
            raise ValueError(f"Unexpected source schema in {path.name}")
        # Footer/query/citation lines have no County Code. Do not infer a county.
        data = raw.loc[raw["County Code"].notna(), required].copy()
        data["fips"] = fips_string(data["County Code"])
        data["year"] = pd.to_numeric(data.Year, errors="raise").astype(int)
        in_scope = data.fips.str[:2].isin(STATES.values()) & data.year.between(start, end)
        data = data[in_scope].copy()
        data["cause_code"] = data["Drug/Alcohol Induced Cause Code"].str.strip()
        data["deaths"] = pd.to_numeric(data.Deaths, errors="coerce")
        # Explicit source suppression, if ever present, remains missing.
        numeric = data.deaths.dropna()
        if numeric.lt(0).any() or numeric.mod(1).ne(0).any():
            raise ValueError("Mortality values are not nonnegative integer counts.")
        if data.duplicated(["fips", "year", "cause_code"]).any():
            raise ValueError(f"Duplicate county/year/cause in {path.name}")
        source_audit.append({"file": path.name, "study_records": len(data),
                             "cause_counts": {str(k): int(v) for k, v in data.cause_code.value_counts().items()}})
        frames.append(data[["fips", "year", "cause_code", "deaths"]])
    if not frames:
        raise ValueError("No assigned mortality text files were found.")
    long = pd.concat(frames, ignore_index=True)
    if long.duplicated(["fips", "year", "cause_code"]).any():
        raise ValueError("Duplicate county/year/cause across source files.")
    overdose = long[long.cause_code.isin(CAUSES)].copy()
    wide = overdose.pivot(index=["fips", "year"], columns="cause_code", values="deaths")
    wide = wide.reindex(columns=list(CAUSES)).rename(columns=CAUSES).reset_index()
    wide.columns.name = None
    out = base.merge(wide, on=["fips", "year"], how="left", validate="one_to_one")
    columns = list(CAUSES.values())
    out["overdose_categories_observed"] = out[columns].notna().sum(axis=1)
    out["overdose_deaths_reported_lower_bound"] = out[columns].sum(axis=1, min_count=1)
    # A missing component can be zero or a suppressed count; exact total unknown.
    out["overdose_deaths"] = out[columns].sum(axis=1, min_count=4)
    out["mortality_status"] = np.select(
        [out.overdose_categories_observed.eq(4), out.overdose_categories_observed.gt(0)],
        ["all_four_categories_observed", "incomplete_reported_categories"],
        default="no_overdose_categories_reported")
    out["mortality_definition"] = "all_intents_strict_total_D1_D2_D3_D4"
    check_keys(out)
    audit = {"rows": len(out), "source_files": source_audit,
             "source_long_rows": len(long), "overdose_cause_rows": len(overdose),
             "strict_total_observed": int(out.overdose_deaths.notna().sum()),
             "unintentional_observed": int(out.unintentional_overdose_deaths.notna().sum()),
             "any_overdose_category_observed": int(out.overdose_categories_observed.gt(0).sum()),
             "cause_definitions": CAUSES,
             "missingness_note": "Source query disables zero and suppressed cells. Missing components are unknown, never confirmed zero. The reported sum is a lower bound, not an exact all-intents total.",
             "opioid_specific": False}
    return out, long, audit


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--population", type=Path, default=ROOT / "10-Clean_Data/pep_county_race_2006_2015.parquet")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "10-Clean_Data")
    args = parser.parse_args()
    data, _, audit = clean_mortality(args.input_dir, read_table(args.population))
    audit["scope"] = "full_input"
    write_parquet(data, args.output_dir / "mortality_county_year.parquet", {**audit, "endpoint": "strict_all_intents"})
    alternative = data.copy()
    alternative["overdose_deaths"] = alternative.unintentional_overdose_deaths
    alternative["mortality_definition"] = "unintentional_drug_overdose_D1_only"
    alternative["mortality_status"] = np.where(alternative.overdose_deaths.notna(), "D1_observed", "D1_not_reported_zero_or_suppressed")
    write_parquet(alternative, args.output_dir / "mortality_county_year_unintentional.parquet", {**audit, "endpoint": "unintentional_D1_only"})
    print(f"Saved {len(data):,} county-years; strict totals={audit['strict_total_observed']}; D1 observed={audit['unintentional_observed']}.")

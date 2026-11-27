"""Build strict and D1 county-year panels using validated population-based joins."""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline_utils import ROOT, STATES, RACES, check_keys, fips_string, read_table, read_metadata, write_parquet

SOURCE_COLUMNS = {
    "arcos": ["total_mme", "shipment_records", "dosage_units", "base_weight_gm",
              "total_mme_observed_records", "dosage_units_observed_records", "base_weight_gm_observed_records"],
    "mortality": ["overdose_deaths"],
    "laus": ["labor_force", "employed", "unemployed", "unemployment_rate"],
    "snap": ["snap_recipients"],
}


def standardize(frame, name, states, start_year, end_year):
    frame = frame.copy()
    if name in {"pep", "snap"}:
        frame = frame.rename(columns={"county_fips": "fips", "state_abbreviation": "state", "total_pop": "population"})
    frame["fips"] = fips_string(frame.fips)
    frame["year"] = pd.to_numeric(frame.year, errors="raise")
    if frame.year.isna().any() or (frame.year % 1 != 0).any():
        raise ValueError(f"{name}: invalid year.")
    frame["year"] = frame.year.astype("int64")
    # LAUS county_fips is only three digits; its full fips is used above.
    expected_state = frame.fips.str[:2].map({v: k for k, v in STATES.items()})
    keep = expected_state.isin(states) & frame.year.between(start_year, end_year)
    frame = frame[keep].copy()
    if "state" in frame:
        frame["state"] = frame.state.astype("string").str.upper().str.strip()
    else:
        frame["state"] = expected_state[keep]
    check_keys(frame)
    return frame


def numeric(frame, columns):
    for column in columns:
        frame[column] = pd.to_numeric(frame[column], errors="raise").astype("float64")
        if np.isinf(frame[column]).any():
            raise ValueError(f"Infinite values in {column}.")


def build_panel(pep, sources, states, start_year, end_year):
    panel = standardize(pep, "pep", states, start_year, end_year)
    numeric(panel, ["population"] + [race + "_pop" for race in RACES])
    if not panel.population.gt(0).all():
        raise ValueError("Population must be positive and nonmissing.")
    if not panel.groupby("fips").year.apply(lambda y: set(y) == set(range(start_year, end_year + 1))).all():
        raise ValueError("PEP does not provide a balanced panel for requested years.")
    if set(panel.state) != set(states):
        raise ValueError("PEP is missing a requested state.")
    report = {"base_rows": len(panel), "merges": {}, "issues": []}
    unmatched_tables = {}
    for name, columns in SOURCE_COLUMNS.items():
        frame = sources.get(name)
        if frame is None:
            for column in columns:
                panel[column] = np.nan
            panel[name + "_merge_status"] = "source_unavailable"
            report["merges"][name] = {"available": False, "rows_before": len(panel), "rows_after": len(panel), "unmatched_base_rows": len(panel)}
            continue
        frame = standardize(frame, name, states, start_year, end_year)
        numeric(frame, columns)
        if name == "arcos":
            counts = ["shipment_records", "total_mme_observed_records", "dosage_units_observed_records", "base_weight_gm_observed_records"]
            if frame[counts].isna().any().any() or (frame[counts] < 0).any().any() or frame[counts].mod(1).ne(0).any().any():
                raise ValueError("ARCOS record counts must be nonnegative observed integers.")
            for column in counts[1:]:
                if frame[column].gt(frame.shipment_records).any():
                    raise ValueError("Observed measurement counts exceed shipment records.")
            incomplete = int(frame.total_mme_observed_records.lt(frame.shipment_records).sum())
            report["arcos_incomplete_mme_county_years"] = incomplete
            if incomplete:
                report["issues"].append("Some ARCOS sums have missing transaction MME; observed-record sums are incomplete.")
        if name == "mortality":
            deaths = frame.overdose_deaths.dropna()
            if deaths.lt(0).any() or deaths.mod(1).ne(0).any():
                raise ValueError("Mortality must contain nonnegative integer counts, not rates.")
        if name == "laus" and not frame.unemployment_rate.dropna().between(0, 100).all():
            raise ValueError("Unemployment rate must be expressed as a percent, between 0 and 100.")
        if name == "snap" and frame.snap_recipients.dropna().lt(0).any():
            raise ValueError("Negative SNAP recipient counts.")
        selected = ["fips", "year"] + columns
        if name == "mortality" and "mortality_status" in frame:
            selected.append("mortality_status")
        if name == "mortality":
            optional = ["mortality_definition", "unintentional_overdose_deaths", "suicide_overdose_deaths",
                        "homicide_overdose_deaths", "undetermined_overdose_deaths",
                        "overdose_categories_observed", "overdose_deaths_reported_lower_bound"]
            selected.extend(column for column in optional if column in frame)
        before = len(panel)
        panel = panel.merge(frame[selected], on=["fips", "year"], how="left", validate="one_to_one", indicator=True)
        unmatched_tables[name + "_base_unmatched"] = panel.loc[panel._merge == "left_only", ["fips", "year"]].copy()
        extras = frame.merge(panel[["fips", "year"]], on=["fips", "year"], how="left", validate="one_to_one", indicator=True)
        unmatched_tables[name + "_source_unmatched"] = extras.loc[extras._merge == "left_only", ["fips", "year"]].copy()
        missing_keys = int(panel._merge.eq("left_only").sum())
        panel[name + "_merge_status"] = panel._merge.map({"both": "matched", "left_only": "not_matched"}).astype("string")
        panel = panel.drop(columns="_merge")
        if len(panel) != before:
            raise ValueError(f"{name} join changed the base row count.")
        report["merges"][name] = {"available": True, "source_rows": len(frame), "rows_before": before,
                                   "rows_after": len(panel), "unmatched_base_rows": missing_keys,
                                   "unmatched_source_rows": len(unmatched_tables[name + "_source_unmatched"])}
    panel["mme_per_capita"] = panel.total_mme / panel.population
    panel["overdose_death_rate"] = panel.overdose_deaths / panel.population * 100000
    if "unintentional_overdose_deaths" in panel:
        panel["unintentional_overdose_death_rate"] = panel.unintentional_overdose_deaths / panel.population * 100000
        panel["reported_overdose_death_rate_lower_bound"] = panel.overdose_deaths_reported_lower_bound / panel.population * 100000
    panel["snap_rate"] = panel.snap_recipients / panel.population
    for race in RACES:
        panel[race + "_share"] = panel[race + "_pop"] / panel.population
        if not panel[race + "_share"].between(0, 1).all():
            raise ValueError(f"Invalid {race} population share.")
    race_total = panel[[r + "_pop" for r in RACES if r != "hispanic"]].sum(axis=1, min_count=6)
    report["race_total_discrepancies"] = int(race_total.ne(panel.population).sum())
    report["snap_share_above_one"] = int(panel.snap_rate.gt(1).sum())
    if report["race_total_discrepancies"]:
        report["issues"].append("Race-alone totals do not match population on some rows.")
    if report["snap_share_above_one"]:
        report["issues"].append("Some SNAP counts exceed population; investigate before analysis.")
    check_keys(panel)
    report["rows"] = len(panel)
    report["columns"] = len(panel.columns)
    report["dtypes"] = {column: str(panel[column].dtype) for column in panel}
    report["states"] = sorted(panel.state.unique().tolist())
    report["years"] = [int(panel.year.min()), int(panel.year.max())]
    report["missing_inputs"] = [name for name in SOURCE_COLUMNS if sources.get(name) is None]
    report["missing_values"] = {column: {"count": int(panel[column].isna().sum()), "fraction": float(panel[column].isna().mean())} for column in panel}
    report["coverage"] = [{"state": s, "year": int(y), "rows": int(len(group)), "counties": int(group.fips.nunique())}
                          for (s, y), group in panel.groupby(["state", "year"])]
    report["analysis_ready"] = not report["missing_inputs"] and not report["issues"] and panel.total_mme.notna().any().item() and panel.overdose_deaths.notna().any().item() and all(
        item["unmatched_base_rows"] == 0 and item["unmatched_source_rows"] == 0
        for name, item in report["merges"].items() if name != "mortality")
    report["mortality_note"] = "Absent mortality records remain missing; absent counts cannot distinguish zero from suppression. Observed suppression labels, if supplied, are preserved."
    if "mortality_definition" in panel:
        report["mortality_definitions"] = panel.mortality_definition.dropna().unique().tolist()
        report["observed_primary_mortality_county_years"] = int(panel.overdose_deaths.notna().sum())
        if panel.overdose_deaths.isna().all():
            report["issues"].append("No exact primary mortality totals are observable from the supplied cause-suppressed extract; use explicit sensitivity endpoints or obtain all-intents totals.")
    return panel.sort_values(["fips", "year"]).reset_index(drop=True), report, unmatched_tables


def load_arcos(path):
    frame = read_table(path)
    metadata = read_metadata(path)
    if metadata.get("scope") != "full_input" or metadata.get("buyer_scope") != "patient-facing":
        raise ValueError("ARCOS provenance must identify a full-input, patient-facing run. Sample or unmarked files cannot be used.")
    return frame, metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "10-Clean_Data")
    parser.add_argument("--endpoint", choices=["both", "strict", "unintentional"], default="both")
    args = parser.parse_args()
    directory = args.data_dir
    arcos, provenance = load_arcos(directory / "arcos_county_year.parquet")
    pep = read_table(directory / "pep_county_race_2006_2015.parquet")
    common = {"arcos": arcos, "laus": read_table(directory / "laus_county_year.parquet"),
              "snap": read_table(directory / "saipe_snap_2006_2015.parquet")}
    endpoints = ["strict", "unintentional"] if args.endpoint == "both" else [args.endpoint]
    for endpoint in endpoints:
        suffix = "" if endpoint == "strict" else "_unintentional"
        sources = {**common, "mortality": read_table(directory / f"mortality_county_year{suffix}.parquet")}
        panel, report, _ = build_panel(pep, sources, list(STATES), 2006, 2015)
        metadata = {"scope": "full_input", "endpoint": endpoint, "buyer_scope": "patient-facing",
                    "arcos_source_records": provenance.get("source_records"), "validation": report}
        output = directory / f"merged_county_year{suffix}.parquet"
        write_parquet(panel, output, metadata)
        print(f"Saved {output.name}: {panel.shape}; analysis_ready={report['analysis_ready']}")

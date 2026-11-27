"""Stream patient-facing opioid sales into county-year and drug aggregates."""

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import time
import zipfile

import numpy as np
import pandas as pd

from pipeline_utils import ROOT, STATES, apply_county_aliases, check_keys, normalize_county, read_table, write_parquet

KEYS = ["state", "county_key", "year", "drug_name"]

OPIOIDS = ["OPIUM", "CODEINE", "MORPHINE", "HYDROCODONE", "OXYCODONE",
           "HYDROMORPHONE", "OXYMORPHONE", "FENTANYL", "METHADONE",
           "BUPRENORPHINE", "TAPENTADOL", "TRAMADOL", "MEPERIDINE",
           "LEVORPHANOL", "DIHYDROCODEINE"]


METRICS = ["total_mme", "dosage_units", "base_weight_gm"]


COUNTS = ["shipment_records"] + [m + "_observed_records" for m in METRICS]


PATIENT_FACING = {
    "CHAIN PHARMACY", "RETAIL PHARMACY", "HOSPITAL/CLINIC", "HOSP/CLINIC",
    "HOSP/CLINIC-VA", "PRACTITIONER", "PRACTITIONER-DW/30", "PRACTITIONER-DW/100",
    "PRACTITIONER-DW/275", "MLP-NURSE PRACTITIONER", "MLP-PHYSICIAN ASSISTANT",
    "MLP-OPTOMETRIST", "MLP-PODIATRIST", "MAINT & DETOX", "COMP/MAINT/DETOX",
    "AUTOMATED DISPENSING SYSTEM", "HOSP/CLINIC FED", "HOSP/CLINIC- MIL",
    "PHARMACY - FED", "PHARMACY- MIL", "PRACTITIONER-MILITARY",
    "COMPOUND/DETOX", "DETOXIFICATION", "MAINTENANCE",
    "MLP-AMBULANCE SERVICE", "MLP-NATUROPATHIC PHYSICIAN",
    "MLP-NURSE PRACTITIONER-DW/100", "MLP-NURSE PRACTITIONER-DW/30",
    "MLP-PHYSICIAN ASSISTANT-DW/30",
    "MLP-PHYSICIAN ASSISTANT-DW/100", "MLP-REGISTERED PHARMACIST",
}


def parse_dates(series, date_format):
    text = series.astype("string").str.strip()
    if date_format == "%m%d%Y":
        text = text.where(~text.str.fullmatch(r"\d{7,8}", na=False), text.str.zfill(8))
    return pd.to_datetime(text, format=date_format, errors="coerce")


def summarize(frame, keys):
    """Keep observed-record counts so missingness survives every aggregation."""
    grouped = frame.groupby(keys, dropna=False, sort=False)
    out = grouped[METRICS].sum(min_count=1)
    if "shipment_records" in frame:
        counts = grouped[COUNTS].sum()
    else:
        counts = grouped.size().rename("shipment_records").to_frame()
        for metric in METRICS:
            counts[metric + "_observed_records"] = grouped[metric].count()
    return out.join(counts).reset_index()


def reconcile(drug, county):
    grouped = summarize(drug, ["fips", "year"]).sort_values(["fips", "year"]).reset_index(drop=True)
    county = county.sort_values(["fips", "year"]).reset_index(drop=True)
    pd.testing.assert_frame_equal(grouped[["fips", "year"]], county[["fips", "year"]], check_dtype=False)
    for metric in METRICS + COUNTS:
        np.testing.assert_allclose(grouped[metric].to_numpy(dtype=float),
                                   county[metric].to_numpy(dtype=float), equal_nan=True, rtol=1e-10)


def clean_chunk(raw, args, audit):
    audit["source_records"] += len(raw)
    state = raw.BUYER_STATE.astype("string").str.upper().str.strip()
    chunk = raw[state.isin(args.states)].copy()
    chunk["state"] = state.loc[chunk.index]
    chunk["buyer_business"] = chunk.BUYER_BUS_ACT.astype("string").str.upper().str.strip()
    chunk = chunk[chunk.buyer_business.isin(PATIENT_FACING)].copy()
    chunk = chunk[chunk.TRANSACTION_CODE.astype("string").str.strip().eq("S")].copy()
    chunk["drug_name"] = chunk.DRUG_NAME.astype("string").str.upper().str.strip().str.replace(r"\s+", " ", regex=True)
    chunk = chunk[chunk.drug_name.str.contains("|".join(OPIOIDS), na=False)].copy()
    dates = parse_dates(chunk.TRANSACTION_DATE, args.date_format)
    audit["invalid_dates"] += int(dates.isna().sum())
    chunk["year"] = dates.dt.year.astype("Int64")
    chunk = chunk[chunk.year.between(args.start_year, args.end_year)].copy()
    chunk["county_key"] = normalize_county(chunk.BUYER_COUNTY)
    before = chunk.county_key.copy()
    chunk = apply_county_aliases(chunk)
    audit["county_alias_records"] += int(before.ne(chunk.county_key).fillna(False).sum())
    for source, target in [("MME", "total_mme"), ("DOSAGE_UNIT", "dosage_units"), ("CALC_BASE_WT_IN_GM", "base_weight_gm")]:
        chunk[target] = pd.to_numeric(chunk[source], errors="coerce").replace([np.inf, -np.inf], np.nan)
        audit[target + "_missing_records"] += int(chunk[target].isna().sum())
        audit[target + "_negative_records"] += int(chunk[target].lt(0).sum())
    audit["selected_patient_records"] += len(chunk)
    return summarize(chunk, KEYS)


def process(reader, args, crosswalk):
    audit = Counter()
    aggregate = None
    started = time.monotonic()
    for index, raw in enumerate(reader, 1):
        group = clean_chunk(raw, args, audit)
        if not group.empty:
            aggregate = group if aggregate is None else summarize(pd.concat([aggregate, group], ignore_index=True), KEYS)
        if index % 10 == 0:
            print(f"Read {audit['source_records']:,} rows; selected {audit['selected_patient_records']:,} sales", flush=True)
        if args.max_chunks is not None and index >= args.max_chunks:
            break
    if aggregate is None or aggregate.empty:
        raise ValueError("No study records found; verify the input and filters.")
    check_keys(crosswalk, ("fips",))
    if crosswalk.duplicated(["state", "county_key"]).any():
        raise ValueError("Ambiguous state/county reference.")
    mapped = aggregate.merge(crosswalk[["state", "county_key", "fips", "county"]],
                             on=["state", "county_key"], how="left", validate="many_to_one")
    unmatched = mapped[mapped.fips.isna()].copy()
    drug = mapped[mapped.fips.notna()].drop(columns="county_key").copy()
    county = summarize(drug, ["fips", "state", "county", "year"])
    check_keys(drug, ("fips", "year", "drug_name"))
    check_keys(county)
    reconcile(drug, county)
    total_mme = mapped.total_mme.sum(min_count=1)
    metadata = dict(audit)
    metadata.update({"scope": "sample" if args.max_chunks is not None else "full_input",
                     "buyer_scope": "patient-facing", "states": args.states,
                     "years": [args.start_year, args.end_year], "date_format": args.date_format,
                     "mme_definition": "supplied MME transaction total in morphine milligrams",
                     "patient_facing_business_types": sorted(PATIENT_FACING), "opioid_keywords": OPIOIDS,
                     "unmatched_groups": len(unmatched), "unmatched_records": int(unmatched.shipment_records.sum()),
                     "matched_transaction_fraction": float(drug.shipment_records.sum() / mapped.shipment_records.sum()),
                     "matched_net_mme_fraction": float(drug.total_mme.sum() / total_mme) if pd.notna(total_mme) and total_mme != 0 else None,
                     "unmatched": json.loads(unmatched.drop(columns=["fips", "county"]).to_json(orient="records")),
                     "elapsed_seconds": round(time.monotonic() - started, 1)})
    return drug, county, metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--member", help="Explicit TSV member when the ZIP contains several")
    parser.add_argument("--crosswalk", type=Path, default=ROOT / "10-Clean_Data/county_crosswalk.parquet")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "10-Clean_Data")
    parser.add_argument("--states", nargs="+", choices=list(STATES), default=list(STATES))
    parser.add_argument("--start-year", type=int, default=2006)
    parser.add_argument("--end-year", type=int, default=2015)
    parser.add_argument("--date-format", default="%Y-%m-%d")
    parser.add_argument("--chunksize", type=int, default=1_000_000)
    parser.add_argument("--max-chunks", type=int)
    args = parser.parse_args()
    if args.chunksize < 1 or args.start_year > args.end_year or (args.max_chunks is not None and args.max_chunks < 1):
        parser.error("Invalid chunksize, year range, or max-chunks.")
    if args.max_chunks is not None and args.output_dir.resolve() == (ROOT / "10-Clean_Data").resolve():
        parser.error("Sample runs require a separate --output-dir.")
    crosswalk = read_table(args.crosswalk)
    columns = ["BUYER_STATE", "BUYER_COUNTY", "BUYER_BUS_ACT", "TRANSACTION_CODE", "DRUG_NAME",
               "TRANSACTION_DATE", "MME", "DOSAGE_UNIT", "CALC_BASE_WT_IN_GM"]
    options = dict(sep="\t", usecols=columns, dtype="string", chunksize=args.chunksize)
    if args.input.suffix.lower() == ".zip":
        with zipfile.ZipFile(args.input) as archive:
            members = [name for name in archive.namelist() if name.lower().endswith(".tsv") and not name.startswith("__MACOSX/")]
            if args.member is None and len(members) != 1:
                raise ValueError("Specify --member because there is not exactly one TSV.")
            with archive.open(args.member or members[0]) as stream:
                with pd.read_csv(stream, **options) as reader:
                    drug, county, metadata = process(reader, args, crosswalk)
    else:
        with pd.read_csv(args.input, **options) as reader:
            drug, county, metadata = process(reader, args, crosswalk)
    metadata["source_file"] = args.input.name
    write_parquet(drug.sort_values(["fips", "year", "drug_name"]), args.output_dir / "arcos_county_year_drug.parquet", metadata)
    write_parquet(county.sort_values(["fips", "year"]), args.output_dir / "arcos_county_year.parquet", metadata)
    print(f"Saved {len(county):,} county-years and {len(drug):,} county-year-drug rows ({metadata['scope']}).")


if __name__ == "__main__":
    main()

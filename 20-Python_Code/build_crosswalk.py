"""Extend the existing NBER reference to all five study states."""

import argparse

import pandas as pd

from pipeline_utils import ROOT, STATES, check_keys, fips_string, normalize_county, write_parquet


def build_crosswalk(source, states):
    raw = pd.read_csv(source, dtype="string")
    # Some NBER rows lack state names/codes, but contain full county FIPS.
    raw["fips"] = fips_string(raw["county_fips"])
    raw["state"] = raw.fips.str[:2].map({v: k for k, v in STATES.items()})
    out = raw.loc[raw.state.isin(states), ["fips", "state", "countycountyequivalent"]].copy()
    out = out.rename(columns={"countycountyequivalent": "county"}).drop_duplicates()
    check_keys(out, ("fips",))
    out["county_key"] = normalize_county(out.county)
    if out.county_key.isna().any() or out.duplicated(["state", "county_key"]).any():
        raise ValueError("Ambiguous or missing state/county names in the reference.")
    if set(out.state) != set(states):
        raise ValueError("Reference does not cover all requested states.")
    return out.sort_values("fips").reset_index(drop=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=str, default=ROOT / "00-Source_Data/nber.csv")
    parser.add_argument("--output", type=str, default=ROOT / "10-Clean_Data/county_crosswalk.parquet")
    parser.add_argument("--states", nargs="+", choices=list(STATES), default=list(STATES))
    args = parser.parse_args()
    crosswalk = build_crosswalk(args.input, args.states)
    write_parquet(crosswalk, args.output)
    print(crosswalk.groupby("state").size().to_string())

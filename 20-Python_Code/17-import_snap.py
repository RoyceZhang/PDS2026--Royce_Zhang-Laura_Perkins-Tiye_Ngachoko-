from pathlib import Path
import pandas as pd

STATES = {"12": "FL", "37": "NC", "45": "SC", "04": "AZ", "53": "WA"}

snap = pd.read_csv("00-Source_Data/saipe_snap.csv", dtype=str, encoding="utf-8-sig")
snap.columns = ["state", "county", "name"] + (
    snap.columns[3:].str.extract(r"(\d{4})")[0].tolist()  # "July 2006" -> "2006"
)

year_cols = [str(y) for y in range(2006, 2016)]

snap["state"] = snap["state"].str.strip().str.zfill(2)
snap["county"] = snap["county"].str.strip().str.zfill(3)
snap = snap[
    snap["state"].isin(STATES) & (snap["county"] != "000")
]  # drop state-total rows

snap = snap.melt(
    id_vars=["state", "county", "name"],
    value_vars=year_cols,
    var_name="year",
    value_name="snap_recipients",
)
snap["year"] = snap["year"].astype(int)
snap["snap_recipients"] = pd.to_numeric(
    snap["snap_recipients"].str.replace(",", ""), errors="coerce"
)
snap["county_fips"] = snap["state"] + snap["county"]
snap["state_abbreviation"] = snap["state"].map(STATES)
snap = snap[["county_fips", "state_abbreviation", "name", "year", "snap_recipients"]]

# Dade County was renamed to Miami-Dade County in 1997.
# This county is present in the file because it was named Dade during the time the data covers, but is not relevent for our time range
# This code removes Dade County
snap = snap[snap["county_fips"] != "12025"]

out_dir = Path("10-Clean_Data")
out_dir.mkdir(parents=True, exist_ok=True)
snap.to_parquet(out_dir / "saipe_snap_2006_2015.parquet", index=False)

assert sorted(snap["year"].unique()) == list(range(2006, 2016))
assert not snap.duplicated(["county_fips", "year"]).any()
print(snap.isna().sum())

missing = snap[snap["snap_recipients"].isna()]
print(missing)
print(missing["county_fips"].value_counts())

print(snap.groupby("state_abbreviation")["county_fips"].nunique())
assert len(snap) == snap["county_fips"].nunique() * 10  # every county has all 10 years

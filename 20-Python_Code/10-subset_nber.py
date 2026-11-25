import pandas as pd

nber = pd.read_csv(
    "00-Source_Data/nber.csv",
    dtype={"fipsstatecode": str, "fipscountycode": str, "county_fips": str},
)

# print col names to find desired columns
# for col in nber:
#    print(col)

# lists of various desired values
desired_cols_nber = [
    "statename",
    "state_abbreviation",
    "fipsstatecode",
    "countycountyequivalent",
    "fipscountycode",
    "county_fips",
]

desired_statename = ["Florida", "Washington"]

desired_state_abbreviation = ["FL", "WA"]

# reduced dataset
nber_clean = nber.loc[
    nber["state_abbreviation"].isin(desired_state_abbreviation)
    | nber["statename"].isin(desired_statename),
    desired_cols_nber,
].copy()

# count number of empty cells in nber_clean
(nber_clean.isna() | nber_clean.astype(str).apply(lambda s: s.str.strip() == "")).sum()


## some values are NaN, so this fills in the missing values
fips5 = (
    pd.to_numeric(nber_clean["county_fips"], errors="coerce")
    .astype("Int64")
    .astype(str)
    .str.zfill(5)
)

state_names = {"FL": "Florida", "WA": "Washington"}

nber_clean["fipsstatecode"] = nber_clean["fipsstatecode"].fillna(fips5.str[:2])
nber_clean["fipscountycode"] = nber_clean["fipscountycode"].fillna(fips5.str[2:])
nber_clean["statename"] = nber_clean["statename"].fillna(
    nber_clean["state_abbreviation"].map(state_names)
)

## assert adding values worked
cols = ["statename", "fipsstatecode", "fipscountycode"]
assert nber_clean[cols].notna().all().all(), nber_clean[cols].isna().sum()

assert nber_clean["fipsstatecode"].str.len().eq(2).all()
assert nber_clean["fipscountycode"].str.len().eq(3).all()

# the parts should match county_fips on every row
assert (nber_clean["fipsstatecode"] + nber_clean["fipscountycode"] == fips5).all()

# assert columns are matching
assert list(nber_clean.columns) == desired_cols_nber

# assert FIPS leading zeros are kept
assert nber_clean["fipsstatecode"].str.len().eq(2).all()

# asserts every row for the desired states is kept
assert (
    len(nber_clean) == nber["state_abbreviation"].isin(desired_state_abbreviation).sum()
)

assert nber_clean[["statename", "state_abbreviation"]].notna().all().all()
assert set(nber_clean["state_abbreviation"]) == {"FL", "WA"}

# no empty cells
missing = nber_clean.isna().sum()
assert missing.sum() == 0, f"Missing values:\n{missing[missing > 0]}"

# export to parquet in clean data folder
nber_clean.to_parquet("10-Clean_Data/nber.parquet")

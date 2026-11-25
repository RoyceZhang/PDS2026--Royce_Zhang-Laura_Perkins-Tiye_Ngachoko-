import pandas as pd

pd.set_option("display.max_columns", None)
pd.set_option("display.width", None)  # use the full terminal width

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
    nber["state_abbreviation"].isin(desired_state_abbreviation), desired_cols_nber
]

## find why assert nber_clean["fipsstatecode"].str.len().eq(2).all() fails
# bad_fsc = nber_clean[~nber_clean["fipsstatecode"].str.len().eq(2)]

# print(len(bad_fsc), "bad rows")
# print(bad_fsc["fipsstatecode"].unique())
# print(bad_fsc[["statename", "fipsstatecode"]].head())

## fails because of NaN values. Looking at whole rows
# bad = nber_clean[nber_clean["fipsstatecode"].isna()]

# print(bad)
# print(bad.isna().sum())  # what else is missing in these rows

# seems like there are places that have a county_fips code, but they may not exist anymore

# counties_to_add_FL = {"fipsstatecode": [], "fipscountycode": [], "county_fips": [12007]}

## find rows with the same county names
# dupes = nber_clean[nber_clean["countycountyequivalent"].duplicated(keep=False)]

# print(dupes.sort_values("countycountyequivalent"))

## fill in NaN values
### county_fips as 5-digit text, e.g. "12007"
### (also handles the case where it was read in as a number)
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

## assert it worked
cols = ["statename", "fipsstatecode", "fipscountycode"]
assert nber_clean[cols].notna().all().all(), nber_clean[cols].isna().sum()

assert nber_clean["fipsstatecode"].str.len().eq(2).all()
assert nber_clean["fipscountycode"].str.len().eq(3).all()

# the parts should match county_fips on every row
assert (nber_clean["fipsstatecode"] + nber_clean["fipscountycode"] == fips5).all()

print(
    nber_clean.loc[[325, 2961], cols + ["county_fips"]]
)  # spot-check two of the fixed rows

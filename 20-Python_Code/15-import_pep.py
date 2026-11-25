# from Claude

from pathlib import Path
import pandas as pd

STATES = {"12": "FL", "37": "NC", "45": "SC", "04": "AZ", "53": "WA"}

BASE = "https://www2.census.gov/programs-surveys/popest/datasets"
FILES = [
    (
        BASE + "/2000-2010/intercensal/county/co-est00int-alldata-{fips}.csv",
        {8: 2006, 9: 2007, 10: 2008, 11: 2009},
        99,
    ),  # all ages = 99
    (
        BASE + "/2010-2019/counties/asrh/cc-est2019-alldata-{fips}.csv",
        {3: 2010, 4: 2011, 5: 2012, 6: 2013, 7: 2014, 8: 2015},
        0,
    ),  # all ages = 0
]

RACES = {
    "white": "WA",
    "black": "BA",
    "native": "IA",
    "asian": "AA",
    "pacific": "NA",
    "two_plus": "TOM",
    "hispanic": "H",
}

frames = []
for url_tpl, year_map, total_age in FILES:
    for fips, abbr in STATES.items():
        df = pd.read_csv(
            url_tpl.format(fips=fips),
            encoding="latin-1",
            dtype={"STATE": str, "COUNTY": str},
        )
        df = df[(df["AGEGRP"] == total_age) & df["YEAR"].isin(year_map)]
        # all ages, July estimates
        out = pd.DataFrame(
            {
                "county_fips": df["STATE"].str.zfill(2) + df["COUNTY"].str.zfill(3),
                "state_abbreviation": abbr,
                "county": df["CTYNAME"],
                "year": df["YEAR"].map(year_map),
                "total_pop": df["TOT_POP"],
            }
        )
        for name, code in RACES.items():
            out[f"{name}_pop"] = df[f"{code}_MALE"] + df[f"{code}_FEMALE"]
        frames.append(out)
        print(f"{abbr} {url_tpl.split('/')[-1][:13]}: {len(out)} rows")

pep = pd.concat(frames, ignore_index=True)

out_dir = Path("10-Clean_Data")
out_dir.mkdir(parents=True, exist_ok=True)
pep.to_parquet(out_dir / "pep_county_race_2006_2015.parquet", index=False)

assert sorted(pep["year"].unique()) == list(range(2006, 2016))
assert not pep.duplicated(["county_fips", "year"]).any()

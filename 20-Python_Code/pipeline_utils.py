"""Shared identifiers, validation, and Parquet provenance."""

import json
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]


STATES = {"AZ": "04", "FL": "12", "NC": "37", "SC": "45", "WA": "53"}


RACES = ["white", "black", "native", "asian", "pacific", "two_plus", "hispanic"]


COUNTY_ALIASES = {("FL", "SAINTJOHNS"): "STJOHNS", ("FL", "SAINTLUCIE"): "STLUCIE"}


def apply_county_aliases(frame):
    frame = frame.copy()
    for (state, original), canonical in COUNTY_ALIASES.items():
        mask = frame.state.eq(state) & frame.county_key.eq(original)
        frame.loc[mask, "county_key"] = canonical
    return frame


def read_table(path):
    path = Path(path)
    if path.suffix.lower() in {".zip", ".gz"}:
        raise ValueError("Use an explicitly configured source cleaner for compressed inputs.")
    with path.open("rb") as stream:
        if stream.read(80).startswith(b"version https://git-lfs.github.com/spec/"):
            raise ValueError(f"{path.name} is a Git LFS pointer; obtain the actual data first.")
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path, dtype="string", sep="\t" if path.suffix == ".tsv" else ",")


def normalize_county(series):
    county = series.astype("string").str.upper().str.strip()
    county = county.str.replace(r"\s+(COUNTY|PARISH|BOROUGH|CENSUS AREA)$", "", regex=True)
    county = county.str.replace(r"[^A-Z0-9]", "", regex=True)
    return county.replace({"DADE": "MIAMIDADE", "DE SOTO": "DESOTO", "": pd.NA})


def fips_string(series):
    values = series.astype("string").str.strip().str.replace(r"\.0$", "", regex=True)
    if not values.str.fullmatch(r"\d{1,5}", na=False).all():
        raise ValueError("Missing or invalid county FIPS identifier.")
    values = values.str.zfill(5)
    if values.str.endswith("000").any():
        raise ValueError("State totals cannot be included as county observations.")
    return values


def check_keys(frame, keys=("fips", "year")):
    if frame.empty:
        raise ValueError("Dataset is empty.")
    if frame[list(keys)].isna().any().any():
        raise ValueError(f"Missing keys: {keys}")
    if frame.duplicated(list(keys)).any():
        examples = frame.loc[frame.duplicated(list(keys), keep=False), list(keys)].head()
        raise ValueError(f"Duplicate keys {keys}:\n{examples}")
    if not frame.columns.str.fullmatch(r"[a-z][a-z0-9_]*").all():
        raise ValueError("Column names must be lowercase snake_case.")
    if not frame.fips.astype("string").str.fullmatch(r"\d{5}", na=False).all():
        raise ValueError("FIPS must contain five digits.")
    if not frame.fips.map(lambda x: isinstance(x, str)).all():
        raise ValueError("FIPS must be stored as text.")
    if "state" in frame:
        expected = frame.state.map(STATES)
        if expected.isna().any() or not frame.fips.str[:2].eq(expected).all():
            raise ValueError("State abbreviation and FIPS disagree.")


def read_metadata(path):
    payload = (pq.read_metadata(path).metadata or {}).get(b"pds_pipeline")
    return json.loads(payload) if payload else {}


def write_parquet(frame, path, metadata=None):
    """Store provenance inside Parquet instead of creating audit sidecar files."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(frame, preserve_index=False)
    if metadata is not None:
        attributes = dict(table.schema.metadata or {})
        attributes[b"pds_pipeline"] = json.dumps(metadata, allow_nan=False).encode()
        table = table.replace_schema_metadata(attributes)
    temporary = path.with_name(path.name + ".tmp")
    pq.write_table(table, temporary)
    temporary.replace(path)

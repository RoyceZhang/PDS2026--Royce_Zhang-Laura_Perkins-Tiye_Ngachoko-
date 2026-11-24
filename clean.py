from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Iterable

import pandas as pd


RAW_COLUMNS = [
	"BUYER_STATE",
	"BUYER_COUNTY",
	"TRANSACTION_DATE",
	"DRUG_NAME",
	"CALC_BASE_WT_IN_GM",
	"DOSAGE_UNIT",
	"MME",
]


# Common opioid names/keywords in ARCOS-style naming.
DEFAULT_OPIOID_KEYWORDS = [
	"OPIUM",
	"CODEINE",
	"MORPHINE",
	"HYDROCODONE",
	"OXYCODONE",
	"HYDROMORPHONE",
	"OXYMORPHONE",
	"FENTANYL",
	"METHADONE",
	"BUPRENORPHINE",
	"TAPENTADOL",
	"TRAMADOL",
	"MEPERIDINE",
	"LEVORPHANOL",
	"DIHYDROCODEINE",
]


US_STATES_AND_DC = {
	"AL",
	"AK",
	"AZ",
	"AR",
	"CA",
	"CO",
	"CT",
	"DE",
	"FL",
	"GA",
	"HI",
	"ID",
	"IL",
	"IN",
	"IA",
	"KS",
	"KY",
	"LA",
	"ME",
	"MD",
	"MA",
	"MI",
	"MN",
	"MS",
	"MO",
	"MT",
	"NE",
	"NV",
	"NH",
	"NJ",
	"NM",
	"NY",
	"NC",
	"ND",
	"OH",
	"OK",
	"OR",
	"PA",
	"RI",
	"SC",
	"SD",
	"TN",
	"TX",
	"UT",
	"VT",
	"VA",
	"WA",
	"WV",
	"WI",
	"WY",
	"DC",
}


COUNTY_SUFFIX_PATTERN = re.compile(
	r"\s+(COUNTY|PARISH|BOROUGH|CENSUS AREA|MUNICIPIO|CITY AND BOROUGH)$"
)


def normalize_county(series: pd.Series) -> pd.Series:
	county = series.astype("string").str.upper().str.strip()
	county = county.str.replace(r"\s+", " ", regex=True)
	county = county.str.replace(COUNTY_SUFFIX_PATTERN, "", regex=True)
	return county


def build_opioid_regex(keywords: Iterable[str]) -> str:
	escaped = [re.escape(k.strip().upper()) for k in keywords if k and k.strip()]
	if not escaped:
		raise ValueError("No opioid keywords provided.")
	return "|".join(escaped)


def clean_arcos(
	input_zip: Path,
	output_csv: Path,
	output_parquet: Path | None,
	chunksize: int,
	opioid_keywords: list[str],
	keep_all_states: bool,
) -> None:
	opioid_regex = build_opioid_regex(opioid_keywords)

	agg = pd.DataFrame(
		columns=[
			"state",
			"county",
			"year",
			"shipment_records",
			"opioid_calc_base_wt_gm",
			"opioid_dosage_unit",
			"opioid_mme",
		]
	)

	dtypes = {
		"BUYER_STATE": "string",
		"BUYER_COUNTY": "string",
		"TRANSACTION_DATE": "string",
		"DRUG_NAME": "string",
		"CALC_BASE_WT_IN_GM": "string",
		"DOSAGE_UNIT": "string",
		"MME": "string",
	}

	reader = pd.read_csv(
		input_zip,
		sep="\t",
		compression="zip",
		usecols=RAW_COLUMNS,
		dtype=dtypes,
		chunksize=chunksize,
		low_memory=True,
	)

	for i, chunk in enumerate(reader, start=1):
		chunk.columns = [c.strip() for c in chunk.columns]

		chunk["BUYER_STATE"] = chunk["BUYER_STATE"].astype("string").str.upper().str.strip()
		if not keep_all_states:
			chunk = chunk[chunk["BUYER_STATE"].isin(US_STATES_AND_DC)]

		chunk["BUYER_COUNTY"] = normalize_county(chunk["BUYER_COUNTY"])

		drug_name = chunk["DRUG_NAME"].astype("string").str.upper().str.strip()
		chunk = chunk[drug_name.str.contains(opioid_regex, regex=True, na=False)]

		tx_date = pd.to_datetime(chunk["TRANSACTION_DATE"], errors="coerce")
		chunk["year"] = tx_date.dt.year

		chunk["CALC_BASE_WT_IN_GM"] = pd.to_numeric(chunk["CALC_BASE_WT_IN_GM"], errors="coerce")
		chunk["DOSAGE_UNIT"] = pd.to_numeric(chunk["DOSAGE_UNIT"], errors="coerce")
		chunk["MME"] = pd.to_numeric(chunk["MME"], errors="coerce")

		chunk = chunk.dropna(subset=["BUYER_STATE", "BUYER_COUNTY", "year"])

		g = (
			chunk.groupby(["BUYER_STATE", "BUYER_COUNTY", "year"], dropna=False)
			.agg(
				shipment_records=("DRUG_NAME", "size"),
				opioid_calc_base_wt_gm=("CALC_BASE_WT_IN_GM", "sum"),
				opioid_dosage_unit=("DOSAGE_UNIT", "sum"),
				opioid_mme=("MME", "sum"),
			)
			.reset_index()
			.rename(columns={"BUYER_STATE": "state", "BUYER_COUNTY": "county"})
		)

		if agg.empty:
			agg = g
		else:
			agg = (
				pd.concat([agg, g], ignore_index=True)
				.groupby(["state", "county", "year"], as_index=False)
				.agg(
					shipment_records=("shipment_records", "sum"),
					opioid_calc_base_wt_gm=("opioid_calc_base_wt_gm", "sum"),
					opioid_dosage_unit=("opioid_dosage_unit", "sum"),
					opioid_mme=("opioid_mme", "sum"),
				)
			)

		if i % 10 == 0:
			print(f"Processed {i} chunks; current county-year rows: {len(agg):,}")

	agg["year"] = agg["year"].astype("Int64")
	agg = agg.sort_values(["state", "county", "year"]).reset_index(drop=True)

	output_csv.parent.mkdir(parents=True, exist_ok=True)
	agg.to_csv(output_csv, index=False)
	print(f"Saved cleaned county-year panel: {output_csv} ({len(agg):,} rows)")

	if output_parquet is not None:
		output_parquet.parent.mkdir(parents=True, exist_ok=True)
		agg.to_parquet(output_parquet, index=False)
		print(f"Saved parquet copy: {output_parquet}")


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description=(
			"Clean ARCOS all-transaction data and output county-year opioid shipment metrics."
		)
	)
	parser.add_argument(
		"--input-zip",
		type=Path,
		default=Path("arcos_all.zip"),
		help="Path to arcos_all.zip",
	)
	parser.add_argument(
		"--output-csv",
		type=Path,
		default=Path("data/clean/arcos_county_year_opioid.csv"),
		help="Output CSV path",
	)
	parser.add_argument(
		"--output-parquet",
		type=Path,
		default=Path("data/clean/arcos_county_year_opioid.parquet"),
		help="Optional parquet output path",
	)
	parser.add_argument(
		"--no-parquet",
		action="store_true",
		help="Disable parquet output",
	)
	parser.add_argument(
		"--chunksize",
		type=int,
		default=1_000_000,
		help="Rows per chunk when streaming the raw file",
	)
	parser.add_argument(
		"--opioid-keywords",
		nargs="+",
		default=DEFAULT_OPIOID_KEYWORDS,
		help="Keywords used to identify opioid transactions in DRUG_NAME",
	)
	parser.add_argument(
		"--keep-all-states",
		action="store_true",
		help="Keep territories/non-state records instead of filtering to 50 states + DC",
	)
	return parser.parse_args()


def main() -> None:
	args = parse_args()
	output_parquet = None if args.no_parquet else args.output_parquet

	clean_arcos(
		input_zip=args.input_zip,
		output_csv=args.output_csv,
		output_parquet=output_parquet,
		chunksize=args.chunksize,
		opioid_keywords=args.opioid_keywords,
		keep_all_states=args.keep_all_states,
	)


if __name__ == "__main__":
	main()

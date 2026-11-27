# County-year data dictionary

The integration panel preserves 2,670 county-years. Mortality diagnostics expand
the schema to 49 columns. The strict panel uses the exact all-intents mortality
definition; the explicitly labeled D1 alternative uses unintentional drug
overdoses. Outcome availability differs between these definitions.
All files use lowercase column names and five-digit text FIPS identifiers.

| Column | Type / units | Source and meaning | Missing-value interpretation |
|---|---|---|---|
| `fips` | text, 5 digits | Full county FIPS, including state digits | Not allowed |
| `state` | text | AZ, FL, NC, SC, WA | Not allowed |
| `county` | text | PEP county name | Not expected |
| `year` | integer, calendar year | 2006–2015 | Not allowed |
| `population` | numeric, persons | PEP July population estimate | Not allowed; must be positive |
| `white_pop` | numeric, persons | PEP White alone | Not expected |
| `black_pop` | numeric, persons | PEP Black alone | Not expected |
| `native_pop` | numeric, persons | PEP American Indian / Alaska Native alone | Not expected |
| `asian_pop` | numeric, persons | PEP Asian alone | Not expected |
| `pacific_pop` | numeric, persons | PEP Native Hawaiian / Pacific Islander alone | Not expected |
| `two_plus_pop` | numeric, persons | PEP two or more races | Not expected |
| `hispanic_pop` | numeric, persons | PEP Hispanic ethnicity, overlapping race categories | Not expected |
| `total_mme` | numeric, morphine mg equivalent | Sum of the supplied ARCOS MME transaction totals for eligible recipients | Unmatched county-year or no observed finite measurement |
| `shipment_records` | numeric, record count | Number of selected ARCOS transactions | Unmatched county-year; absence is not zero shipments |
| `dosage_units` | numeric, dosage units | Sum of ARCOS DOSAGE_UNIT; not necessarily pills alone | No observed finite measurement |
| `base_weight_gm` | numeric, grams | Sum of ARCOS active ingredient weight | No observed finite measurement |
| `total_mme_observed_records` | numeric, record count | Transactions with observed finite MME | Zero means all MME measurements are missing in an observed group |
| `dosage_units_observed_records` | numeric, record count | Transactions with observed finite dosage units | As above, for dosage units |
| `base_weight_gm_observed_records` | numeric, record count | Transactions with observed finite active grams | As above, for active grams |
| `overdose_deaths` | numeric, death count | Strict all-intents total in the main panel; D1 only in the labeled alternative | Unknown when components are omitted, or D1 not reported in the alternative; never imputed |
| `labor_force` | numeric, persons | BLS LAUS annual average | Source missingness or unmatched county-year |
| `employed` | numeric, persons | BLS LAUS annual average employed | As above |
| `unemployed` | numeric, persons | BLS LAUS annual average unemployed | As above |
| `unemployment_rate` | numeric, percent | LAUS; 5.5 means 5.5%, not 0.055 | As above |
| `snap_recipients` | numeric, persons | Census SAIPE SNAP model input, July recipients | No missing values in current 2,670 rows; not a missing-value imputation |
| `arcos_merge_status` | text | `source_unavailable`, `not_matched`, or `matched` | Describes availability/join only |
| `mortality_merge_status` | text | Same join categories for mortality | Does not label absent records as suppressed |
| `laus_merge_status` | text | Same join categories for LAUS | Real local data verified against the LFS object SHA-256 |
| `snap_merge_status` | text | Same join categories for SNAP | All current rows matched |
| `mme_per_capita` | numeric, morphine mg equivalent/person/year | `total_mme / population` | Missing numerator stays missing |
| `overdose_death_rate` | numeric, deaths/100,000 persons/year | `overdose_deaths / population * 100000` | Missing numerator stays missing; not age-adjusted |
| `snap_rate` | numeric, fraction | `snap_recipients / population` | Missing numerator stays missing |
| `white_share` | numeric, fraction | `white_pop / population` | Not expected |
| `black_share` | numeric, fraction | `black_pop / population` | Not expected |
| `native_share` | numeric, fraction | `native_pop / population` | Not expected |
| `asian_share` | numeric, fraction | `asian_pop / population` | Not expected |
| `pacific_share` | numeric, fraction | `pacific_pop / population` | Not expected |
| `two_plus_share` | numeric, fraction | `two_plus_pop / population` | Not expected |
| `hispanic_share` | numeric, fraction | `hispanic_pop / population` | Overlaps race shares; do not sum with them |

Additional mortality fields are:

| Column | Definition / units |
|---|---|
| `mortality_status` | Observed category completeness; does not guess whether absent cells are zero or suppressed |
| `mortality_definition` | Explicit strict-all-intents or D1-only endpoint definition |
| `unintentional_overdose_deaths` | D1 reported count |
| `suicide_overdose_deaths` | D2 reported count |
| `homicide_overdose_deaths` | D3 reported count; absent values stay NaN |
| `undetermined_overdose_deaths` | D4 reported count |
| `overdose_categories_observed` | Number of observed D1–D4 components, integer 0–4 |
| `overdose_deaths_reported_lower_bound` | Sum of observed D1–D4; not the exact total |
| `unintentional_overdose_death_rate` | D1 / population × 100,000 |
| `reported_overdose_death_rate_lower_bound` | Reported-component lower bound / population × 100,000 |

See README for cause definitions and endpoint limitations. D1 is unintentional (X40–X44), D2 suicide (X60–X64), D3 homicide (X85), and D4 undetermined intent (Y10–Y14). D9 and alcohol/non-drug categories are excluded.

`arcos_county_year_drug.parquet` additionally contains `drug_name` (text,
uppercase normalized raw name). Its unique key is `fips, year, drug_name`.
`arcos_county_year.parquet` and the merged panel use `fips, year`.
Canonical ARCOS outputs select the patient-facing recipient types listed in
`clean_arcos.py`. Nonclinical/supply-chain buyers and mail-order/central-fill
pharmacies are excluded from the local-recipient definition. A partially observed
numeric sum uses observed records only; compare its observed-record count with
`shipment_records` before interpreting it as a complete total.

The crosswalk contains `fips`, `state`, `county`, and `county_key` (normalized
county name), covering all five states. Exact joint state/county matching is
used; verified Florida Saint/St and Miami-Dade aliases are supported.

Audit information is embedded in each generated Parquet file under the
`pds_pipeline` schema metadata key. It is not an additional analytic column.
ARCOS metadata identifies full-input versus sample scope, recipient selection,
source record counts, matching rates, and the remaining unmatched aggregates.
Merged metadata records the endpoint and join validation. The common helper
`read_metadata()` reads it; no external audit JSON file is required.

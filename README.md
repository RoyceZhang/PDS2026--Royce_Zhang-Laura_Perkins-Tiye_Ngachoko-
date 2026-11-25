"This product uses the Census Bureau Data API but is not endorsed or certified by the Census Bureau."

^ keep this displayed near the top of the README



# Project Overview

Measure the effect of a series of policy changes designed to limit opioid abuse on:
- opioid drug prescriptions
- mortality from drug overdoses

Unit of observation = counties per year

## Project goals

What is the effect of opioid drug prescription regulations on:

- the volume of opioids prescribed
- drug overdose deaths

## Assigned tasks

pre-post analysis and diff-in-diff analysis for both FL and WA

We want 8 graphs, one for each analysis in each state for opioid shipments and overdose deaths.

# Report plots

*Report plots should include standard error bands!*

- Difference-in-Difference plots

# Data

## Requirements

- opioid prescriptions
    - from a provided dataset on all prescription opioid drug shipments in the US from 2006 to 2019
    - Royce cleaned this data
- drug overdose mortality
    - from a provided dataset on US Vital Statistics from 2003 to 2015
    - **NOTICE** if a category has less than 10, the data does not appear (this includes 0 counts) so counties with low death counts will not appear for that year and counties with low overdose deaths  will not include that statistic

## Control variables (2006–2015, all five states)

| Data | Source | Clean file |
|---|---|---|
| County population by race | Census Population Estimates Program (PEP): 2000–2010 intercensal + Vintage 2019 county characteristics files | `pep_county_race_2006_2015.parquet` |
| SNAP recipients (July of each year) | Census SAIPE model input data (`cntysnap`) | `saipe_snap_2006_2015.parquet` |

- PEP was used instead of the ACS because the ACS 1-year skips counties under 65,000 people and the ACS 5-year starts in 2009 and averages five years together.
- PEP race columns are "race alone"; `hispanic_pop` overlaps them and should not be added to the race totals.
- In the PEP 2000–2010 file the all-ages total is `AGEGRP == 99`; in the 2010–2019 file it is `AGEGRP == 0`.
- Old Dade County, FL (`12025`) is dropped from the SNAP data; it is Miami-Dade (`12086`) for all study years.
- All files use a 5-digit text `county_fips` (leading zeros kept) for merging.

## Pipeline

| Script | Output |
|---|---|
| `20-Python_Code/10-subset_nber.py` | `10-Clean_Data/nber.parquet` — FL/WA county FIPS crosswalk; fills missing state/county codes from `county_fips` |
| `20-Python_Code/15-import_pep.py` | `10-Clean_Data/pep_county_race_2006_2015.parquet` (downloads from census.gov) |
| `20-Python_Code/17-import_snap.py` | `10-Clean_Data/saipe_snap_2006_2015.parquet` (reads `00-Source_Data/saipe_snap.csv`) |
| `20-Python_Code/20-clean_data_plots.py` | Population, SNAP count, and SNAP share plots in `30-Exported_Files/10-Plots/` |

Run scripts from the project root folder so the relative paths resolve.

# States

**Required States**

Florida and Washington

**States for diff-in-diff comparison**

*Candidates:*

- Florida (policy 2010): North Carolina, South Carolina, Arizona (Virginia as a backup)
- Washington (policy 2012): Arizona, California; Michigan, New Jersey, South Carolina if pre-trends match

*Choices and reasoning*

- **North Carolina** is the comparison state used in published evaluations of Florida's pill mill laws: similar pre-2010 overdose trends and no pain clinic law, PDMP, or major opioid policy during the study period.
- **Arizona, California, Michigan, New Jersey, South Carolina** were the comparison states in a published diff-in-diff of Washington's opioid prescribing guideline.
- **Excluded:**
    - states with their own pill mill / pain clinic laws in the window (TX, LA, OH, KY, TN, WV, MS, AL)
    - Georgia and Alabama for FL, because pill mills moved there after Florida's crackdown (spillover)
    - Oregon for WA, because its PDMP went live in Sept 2011; Idaho for WA because of border spillover
    - Colorado and Utah for WA, because they adopted similar prescribing guidelines
- Final choice depends on parallel pre-policy trends in our own shipment and mortality data.

**Do not work with Alaska.** This is due to state restructuring of counties during 

# Things to do:

- Develop a strategy for dealing with missing values in data
    - do **NOT** fill all 10s, fill all 0s, fill with average mortality counts
- Discuss what years we will look at
    - FL legislation: 2010 - main policy, 2011 - statewide raids & mandated dispensor reporting, 2012 - expanded wholesale distribution regulations
    - WA legislation: 2012 - main policy (rules effective Jan 2, 2012); note WA already had a 2007 prescribing guideline, so the pre-period is not policy-free
- Check pre-policy trends for each candidate comparison state before finalizing
- Merge PEP population with mortality and shipment data to compute per-capita rates

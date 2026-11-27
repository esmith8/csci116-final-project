"""Gemini Hydrogen 4.0 was used to create the filtering logic used in this file.
The purpose of this script is to take the offenses known dataset from Jacob Kaplan's
concatenated files and do the following for data from the years 1996 to 2024:
1. Consolidate robbery, burglary, assault, and theft totals to an MSA level for each of the metropolitan areas
    outlined in the ../data_info/metropolitan_areas.csv file into a single .xlsx file.
2. Create a mapping of ori9 to metropolitan area, which will allow for the api calls to be made in crime_etl_api_2025.py
    to be used to get agency-level crime statistics for  relevant metropolitan areas.
"""
import polars as pl
from pathlib import Path

import time

import pandas as pd
from collections import defaultdict

SUMMARY_FILE_NAME = "../data/known_offenses/known_offenses_summary_1996_2024.xlsx"

start = time.time()

# 3. Build METROPOLITAN_AREAS_TO_KEEP from the updated CSV
metro_areas = defaultdict(list)
metropolitan_areas_df = pd.read_csv("../data_info/metropolitan_areas.csv")
for _, row in metropolitan_areas_df.iterrows():
    state_key = row["state"]
    city_val = row["city"].lower()
    if city_val not in metro_areas[state_key]:
        metro_areas[state_key].append(city_val)

METROPOLITAN_AREAS_TO_KEEP = dict(metro_areas)

folder_path = r"../data/offenses_known_data_1996_2024"

# Persistent dictionary mapping ori9 -> (city, state) across all files
ori9_to_metro: dict[str, tuple[str, str]] = defaultdict(set)

# Used Claude Sonnet 5.5 Extra to fix the clean_offense_data function to properly pull all of the 
def clean_offense_data(file_path, ori9_to_metro):
    df = pl.read_csv(file_path, null_values=["NA"], infer_schema_length=None)

    city_state_match = pl.any_horizontal([
        (pl.col("address_state").str.to_lowercase().str.strip_chars() == state.lower())
        & (
            pl.col("address_city")
            .str.to_lowercase()
            .str.strip_chars()
            .is_in([city.lower() for city in cities])
        )
        for state, cities in METROPOLITAN_AREAS_TO_KEEP.items()
    ])
    subset_df = df.filter(city_state_match)

    # One row per (msa, city, state) -- an MSA can legitimately appear under several cities
    mapping = (
        subset_df.select(["population_1_msa", "address_state", "address_city"])
        .drop_nulls("population_1_msa")
        .rename({"address_state": "metro_state", "address_city": "metro_city"})
        .unique()
    )

    joined = df.join(mapping, on="population_1_msa", how="inner")  # many-to-many

    for row in (
        joined.select(["ori9", "population_1_msa", "metro_city", "metro_state"])
        .drop_nulls()
        .unique()
        .iter_rows(named=True)
    ):
        ori9 = str(row["ori9"]).strip()
        msa = int(row["population_1_msa"])
        city = str(row["metro_city"]).strip()
        state = str(row["metro_state"]).strip()
        ori9_to_metro[ori9].add((msa, city, state))

    offense_cols = [
        "actual_robbery_total",
        "actual_assault_total",
        "actual_assault_simple",
        "actual_burglary_total",
        "actual_theft_total",
        "actual_motor_vehicle_theft_total"
    ]
    return (
        joined.group_by(["metro_state", "metro_city", "population_1_msa", "year", "month"])
        .agg(pl.col(offense_cols).sum())
        .rename({"metro_state": "address_state", "metro_city": "address_city"})
    )

# There are a lot of .csv files to clean, the easiest way to read each of them is to iterate through the entire folder.
offenses_df_list = []
for file_path in Path(folder_path).iterdir():
    if file_path.is_file():
        offenses_df_list.append(clean_offense_data(file_path, ori9_to_metro))

# Concatenating all offense dataframes into a single dataframe, then exporting as a condensed Excel file.
# Filtering out all of the rows with MSA codes that should be ignored
full_offenses_df = pl.concat(offenses_df_list, how="diagonal_relaxed")
full_offenses_df.write_excel(SUMMARY_FILE_NAME)

# Reading in recently saved summary file to filter it by the correct MSA codes
# It took me around 2 hours to figure out that the same MSA codes were being shared across different cities and states,
# which is because I didn't really expect Providence, RI and Boston, MA to share MSA codes.
# I had already used Gemini Hydrogen 4.0 to write a test filter using pandas, so I'm keeping it like this.
df = pd.read_excel(SUMMARY_FILE_NAME)

MSA_CODES_TO_IGNORE_BY_CITY_STATE = {
    ("los angeles", "ca"): [549, 619, 740, 777, 783, 786, 864, 983, 990], # All assigned to Los Angeles, CA but not relevant geographically. 478 and 480 are the only two MSAs which represent true LA
    ("new haven", "ct"): [349, 938], # Misassigned to New Haven, CT (588 is correct)
    ("atlanta", "ga"): [51], # Misassigned to Atlanta, GA (50 is correct)
    ("indianapolis", "in"): [39, 100, 101, 102, 162, 163, 165, 186, 241, 257, 289, 312, 414, 416, 417, 483, 533, 561, 828, 883], # Misassigned to Indianapolis, IN (372 is correct)
    ("boston", "ma"): [38, 76, 106, 107, 115, 671, 690, 841, 976], # Misassigned to Boston, MA (105 is correct)
    ("portland", "me"): [74, 450], # Misassigned to Portland, ME (680 is correct)
    ("new york", "ny"): [235, 412, 573, 580, 601, 603, 610, 687], # Misassigned to New York City, NY (607 is correct)
    ("norfolk", "va"): [722], # Misassigned to Norfolk, VA (611 is correct)
    ("charleston", "wv"): [18, 88, 195, 196, 337, 363, 557, 642, 859, 860, 933, 934, 936, 946, 947, 952, 972], # Misassigned to Charleston, WV (141 and 147 are correct)
    ("wilmington", "de"): [228], # 970, 657, and 661 are correct
    ("columbia", "sc"): [40, 59, 142, 151, 277, 278, 335, 353, 564, 566, 830, 866] # 179 is correct
}

# Flatten dictionary into a MultiIndex of (address_city, address_state, population_1_msa)
ignore_triples = pd.MultiIndex.from_tuples(
    [
        (city, state, msa)
        for (city, state), msa_codes in MSA_CODES_TO_IGNORE_BY_CITY_STATE.items()
        for msa in msa_codes
    ],
    names=["address_city", "address_state", "population_1_msa"],
)

row_triples = pd.MultiIndex.from_frame(
    df[["address_city", "address_state", "population_1_msa"]]
)

# Remove all MSA 0 rows globally, plus any exact (city, state, msa) matches
rows_to_remove = df["population_1_msa"].eq(0) | row_triples.isin(ignore_triples)
filtered_df = df[~rows_to_remove]

# Saving the final summary file here, completely cleaned.
filtered_df.to_excel(SUMMARY_FILE_NAME, index = False)

# Apply the exact same MSA == 0 and (city, state, msa) filter to ori9_to_metro
ori9_to_metro = {
    ori9: valid_triples
    for ori9, triples in ori9_to_metro.items()
    if (
        valid_triples := {
            (msa, city, state)
            for (msa, city, state) in triples
            if msa != 0 and (city.lower(), state.lower(), msa) not in ignore_triples
        }
    )
}

# Export the filtered ori9 -> (msa, city, state) mapping
ori9_metro_df = pl.DataFrame(
    [
        {"ori9": ori9, "msa": msa, "city": city, "state": state}
        for ori9, triples in sorted(ori9_to_metro.items())
        for (msa, city, state) in sorted(triples)
    ],
    schema={"ori9": pl.String, "msa": pl.Int64, "city": pl.String, "state": pl.String},
)
ori9_metro_df.write_csv("../data_info/ori9_metro_mapping.csv")

# The purpose of this section is to print out how many rows were captured for each city.
# It was generated using Gemini Hydrogen 4.0
# Ideally, 300 rows should be captured but 264 were captured for Idaho Falls and St. George since they werent MSAs until 2003.
df = pl.read_excel(SUMMARY_FILE_NAME, engine="openpyxl")

city_counts = (
    df.group_by("address_city")
    .agg(
        pl.len().alias("row_count"),
        pl.col("address_state").unique().sort().alias("states"),
        pl.col("year").n_unique().alias("year_count"),
        pl.col("year")
        .unique()
        .sort()
        .cast(pl.String)
        .implode()
        .list.join(", ")
        .alias("years"),
    )
    .sort("row_count", descending=True)
)

with pl.Config(tbl_rows=-1, tbl_cols=-1, fmt_str_lengths=200):
    print(city_counts)

# The purpose of this function is to save a sheet containing any MSAs which were used for the same
# metropolitan area for the same year. This sheet is used for me to manually inspect which MSA should
# be used for that particular year. Given the updated MSA_CODES_TO_IGNORE list, this sheet should be empty.
def export_duplicate_msa_years(
    input_path: str | Path = SUMMARY_FILE_NAME,
    output_path: str | Path = "duplicate_msa_years_1996_2024.xlsx",
) -> Path:
    df = pd.read_excel(input_path)

    # Drop missing keys and normalize city/state text so case/whitespace differences don't split groups
    df = df.dropna(subset=["population_1_msa", "address_city", "address_state", "year"]).copy()
    df["city"] = df["address_city"].astype(str).str.strip().str.lower()
    df["state"] = df["address_state"].astype(str).str.strip().str.lower()
    df["year"] = df["year"].astype(int)

    # Keep only rows where the same (city, state, year) has more than 1 distinct population_1_msa
    msas_per_city_year = df.groupby(["city", "state", "year"])["population_1_msa"].transform("nunique")
    overlapping_df = df[msas_per_city_year > 1]

    # Aggregate into population_1_msa, city, state, and a sorted comma-separated string of years
    result_df = (
        overlapping_df.groupby(["population_1_msa", "city", "state"], as_index=False)
        .agg(**{
            "years included": ("year", lambda s: ", ".join(str(y) for y in sorted(s.unique())))
        })
        [["population_1_msa", "city", "state", "years included"]]
        .sort_values(["state", "city", "population_1_msa"])
    )

    output_file = Path(output_path)
    result_df.to_excel(output_file, index=False)
    return output_file

export_duplicate_msa_years()

end = time.time()

print(f"Total runtime: {(end - start)/60:.2f} minutes")
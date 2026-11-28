"""The purpose of this file is to convert the frequency of the monthly known offenses summary (2024 and earlier) to quarterly.
Additionally, the new quarterly data (2025 and later) is combined to find the total robbery, burglary, theft, and assault offenses
for each metropolitan statistical area (MSA).

It is assumed that the known_offenses_quarterly_folder only contains subdirectories which contain quarterly offense .xlsx files.
The code does not explicity check for other file formats (and .xlsx files with different contents) to ignore those files and will result in an error.

Additionally, the default file names used from the crime_etl_api_2025.py file should be kept, as the information for the associated quarter
is pulled from the filename itself, as I forgot to include the corresponding quarter as a column in the .xlsx file.
"""

import re
import pandas as pd
from datetime import datetime
from pathlib import Path

# Initializing constants which will be used throughout the script
SUMMARY_CITY_COLUMN = "address_city" # The city column saved for the summary file (2024 and earlier) is different than the newer files.
SUMMARY_STATE_COLUMN = "address_state" # The state column saved for the summary file (2024 and earlier) is different than the newer files.
CITY_COLUMN = "city"
STATE_COLUMN = "state"
OFFENSE_TYPE_COLUMN = "offense_type"
OFFENSE_TOTAL_COLUMN = "offense_total" # Column to be used temporarily as a common indicator for totals, replaced with a more specific total column name later
ROBBERY_COLUMN_NAME = "actual_robbery_total"
BURGLARY_COLUMN_NAME = "actual_burglary_total"
MOTOR_VEHICLE_THEFT_COLUMN_NAME = "actual_motor_vehicle_theft_total"
ASSAULT_COLUMN_NAME = "actual_assault_total"
THEFT_COLUMN_NAME = "actual_theft_total"
YEAR_COLUMN = "year"
MONTH_COLUMN = "month"
ROBBERY_CODE = "120"
BURGLARY_CODE = "220"
MOTOR_VEHILE_THEFT_CODE = "240"
ASSAULT_CODE_LIST = [
    "13A", # Aggravated Assault
    "13B", # Simple Assault
    "13C" # Intimidation
]
THEFT_CODE_LIST = [
    "23A", # Pocket-picking
    "23B", # Purse-snatching
    "23C", # Shoplifting
    "23D", # Theft From Building
    "23E", # Theft From Coin-Operated Machine or Device
    "23F", # Theft From Motor Vehicle
    "23G", # Theft of Motor Vehicle Parts or Accessories
    "23H" # All Other Larceny
]


def parse_known_offenses_quarterly(known_offenses_quarterly_folder: str | Path) -> pd.DataFrame:
    # Guranteeing that known_offenses_quarterly_folder is a Path, which can be iterated upon.
    known_offenses_quarterly_folder = Path(known_offenses_quarterly_folder)

    list_of_robbery_dataframes = []
    list_of_burglary_dataframes = []
    list_of_motor_vehicle_theft_dataframes = []
    list_of_assault_dataframes = []
    list_of_theft_dataframes = []
    # Used Gemini Hydrogen 4.0 to find logic for iterating through subdirectories.
    for offense_folder in known_offenses_quarterly_folder.iterdir():
        # Ensuring that offense_folder is indeed a directory.
        if offense_folder.is_dir():
            print(f"Parsing folder for offense {offense_folder.name}")
            for known_offense_quarterly_path in offense_folder.iterdir():
                # Ensuring that known_offense_quarterly_path is indeed a file.
                if known_offense_quarterly_path.is_file():
                    quarterly_offense_df, offense_type = parse_quarterly_offense_file(known_offense_quarterly_path = known_offense_quarterly_path)

                    if offense_type == ROBBERY_CODE:
                        list_of_robbery_dataframes.append(quarterly_offense_df)
                    elif offense_type == BURGLARY_CODE:
                        list_of_burglary_dataframes.append(quarterly_offense_df)
                    elif offense_type == MOTOR_VEHILE_THEFT_CODE:
                        list_of_motor_vehicle_theft_dataframes.append(quarterly_offense_df)
                    elif offense_type in ASSAULT_CODE_LIST:
                        list_of_assault_dataframes.append(quarterly_offense_df)
                    elif offense_type in THEFT_CODE_LIST:
                        list_of_theft_dataframes.append(quarterly_offense_df)

    # It is now necessary to aggregate all dataframes to create one total for each city and state combination.
    def aggregate_total_offense_df(df_list: list[pd.DataFrame], total_column_name: str) -> pd.DataFrame:
        # It is necessary to first concatenate all of the dataframes into one, after which aggregation will take place.
        concatenated_df = pd.concat(df_list, ignore_index = True)
        total_df = pd.DataFrame(concatenated_df.groupby([CITY_COLUMN, 
                                                         STATE_COLUMN, 
                                                         YEAR_COLUMN, 
                                                         MONTH_COLUMN], as_index=False)[OFFENSE_TOTAL_COLUMN].sum())
        total_df.rename(columns = {OFFENSE_TOTAL_COLUMN: total_column_name}, inplace = True)
        return total_df
    
    total_robbery_df = aggregate_total_offense_df(list_of_robbery_dataframes, ROBBERY_COLUMN_NAME)
    total_burglary_df = aggregate_total_offense_df(list_of_burglary_dataframes, BURGLARY_COLUMN_NAME)
    total_motor_vehicle_theft_df = aggregate_total_offense_df(list_of_motor_vehicle_theft_dataframes, MOTOR_VEHICLE_THEFT_COLUMN_NAME)
    total_assault_df = aggregate_total_offense_df(list_of_assault_dataframes, ASSAULT_COLUMN_NAME)
    total_theft_df = aggregate_total_offense_df(list_of_theft_dataframes, THEFT_COLUMN_NAME)
    total_df_list = [
        total_robbery_df,
        total_burglary_df,
        total_motor_vehicle_theft_df,
        total_assault_df,
        total_theft_df
    ]
    MERGE_KEYS = [CITY_COLUMN,
                  STATE_COLUMN,
                  YEAR_COLUMN,
                  MONTH_COLUMN]

    # Used Gemini Hydrogen 4.0 to make it easier to outer merge all of the dataframes at once (instead of multiple uses of merge)
    total_quarterly_offense_df = (
        pd.concat([df.set_index(MERGE_KEYS) for df in total_df_list], axis = 1)
        .fillna(0)
        .reset_index()
    )

    return total_quarterly_offense_df


def parse_quarterly_offense_file(known_offense_quarterly_path: Path) -> tuple[pd.DataFrame, str]:
    """Returns an aggregated offense total for a given file and the corresponding offense type."""
    # Because I forgot to include the quarter that this data represents in the file itself, the 
    # quarter must be parsed from the file name.
    # Used Gemini Hydrogen 4.0 for re.search logic, as regex is the bane of my existence.
    # offense[^_]*_ — matches offense plus any offense code (like 13A) up to the underscore, ignoring everything before offense.
    # (\d{2}-\d{4}) — captures each MM-YYYY date into separate groups.
    # _to_ — matches the separator between the two dates.
    quarterly_offense_filename = known_offense_quarterly_path.name
    match = re.search(r"offense[^_]*_(\d{2}-\d{4})_to_(\d{2}-\d{4})", quarterly_offense_filename)
    if match:
        start_str, end_str = match.groups()
        # Only the date of the first day of the month/year is needed as all quarters are matched based on the 
        # first date of that quarter's month
        quarter_start_date = datetime.strptime(start_str, "%m-%Y")
        month, year = start_str.split("-") # Format is "mm-YYYY"
        month = int(month)
        year = int(year)

    print(f"Parsing File: {known_offense_quarterly_path}")
    # There should only be one sheet in the known offense file, so the default pd.read_excel parameters should be sufficient.
    # Used Gemini Hydrogen 4.0 for file extension logic, which will allow for this function to handle both .csv and .xlsx files appropriately.
    file_ext = Path(known_offense_quarterly_path).suffix.lower()
    if file_ext == ".csv":
        offense_data = pd.read_csv(known_offense_quarterly_path)
    elif file_ext == ".xlsx":
        offense_data = pd.read_excel(known_offense_quarterly_path, engine="openpyxl")
    else:
        raise ValueError(f"Unsupported file format: {known_offense_quarterly_path}")

    # Used Gemini Hydrogen 4.0 to find the offense column name, as it changes based on the offense (such as offense13A or offense23C)
    matches = [col for col in offense_data.columns if col.startswith("offense")]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly 1 offense column, found: {matches}")

    offense_col = matches[0]
    offense_type = offense_col.replace("offense", "").strip() # Format for offense code is "offenseXXX"

    # Used Gemini Hydrogen 4.0 for getting groupby aggregation syntax
    total_offenses_by_city_and_state = pd.DataFrame(offense_data.groupby([CITY_COLUMN, STATE_COLUMN], as_index=False)[offense_col].sum())

    total_offenses_by_city_and_state[OFFENSE_TYPE_COLUMN] = offense_type
    total_offenses_by_city_and_state[YEAR_COLUMN] = year
    total_offenses_by_city_and_state[MONTH_COLUMN] = month

    total_offenses_by_city_and_state.rename(columns = {offense_col: OFFENSE_TOTAL_COLUMN}, inplace = True)

    return total_offenses_by_city_and_state, offense_type

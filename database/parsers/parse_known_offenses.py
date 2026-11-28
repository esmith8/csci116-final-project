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
from utility import convert_daily_monthly_to_quarterly

# Initializing constants which will be used throughout the script
SUMMARY_CITY_COLUMN = "address_city" # The city column saved for the summary file (2024 and earlier) is different than the newer files.
SUMMARY_STATE_COLUMN = "address_state" # The state column saved for the summary file (2024 and earlier) is different than the newer files.
SUMMARY_MSA_COLUMN = "population_1_msa"
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
DATE_COLUMN = "date"
ROBBERY_CODE = "120"
BURGLARY_CODE = "220"
MOTOR_VEHILE_THEFT_CODE = "240"
# Personally, I was on the fence about whether I should include simple assault or only use aggravated assault, but for my purposes
# I feel that the rate of people threatening and/or attempting (but failing) to do harm to others is enough to warrant the metric's
# inclusion on my list. I recognize that manslaughter, murder, and r*pe could have also been added as they are part of the
# existing dataset, but the quantities of those offenses are very low compared to assault and robbery and I'm not a fan of those words,
# so I have opted to not include them and will instead use robbery + aggravated assault + simple assault for "violent" crimes.
ASSAULT_CODE_LIST = [
    "13A", # Aggravated Assault, very serious bodily harm is done
    "13B", # Simple Assault, an attempt was made but the harm isn't nearly as bad.
    # "13C" # Intimidation (Not included in assault total based on how it was aggregated in lines 15-17 of Jacob Kaplan's source code: https://github.com/jacobkap/crime_data/blob/master/R/utils/offenses_known_utils.R)
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
# This list contains the final column subset desired from both dataframes
FINAL_COLUMN_LIST = [
    CITY_COLUMN,
    STATE_COLUMN,
    DATE_COLUMN,
    ROBBERY_COLUMN_NAME,
    ASSAULT_COLUMN_NAME,
    BURGLARY_COLUMN_NAME,
    THEFT_COLUMN_NAME,
    MOTOR_VEHICLE_THEFT_COLUMN_NAME
]

def get_known_offenses_quarterly_df(known_offenses_summary_path: str | Path, known_offenses_quarterly_folder: str | Path) -> pd.DataFrame:
    quarterly_original = parse_known_offenses_summary(known_offenses_summary_path=known_offenses_summary_path)
    quarterly_new = parse_known_offenses_quarterly(known_offenses_quarterly_folder=known_offenses_quarterly_folder)
    
    known_offenses_quarterly_df = pd.concat([quarterly_original, quarterly_new], ignore_index = True)
    known_offenses_quarterly_df.to_excel("final_test.xlsx", index = False)
    return known_offenses_quarterly_df


def parse_known_offenses_summary(known_offenses_summary_path: str | Path) -> pd.DataFrame:
    # There should only be one sheet in the known offenses summary, so the default read_excel parameters should be sufficient.
    known_offenses_summary_data = pd.read_excel(known_offenses_summary_path)

    # The data in the known offenses summary is already mostly cleaned, the only necessary steps are as follows:
    # 1. Rename the city columns to simply CITY_COLUMN and STATE_COLUMN
    known_offenses_summary_data.rename(columns = {SUMMARY_CITY_COLUMN: CITY_COLUMN,
                                                  SUMMARY_STATE_COLUMN: STATE_COLUMN}, 
                                       inplace = True)
    
    # 2. Convert the year and month columns to a single date column
    # Used Gemini Hydrogen 4.0 to make this conversion work.
    # The month column contains the full month's name in lowercase (for example, november)
    known_offenses_summary_data[DATE_COLUMN] = pd.to_datetime(
        known_offenses_summary_data[YEAR_COLUMN].astype(str) + "-" + known_offenses_summary_data[MONTH_COLUMN].str.strip(),
        format="%Y-%B",
    )
    known_offenses_summary_data.drop(columns = [YEAR_COLUMN,
                                                MONTH_COLUMN,
                                                SUMMARY_MSA_COLUMN], # MSA column is not needed either
                                     inplace = True)
    
    # 3. Convert the frequency from monthly to quarterly.
    known_offenses_summary_data_quarterly = convert_daily_monthly_to_quarterly(df = known_offenses_summary_data,
                                                                               aggregation_function = "sum",
                                                                               date_column_name = DATE_COLUMN,
                                                                               group_columns = [
                                                                                   CITY_COLUMN,
                                                                                   STATE_COLUMN
                                                                               ])
    
    # Only keeping necessary columns
    known_offenses_summary_data_quarterly = known_offenses_summary_data_quarterly[FINAL_COLUMN_LIST]
    
    return known_offenses_summary_data_quarterly


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
                                                        #  YEAR_COLUMN, 
                                                        #  MONTH_COLUMN,
                                                         DATE_COLUMN], as_index=False)[OFFENSE_TOTAL_COLUMN].sum())
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
                #   YEAR_COLUMN,
                #   MONTH_COLUMN,
                  DATE_COLUMN]

    # Used Gemini Hydrogen 4.0 to make it easier to outer merge all of the dataframes at once (instead of multiple uses of merge)
    total_quarterly_offense_df = (
        pd.concat([df.set_index(MERGE_KEYS) for df in total_df_list], axis = 1)
        .fillna(0)
        .reset_index()
    )

    # Only keeping necessary columns
    total_quarterly_offense_df = total_quarterly_offense_df[FINAL_COLUMN_LIST]

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
    # total_offenses_by_city_and_state[YEAR_COLUMN] = year
    # total_offenses_by_city_and_state[MONTH_COLUMN] = month
    total_offenses_by_city_and_state[DATE_COLUMN] = quarter_start_date

    total_offenses_by_city_and_state.rename(columns = {offense_col: OFFENSE_TOTAL_COLUMN}, inplace = True)

    return total_offenses_by_city_and_state, offense_type

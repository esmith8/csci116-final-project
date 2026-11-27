"""The purpose of this file is to convert the frequency of the monthly known offenses summary (2024 and earlier) to quarterly.
Additionally, the new quarterly data (2025 and later) is combined to find the total robbery, burglary, theft, and assault offenses
for each metropolitan statistical area (MSA).

It is assumed that the known_offenses_quarterly_folder only contains subdirectories which contain quarterly offense .xlsx files.
The code does not explicity check for other file formats (and .xlsx files with different contents) to ignore those files and will result in an error.

Additionally, the default file names used from the crime_etl_api_2025.py file should be kept, as the information for the associated quarter
is pulled from the filename itself, as I forgot to include the corresponding quarter as a column in the .xlsx file.
"""

import pandas as pd
from pathlib import Path

def parse_known_offenses_quarterly(known_offenses_quarterly_folder: str | Path) -> pd.DataFrame:
    # Guranteeing that known_offenses_quarterly_folder is a Path, which can be iterated upon.
    known_offenses_quarterly_folder = Path(known_offenses_quarterly_folder)

    list_of_offense_dataframes = []
    # Used Gemini Hydrogen 4.0 to find logic for iterating through subdirectories.
    for offense_folder in known_offenses_quarterly_folder.iterdir():
        # Ensuring that offense_folder is indeed a directory.
        if offense_folder.is_dir():
            print(f"Parsing folder for offense {offense_folder.name}")
            for known_offense_quarterly_path in offense_folder.iterdir():
                # Ensuring that known_offense_quarterly_path is indeed a file.
                if known_offense_quarterly_path.is_file():
                    quarterly_offense_df = parse_quarterly_offense_file(known_offense_quarterly_path = known_offense_quarterly_path)


def parse_quarterly_offense_file(known_offense_quarterly_path: Path) -> pd.DataFrame:
    # Because I forgot to include the quarter that this data represents in the file itself, the 
    # quarter must be parsed from the file name.
    return

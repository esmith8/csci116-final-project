"""This script was created primarily using Gemini Hydrogen 4.0,
Although I turned the core logic into a reusable function myself.
The purpose of this script is to usse the Energy Information Administration's
API to create and save relevant .csv and .xlsx files for use in creating predictors.
All API parameters were first found using the EIA's API Dashboard, and then translated
to the parameters used here, where the data is pulled and saved automatically."""

import pandas as pd
import requests

from pathlib import Path
import tomllib
CONFIG_PATH = Path("api_keys.toml")
def load_api_key(config_path: Path) -> str:
    api_key_dict = tomllib.loads(config_path.read_text(encoding="utf-8"))
    return api_key_dict["API_KEYS"]["EIA"]
API_KEY = load_api_key(CONFIG_PATH)

def get_data(url_path: str,
             parameters: dict,
             file_name: str):

    all_rows = []
    while True:
        res = requests.get(url_path, params=parameters).json()["response"]
        rows = res.get("data", [])
        if not rows:
            break
        all_rows.extend(rows)
        parameters["offset"] += len(rows)
        print(f"Fetched {len(all_rows)} of {res.get('total')} rows...")
        if len(all_rows) >= int(res.get("total", 0)):
            break

    df = pd.DataFrame(all_rows)
    df.to_csv(f"{file_name}.csv", index=False)
    df.to_excel(f"{file_name}.xlsx", index=False)


### Electricity Sales
# API Dashboard URL: https://www.eia.gov/opendata/browser/electricity/retail-sales?frequency=quarterly&data=customers;price;revenue;sales;&sortColumn=period;&sortDirection=asc;
BASE_URL_ELECTRICITY_SALES = "https://api.eia.gov/v2/electricity/retail-sales/data/"

PARAMETERS_ELECTRICITY_SALES = {
    "api_key": API_KEY,
    "frequency": "quarterly",
    "data[0]": "customers",
    "data[1]": "price",
    "data[2]": "revenue",
    "data[3]": "sales",
    "sort[0][column]": "period",
    "sort[0][direction]": "asc",
    "offset": 0,
    "length": 5000,
}

ELECTRICITY_SALES_FILE_NAME = "../data/eia_electricity_retail_sales_quarterly"

get_data(url_path=BASE_URL_ELECTRICITY_SALES,
         parameters=PARAMETERS_ELECTRICITY_SALES,
         file_name=ELECTRICITY_SALES_FILE_NAME)

### Natural Gas Consumption
# API Dashboard URL: https://www.eia.gov/opendata/browser/natural-gas/cons/sum?frequency=monthly&data=value;&start=1999-01&sortColumn=period;&sortDirection=asc;

BASE_URL_NATURAL_GAS_CONSUMPTION = "https://api.eia.gov/v2/natural-gas/cons/sum/data/"

PARAMETERS_NATURAL_GAS_CONSUMPTION = {
    "api_key": API_KEY,
    "frequency": "monthly",
    "data[0]": "value",
    "sort[0][column]": "period",
    "sort[0][direction]": "asc",
    "offset": 0,
    "length": 5000,
}

NATURAL_GAS_CONSUMPTION_FILE_NAME = "../data/eia_natural_gas_consumption_monthly"

get_data(url_path=BASE_URL_NATURAL_GAS_CONSUMPTION,
         parameters=PARAMETERS_NATURAL_GAS_CONSUMPTION,
         file_name=NATURAL_GAS_CONSUMPTION_FILE_NAME)
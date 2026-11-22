"""The purpose of this file is to generate a quarterly dataset of """

import logging
import time
import tomllib
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

# --- Configuration ---
CONFIG_PATH = Path("api_keys.toml")
INPUT_CSV = Path("ori9_metro_mapping_trimmed.csv")
OFFENSE_CODE = "120"
OUTPUT_DIR = Path(f"nibrs_output{OFFENSE_CODE}")

BASE_URL = "https://api.usa.gov/crime/fbi/cde/nibrs/agency"


DATE_RANGES = [
    ("01-2025", "03-2025"),
    ("04-2025", "06-2025"),
    ("07-2025", "09-2025"),
    ("10-2025", "12-2025"),
]

SLEEP_MINUTES = 65
MAX_REQUESTS_PER_CYCLE = 950  # Safety buffer under the 1,000/hour limit
SAVE_EVERY_N_ROWS = 20

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def load_api_key(config_path: Path) -> str:
    api_key_dict = tomllib.loads(config_path.read_text(encoding="utf-8"))
    return api_key_dict["API_KEYS"]["NIBRS"]


def get_range_dataframe(start_date: str, end_date: str) -> tuple[pd.DataFrame, Path]:
    """Load existing progress CSV for a date range, or initialize it from the input CSV."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"ori9_offense{OFFENSE_CODE}_{start_date}_to_{end_date}.csv"

    if output_path.exists():
        df = pd.read_csv(output_path, dtype={"ori9": str, "offense120": "Int64"})
    else:
        df = pd.read_csv(INPUT_CSV, dtype={"ori9": str})
        df["offense120"] = pd.Series(pd.NA, index=df.index, dtype="Int64")
        df.to_csv(output_path, index=False)

    return df, output_path


def sum_victim_locations(payload: dict) -> int:
    """Sum all numeric values inside victim -> location."""
    locations = payload.get("victim", {}).get("location", {})
    if not isinstance(locations, dict):
        return 0
    return int(sum(v for v in locations.values() if isinstance(v, (int, float))))


def fetch_agency_offense(
    session: requests.Session,
    ori9: str,
    start_date: str,
    end_date: str,
    api_key: str,
    max_retries: int = 3,
) -> tuple[str, int | None, bool]:
    """
    Query the NIBRS endpoint for a single ORI9 and date range.

    Returns:
        (status, value, quota_exhausted)
        status: "ok" | "rate_limited" | "invalid" | "error"
    """
    url = f"{BASE_URL}/{ori9}/{OFFENSE_CODE}"
    params = {
        "from": start_date,
        "to": end_date,
        "API_KEY": api_key,
    }

    for attempt in range(1, max_retries + 1):
        try:
            resp = session.get(url, params=params, timeout=30)

            # Check remaining quota header from api.usa.gov
            remaining_hdr = resp.headers.get("X-RateLimit-Remaining")
            quota_exhausted = remaining_hdr is not None and int(remaining_hdr) <= 1

            if resp.status_code == 429:
                return "rate_limited", None, True

            if resp.status_code == 200:
                total_locations = sum_victim_locations(resp.json())
                return "ok", total_locations, quota_exhausted

            if resp.status_code in (400, 404):
                logging.warning("ORI9 %s returned HTTP %s; marking as -1.", ori9, resp.status_code)
                return "invalid", -1, quota_exhausted

            logging.warning(
                "HTTP %s for ORI9 %s (attempt %d/%d)",
                resp.status_code,
                ori9,
                attempt,
                max_retries,
            )
        except requests.RequestException as exc:
            logging.warning(
                "Network error for ORI9 %s (attempt %d/%d): %s",
                ori9,
                attempt,
                max_retries,
                exc,
            )

        time.sleep(2 * attempt)

    return "error", None, False


def run_batch(api_key: str) -> bool:
    """
    Process pending rows across date ranges until either all ranges complete
    or the hourly API rate limit is reached.

    Returns True if ALL date ranges are completely finished, False otherwise.
    """
    requests_made = 0

    with requests.Session() as session:
        for start_date, end_date in DATE_RANGES:
            df, output_path = get_range_dataframe(start_date, end_date)
            pending_indices = df.index[df["offense120"].isna()].tolist()

            if not pending_indices:
                logging.info("Range %s to %s is already complete.", start_date, end_date)
                continue

            logging.info(
                "Processing range %s to %s (%d/%d rows remaining)...",
                start_date,
                end_date,
                len(pending_indices),
                len(df),
            )

            unsaved_count = 0
            try:
                for idx in pending_indices:
                    if requests_made >= MAX_REQUESTS_PER_CYCLE:
                        df.to_csv(output_path, index=False)
                        logging.info(
                            "Reached safety cap of %d requests. Saved progress to %s.",
                            MAX_REQUESTS_PER_CYCLE,
                            output_path,
                        )
                        return False

                    ori9 = str(df.at[idx, "ori9"]).strip()
                    status, value, quota_exhausted = fetch_agency_offense(
                        session, ori9, start_date, end_date, api_key
                    )
                    requests_made += 1

                    if status == "rate_limited":
                        df.to_csv(output_path, index=False)
                        logging.warning(
                            "Hit HTTP 429 rate limit at ORI9 %s. Saved progress to %s.",
                            ori9,
                            output_path,
                        )
                        return False

                    if status in ("ok", "invalid") and value is not None:
                        df.at[idx, "offense120"] = value
                        unsaved_count += 1

                    if unsaved_count >= SAVE_EVERY_N_ROWS:
                        df.to_csv(output_path, index=False)
                        unsaved_count = 0
                        logging.info(
                            "Saved checkpoint (%d requests used this cycle).",
                            requests_made,
                        )

                    if quota_exhausted:
                        df.to_csv(output_path, index=False)
                        logging.warning(
                            "API quota depleted per response header. Saved progress to %s.",
                            output_path,
                        )
                        return False

                    time.sleep(0.1)  # Avoid burst throttling

            finally:
                # Always flush progress on exit, error, or Ctrl+C
                df.to_csv(output_path, index=False)

            logging.info("Completed range %s to %s -> %s", start_date, end_date, output_path)

    return True


def main() -> None:
    api_key = load_api_key(CONFIG_PATH)

    while True:
        logging.info("Starting fetch cycle...")
        all_done = run_batch(api_key)

        if all_done:
            logging.info("All date ranges are 100%% complete. Exiting.")
            break

        next_run = datetime.now() + timedelta(minutes=SLEEP_MINUTES)
        logging.info(
            "Sleeping for %d minutes. Next run at %s.",
            SLEEP_MINUTES,
            next_run.strftime("%Y-%m-%d %H:%M:%S"),
        )
        time.sleep(SLEEP_MINUTES * 60)


if __name__ == "__main__":
    main()
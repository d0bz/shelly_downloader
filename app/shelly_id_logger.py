import hashlib
import os
import requests
import csv
import time
from datetime import datetime, timedelta, date
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv

# -----------------------------
# Config
# -----------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
env_path = SCRIPT_DIR / ".env"
if not env_path.exists():
    env_path = SCRIPT_DIR.parent / ".env"

if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()

EMAIL = os.getenv("SHELLY_EMAIL")
PASSWORD = os.getenv("SHELLY_PASSWORD")
if not EMAIL or not PASSWORD:
    raise RuntimeError("Missing SHELLY_EMAIL or SHELLY_PASSWORD in environment variables or .env file")

OUTPUT_DIR = Path("/data")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DATE_FROM = "2025-10-12"
LOG_SHELLY = True
LOG_FRR = True
LOG_NORPOOL = True

FRR_DATA_IDS = [
    "local_marginal_price_mfrr",
    "normal_activations_sa_mfrr",
    "normal_activations_da_mfrr",
    "activations_afrr",
    "local_marginal_price_afrr"
]
COMBINED_FRR_FILENAME = "FRR_EST.csv"
ELERING_FILENAME = "NordPool_EST.csv"
BASE_URL_FRR = "https://api-baltic.transparency-dashboard.eu/api/v1/export"

# -----------------------------
# Shelly functions
# -----------------------------
def get_shelly_token():
    url = "https://api2.shelly.cloud/v2/users/auth/login"
    headers = {"Content-Type": "application/json"}
    hashed_pw = hashlib.sha1(PASSWORD.encode("utf-8")).hexdigest()
    payload = {"email": EMAIL, "password": hashed_pw}
    r = requests.post(url, json=payload, headers=headers, timeout=30)
    r.raise_for_status()
    data = r.json()
    return data.get("accessToken")

def get_all_devices(token):
    url = "https://shelly-79-eu.shelly.cloud/interface/device/get_all_lists"
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.post(url, headers=headers, timeout=30)
    r.raise_for_status()
    devices = r.json().get("data", {}).get("devices", {})
    return {d: info.get("server") for d, info in devices.items()}

def fetch_consumption(token, device_id, dt, base_url):
    url = f"https://{base_url}/v2/statistics/power-consumption"
    params = {
        "id": device_id,
        "channel": 0,
        "date_range": "custom",
        "date_from": dt.strftime("%Y-%m-%d %H:00:00"),
        "date_to": (dt + timedelta(hours=1, seconds=-1)).strftime("%Y-%m-%d %H:%M:%S")
    }
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=30)
        if r.status_code != 200:
            return []
        return r.json().get("history", [])
    except requests.RequestException:
        return []

def file_path(device_id):
    return OUTPUT_DIR / f"{device_id}.csv"

def ensure_csv(path):
    if not path.exists():
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["datetime", "voltage", "consumption"])
            writer.writeheader()

def append_rows(path, rows):
    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["datetime", "voltage", "consumption"])
        for r in rows:
            writer.writerow({
                "datetime": r.get("datetime", ""),
                "voltage": r.get("voltage", ""),
                "consumption": r.get("consumption", "")
            })

def get_last_logged_dt(path):
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, usecols=["datetime"])
        if df.empty:
            return None
        last_str = str(df["datetime"].dropna().iloc[-1])
        return datetime.strptime(last_str, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None

# -----------------------------
# FRR functions
# -----------------------------
def months_between(start_dt, end_dt):
    months = []
    cur = datetime(start_dt.year, start_dt.month, 1)
    end_month = datetime(end_dt.year, end_dt.month, 1)
    while cur <= end_month:
        months.append((cur.year, cur.month))
        if cur.month == 12:
            cur = datetime(cur.year + 1, 1, 1)
        else:
            cur = datetime(cur.year, cur.month + 1, 1)
    return months


def fetch_month_frr(data_id, year, month):
    start_date = datetime(year, month, 1)
    if month == 12:
        end_date = datetime(year + 1, 1, 1)
    else:
        end_date = datetime(year, month + 1, 1)
    params = {
        "id": data_id,
        "start_date": start_date.strftime("%Y-%m-%dT%H:%M"),
        "end_date": end_date.strftime("%Y-%m-%dT%H:%M"),
        "output_time_zone": "EET",
        "output_format": "json",
        "json_header_groups": "0"
    }
    r = requests.get(BASE_URL_FRR, params=params, timeout=60)
    r.raise_for_status()
    data = r.json()
    rows = []
    if not data.get("error") and "timeseries" in data.get("data", {}):
        for entry in data["data"]["timeseries"]:
            ts = entry["from"]
            vals = entry["values"]
            rows.append([ts] + vals)
    return rows


def run_frr_logger(output_dir, date_from, date_to):
    start_dt = datetime.strptime(date_from, "%Y-%m-%d")
    end_dt = datetime.strptime(date_to, "%Y-%m-%d")
    months = months_between(start_dt, end_dt)
    combined_df = None

    for data_id in FRR_DATA_IDS:
        df_all = None
        for (y, m) in months:
            rows = fetch_month_frr(data_id, y, m)
            if not rows:
                continue
            header = ["date", "ESTup", "ESTdown", "LVup", "LVdown", "LTup", "LTdown"]
            df = pd.DataFrame(rows, columns=header)
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date")
            df = df[["ESTup", "ESTdown"]].astype(float)
            if df_all is None:
                df_all = df
            else:
                df_all = pd.concat([df_all, df])

        if df_all is None:
            continue

        df_all = df_all[~df_all.index.duplicated(keep="first")]
        df_all = df_all.sort_index()
        df_all = df_all.rename(columns=lambda x: f"{data_id}_{x}")

        if combined_df is None:
            combined_df = df_all
        else:
            combined_df = combined_df.join(df_all, how="outer")

    if combined_df is not None:
        try:
            if combined_df.index.tz is not None:
                combined_df.index = combined_df.index.tz_convert(None)
        except Exception:
            pass

        combined_df.index = combined_df.index.strftime("%Y-%m-%d %H:%M:%S")
        combined_df.index.name = "datetime"

        (Path(output_dir) / COMBINED_FRR_FILENAME).parent.mkdir(parents=True, exist_ok=True)
        combined_df.to_csv(Path(output_dir) / COMBINED_FRR_FILENAME, sep=",", decimal=".", encoding="utf-8")
        print("FRR data saved:", Path(output_dir) / COMBINED_FRR_FILENAME)
    else:
        print("No FRR data fetched")


# -----------------------------
# Nordpool / Elering functions
# -----------------------------
def to_utc_iso(dt_str):
    dt = datetime.strptime(dt_str, "%Y-%m-%d")
    dt_utc = dt - timedelta(hours=3)
    return dt_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def run_norpool_logger(output_dir, date_from, date_to):
    start_utc = to_utc_iso(date_from)
    end_utc = to_utc_iso(date_to)
    url = (
        "https://dashboard.elering.ee/api/nps/price/csv"
        f"?start={start_utc}"
        f"&end={end_utc}"
        "&fields=ee"
    )
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    text = r.content.decode("utf-8", errors="replace")
    lines = text.splitlines()
    out_lines = []
    for i, line in enumerate(lines):
        if i == 0:
            out_lines.append("timestamp,datetime,price")
            continue
        if not line.strip():
            continue
        parts = line.split(";")
        if len(parts) >= 3:
            parts[2] = parts[2].replace(",", ".")
            out_lines.append(",".join(parts))
        else:
            out_lines.append(line.replace(";", ","))
    out_text = "\n".join(out_lines) + "\n"
    (Path(output_dir) / ELERING_FILENAME).write_text(out_text, encoding="utf-8")
    print("Nordpool prices saved:", Path(output_dir) / ELERING_FILENAME)


# -----------------------------
# Main
# -----------------------------
def run_all():
    today = date.today()
    # stop at yesterday 00:00 — do not include yesterday or today
    end_dt = datetime.combine(today - timedelta(days=1), datetime.min.time())
    date_to = (today - timedelta(days=1)).strftime("%Y-%m-%d")

    if LOG_SHELLY:
        print("Starting Shelly logging...")
        try:
            token = get_shelly_token()
            devices = get_all_devices(token)
        except Exception as e:
            print("Shelly login failed:", e)
            devices = {}

        print(f"Total devices: {len(devices)}")

        for idx, (dev_id, server) in enumerate(devices.items(), start=1):
            path = file_path(dev_id)
            last_dt = get_last_logged_dt(path)

            # Determine start time per device
            if last_dt:
                if last_dt >= end_dt:
                    print(f"[{idx}/{len(devices)}] {dev_id}: up to date (until {last_dt.date()}), skipping")
                    continue
                start_dt = last_dt.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            else:
                ensure_csv(path)
                start_dt = datetime.strptime(DATE_FROM, "%Y-%m-%d")

            print(f"[{idx}/{len(devices)}] {dev_id}: logging from {start_dt} to {end_dt - timedelta(hours=1)}")

            cur = start_dt
            while cur < end_dt:
                rows = fetch_consumption(token, dev_id, cur, server)
                if rows:
                    append_rows(path, rows)
                else:
                    print(f"No data for {dev_id} {cur}")
                cur += timedelta(hours=1)
                time.sleep(0.05)

    # Always log FRR and Nordpool
    if LOG_FRR:
        run_frr_logger(OUTPUT_DIR, DATE_FROM, date_to)
    if LOG_NORPOOL:
        run_norpool_logger(OUTPUT_DIR, DATE_FROM, date_to)

    print("All logging complete.")

if __name__ == "__main__":
    run_all()

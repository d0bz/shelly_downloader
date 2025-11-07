# Shelly Downloader

Utility scripts for collecting Shelly consumption history plus FRR and Nordpool market data, and a tiny Flask downloader UI that serves the generated CSV files.

The recommended way to run everything (cron job + web app) is inside Docker, but you can also execute the scripts directly for quick checks.

## Prerequisites
- Docker and Docker Compose (v2+).
- Python 3.11+ if you want to run the scripts directly.

Before first run:

1. Copy `.env.sample` to `.env` and fill in your real Shelly Cloud credentials.
2. Edit `app/shelly_id_logger.py` to tweak the remaining config near the top (`DATE_FROM`, toggles for the different data sources, etc.).

## Run with Docker
1. Build and start the stack:
   ```bash
   docker compose up --build -d
   ```
   This launches a container named `csvbox` that runs both the Flask app and a cron job (daily at 03:00 container time) via Supervisor.

2. Verify everything is healthy:
   ```bash
   docker compose ps
   docker compose logs -f csvbox
   ```

3. Generated CSV files land in the container’s `/data` volume, mapped to the local `./data` directory. The web UI is available at [http://localhost:8008](http://localhost:8008) and exposes:
   - `FRR_EST.csv`
   - `NordPool_EST.csv`
   - Individual device CSVs (`<device-id>.csv`) collected by the Shelly logger.

4. Stop the stack when you are done:
   ```bash
   docker compose down
   ```

## Run Scripts Manually
For ad hoc runs outside Docker:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Generate CSVs once
python app/shelly_id_logger.py

# Serve the download UI (defaults to port 8008)
DATA_DIR=./data python app/web.py
```

You can override where CSVs are written by changing `OUTPUT_DIR` in `app/shelly_id_logger.py`. Make sure the Flask app’s `DATA_DIR` points to the same location so the files appear in the UI.

## Cron & Supervisor Details
- Cron schedule lives in `crontab` (`/etc/cron.d/generate_csv` inside the container) and pipes log output to `/var/log/script.log`.
- `supervisord.conf` starts both cron and the Flask web app, supervised for automatic restarts.

## Useful Paths
- Data volume (outside container): `./data`
- Supervisor logs (inside container): `/var/log/supervisor/`
- One-off script log (inside container): `/var/log/script.log`

from flask import Flask, send_from_directory, render_template_string, request
from pathlib import Path
import re

app = Flask(__name__, static_folder=None)
DATA_DIR = Path("/data")
SAFE_ID = re.compile(r"^[A-Za-z0-9_\-\.]+$")

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Download Reports</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 40px; max-width: 700px; }
    input, button { font-size:16px; padding:8px; }
    form { margin-top: 16px; display: flex; gap: 8px; }
    #message { margin-top: 18px; color: {{ color|default('red') }}; }
    a { display:block; margin-top:8px; font-size:16px; }
  </style>
</head>
<body>
  <h1>Download Reports</h1>

  <h2>Direct Files</h2>
  <a href="/direct/FRR_EST.csv" download>Download FRR_EST.csv</a>
  <a href="/direct/NordPool_EST.csv" download>Download NordPool_EST.csv</a>

  <hr style="margin: 30px 0;">

  <h2>Download by ID</h2>
  <p>Enter your ID and click Download (downloads &lt;ID&gt;.csv):</p>

  <form method="GET" action="/download">
    <input type="text" name="id" placeholder="Enter ID" required>
    <button type="submit">Download</button>
  </form>

  {% if message %}
    <p id="message">{{ message }}</p>
  {% endif %}
</body>
</html>
"""

@app.get("/")
def index():
    return render_template_string(HTML_PAGE)

@app.get("/download")
def download():
    raw = (request.args.get("id") or "").strip()
    if not raw:
        return render_template_string(HTML_PAGE, message="Please enter an ID.")
    if not SAFE_ID.match(raw):
        return render_template_string(HTML_PAGE, message="Invalid ID format. Allowed: letters, numbers, _ - .")
    filename = f"{raw}.csv"
    file_path = DATA_DIR / filename
    if not file_path.exists():
        return render_template_string(HTML_PAGE, message="No file found for that ID.")
    return send_from_directory(DATA_DIR, filename, as_attachment=True)

@app.get("/direct/<filename>")
def direct(filename):
    file_path = DATA_DIR / filename
    if not file_path.exists():
        return render_template_string(HTML_PAGE, message=f"{filename} not found.")
    return send_from_directory(DATA_DIR, filename, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8008)

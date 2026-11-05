import os
import re
import subprocess
import sys
import time
from pathlib import Path
import httpx

BASE_DIR = Path(__file__).resolve().parent
CLOUDFLARED_EXE = BASE_DIR / "cloudflared.exe"
URL_FILE = BASE_DIR / "tunnel_url.txt"
LOG_FILE = BASE_DIR / "tunnel.log"

if not CLOUDFLARED_EXE.exists():
    print(f"Error: {CLOUDFLARED_EXE} not found.")
    sys.exit(1)

print("Starting Cloudflare Tunnel to http://127.0.0.1:8088 ...")

log_fp = open(LOG_FILE, "w", encoding="utf-8")
cmd = [str(CLOUDFLARED_EXE), "tunnel", "--url", "http://127.0.0.1:8088"]
proc = subprocess.Popen(cmd, stdout=log_fp, stderr=subprocess.STDOUT, text=True)

tunnel_url = None
start_time = time.time()
print("Waiting for Cloudflare Tunnel public URL...")

while time.time() - start_time < 30:
    time.sleep(1)
    if LOG_FILE.exists():
        with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            match = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", content)
            if match:
                tunnel_url = match.group(0)
                break

if not tunnel_url:
    print("Failed to obtain Cloudflare Tunnel URL within 30 seconds.")
    sys.exit(1)

with open(URL_FILE, "w", encoding="utf-8") as f:
    f.write(tunnel_url)

print(f"\n========================================================")
print(f" SUCCESS: Cloudflare Tunnel is LIVE 24/7!")
print(f" Public URL: {tunnel_url}")
print(f" Saved to:   {URL_FILE}")
print(f"========================================================\n")

# Verify public access
for attempt in range(5):
    try:
        r = httpx.get(f"{tunnel_url}/health", timeout=10.0)
        if r.status_code == 200:
            print(f" Verified public access: HTTP {r.status_code} OK")
            break
    except Exception as e:
        print(f"Waiting for DNS propagation ({attempt+1}/5)...")
        time.sleep(2)

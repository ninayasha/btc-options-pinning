import sqlite3, time, sys
sys.path.append(r'C:\Users\Noname\.gemini\antigravity\scratch\btc-pinning-dashboard')

conn = sqlite3.connect(r'C:\Users\Noname\.gemini\antigravity\scratch\btc-pinning-dashboard\data\btc_pinning.db')
c = conn.cursor()

print("--- Indexes on oi_by_strike ---")
for r in c.execute("PRAGMA index_info(idx_oi_by_strike_snap)").fetchall():
    print("idx_oi_by_strike_snap:", r)

print("--- Indexes on snapshots ---")
for r in c.execute("PRAGMA index_info(idx_snapshots_expiry)").fetchall():
    print("idx_snapshots_expiry:", r)

from web.app import api_timeline
import json

for test_exp in ['group_today', 'group_weekly', 'group_monthly', 'all', '2026-11-06']:
    t0 = time.time()
    res = api_timeline(test_exp, 'active')
    dur = time.time() - t0
    payload_str = json.dumps(res)
    payload_mb = len(payload_str) / (1024 * 1024)
    snaps_count = len(res.get('snapshots', []))
    print(f"Expiry '{test_exp}': {dur:.3f}s | Snaps: {snaps_count} | Payload: {payload_mb:.2f} MB")

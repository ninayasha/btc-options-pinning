import sqlite3, time

conn = sqlite3.connect(r'C:\Users\Noname\.gemini\antigravity\scratch\btc-pinning-dashboard\data\btc_pinning.db')

t0 = time.time()
cur_exp = conn.execute("""
    SELECT s.expiry_date, s.expiry_type, COUNT(*) as snap_count,
           MAX(s.snapshot_time_bkk) as last_snap,
           (
               SELECT s2.total_oi
               FROM snapshots s2
               WHERE s2.expiry_date = s.expiry_date
               ORDER BY s2.snapshot_time_bkk DESC
               LIMIT 1
           ) as latest_total_oi,
           (
               SELECT s2.total_volume
               FROM snapshots s2
               WHERE s2.expiry_date = s.expiry_date
               ORDER BY s2.snapshot_time_bkk DESC
               LIMIT 1
           ) as latest_total_volume
    FROM snapshots s
    GROUP BY s.expiry_date
    ORDER BY s.expiry_date ASC
""")
r1 = cur_exp.fetchall()
t1 = time.time()
print(f"cur_exp: {t1 - t0:.4f}s ({len(r1)} rows)")

cur_latest_vol = conn.execute("""
    WITH latest_snaps AS (
        SELECT expiry_date, MAX(snapshot_time_bkk) as max_time
        FROM oi_by_strike
        GROUP BY expiry_date
    )
    SELECT o.expiry_date, ROUND(SUM(COALESCE(o.call_volume_24h, 0) + COALESCE(o.put_volume_24h, 0)), 2) as vol
    FROM oi_by_strike o
    JOIN latest_snaps ls ON o.expiry_date = ls.expiry_date AND o.snapshot_time_bkk = ls.max_time
    GROUP BY o.expiry_date
""")
r2 = cur_latest_vol.fetchall()
t2 = time.time()
print(f"cur_latest_vol: {t2 - t1:.4f}s ({len(r2)} rows)")

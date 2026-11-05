import sqlite3, time
from collections import defaultdict
from src.options_math import calculate_max_pain

conn = sqlite3.connect(r'C:\Users\Noname\.gemini\antigravity\scratch\btc-pinning-dashboard\data\btc_pinning.db')
conn.row_factory = sqlite3.Row

# Get all active dates
cur = conn.execute("SELECT DISTINCT expiry_date FROM snapshots WHERE expiry_date >= '2026-11-04'")
target_dates = [r[0] for r in cur.fetchall()]
print(f"Target dates: {len(target_dates)} expiries ({target_dates})")

placeholders = ",".join("?" for _ in target_dates)

t0 = time.time()
cur_times = conn.execute(f"""
    SELECT snapshot_time_bkk, MAX(index_price) as index_price,
           label, MAX(dvol) as dvol, MAX(atm_iv) as atm_iv
    FROM snapshots
    WHERE expiry_date IN ({placeholders})
    GROUP BY snapshot_time_bkk
    ORDER BY snapshot_time_bkk ASC
""", tuple(target_dates))
times_rows = [dict(r) for r in cur_times.fetchall()]
t1 = time.time()
print(f"Times rows query: {t1 - t0:.4f}s ({len(times_rows)} timestamps)")

cur_all_agg = conn.execute(
    f"""
    SELECT snapshot_time_bkk, strike,
           ROUND(SUM(call_oi), 2) as call_oi,
           ROUND(SUM(put_oi), 2) as put_oi,
           ROUND(SUM(total_oi), 2) as total_oi,
           ROUND(SUM(call_oi_usd), 2) as call_oi_usd,
           ROUND(SUM(put_oi_usd), 2) as put_oi_usd,
           ROUND(SUM(call_volume_24h), 2) as call_volume_24h,
           ROUND(SUM(put_volume_24h), 2) as put_volume_24h,
           ROUND(SUM(COALESCE(call_volume_24h, 0) + COALESCE(put_volume_24h, 0)), 2) as total_volume_24h,
           ROUND(SUM(call_gex_usd), 2) as call_gex_usd,
           ROUND(SUM(put_gex_usd), 2) as put_gex_usd,
           ROUND(SUM(net_gex_usd), 2) as net_gex_usd,
           ROUND(AVG(call_iv), 1) as call_iv,
           ROUND(AVG(put_iv), 1) as put_iv
    FROM oi_by_strike
    WHERE expiry_date IN ({placeholders})
    GROUP BY snapshot_time_bkk, strike
    ORDER BY snapshot_time_bkk ASC, strike ASC
    """,
    tuple(target_dates),
)
strikes_by_time = defaultdict(list)
for r in cur_all_agg.fetchall():
    st_dict = dict(r)
    snap_time = st_dict.pop("snapshot_time_bkk")
    strikes_by_time[snap_time].append(st_dict)
t2 = time.time()
print(f"Strikes aggregate query: {t2 - t1:.4f}s (Fetched {sum(len(v) for v in strikes_by_time.values())} strike records)")

# Max Pain loop
t_mp0 = time.time()
for t_row in times_rows:
    agg_strikes = strikes_by_time.get(t_row["snapshot_time_bkk"], [])
    if agg_strikes:
        calculate_max_pain(agg_strikes)
t_mp1 = time.time()
print(f"Max pain calculation loop: {t_mp1 - t_mp0:.4f}s")

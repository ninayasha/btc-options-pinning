import sqlite3, time

conn = sqlite3.connect(r'C:\Users\Noname\.gemini\antigravity\scratch\btc-pinning-dashboard\data\btc_pinning.db')
c = conn.cursor()

c.execute("CREATE INDEX IF NOT EXISTS idx_oi_by_strike_exp_snap ON oi_by_strike(expiry_date, snapshot_time_bkk, strike)")
conn.commit()

print("New query plan for single expiry:")
for r in c.execute("EXPLAIN QUERY PLAN SELECT strike, call_oi, put_oi FROM oi_by_strike WHERE expiry_date = '2026-11-06' ORDER BY snapshot_time_bkk ASC, strike ASC").fetchall():
    print(r)

t0 = time.time()
c.execute("SELECT strike, call_oi, put_oi FROM oi_by_strike WHERE expiry_date = '2026-11-06' ORDER BY snapshot_time_bkk ASC, strike ASC").fetchall()
print(f"Single expiry query time with new index: {time.time() - t0:.4f}s")

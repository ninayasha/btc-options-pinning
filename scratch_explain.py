import sqlite3

conn = sqlite3.connect(r'C:\Users\Noname\.gemini\antigravity\scratch\btc-pinning-dashboard\data\btc_pinning.db')
c = conn.cursor()

c.execute("EXPLAIN QUERY PLAN SELECT snapshot_time_bkk, strike FROM oi_by_strike WHERE expiry_date IN ('2026-11-06', '2026-11-13') GROUP BY snapshot_time_bkk, strike")
print("Query plan for GROUP BY on oi_by_strike:")
for r in c.fetchall():
    print(r)

c.execute("EXPLAIN QUERY PLAN SELECT * FROM oi_by_strike WHERE expiry_date = '2026-11-06' ORDER BY snapshot_time_bkk ASC, strike ASC")
print("\nQuery plan for single expiry:")
for r in c.fetchall():
    print(r)

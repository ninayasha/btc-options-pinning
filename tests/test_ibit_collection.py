import pytest
from src.config import DB_PATH, ETH_DB_PATH, IBIT_DB_PATH
from src.db import get_db, get_ibit_db, init_db, init_eth_db, init_ibit_db
from src.ibit_collector import run_ibit_snapshot, OCC_PATTERN


def test_occ_pattern_regex():
    sample_call = "IBIT270115C00050000"
    m = OCC_PATTERN.match(sample_call)
    assert m is not None
    yy, mm, dd, cp, k_str = m.groups()
    assert yy == "27"
    assert mm == "01"
    assert dd == "15"
    assert cp == "C"
    assert float(k_str) / 1000.0 == 50.0

    sample_put = "IBIT261218P00037500"
    m2 = OCC_PATTERN.match(sample_put)
    assert m2 is not None
    yy2, mm2, dd2, cp2, k_str2 = m2.groups()
    assert cp2 == "P"
    assert float(k_str2) / 1000.0 == 37.5


def test_ibit_db_schema():
    init_ibit_db()
    with get_ibit_db() as conn:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        assert "snapshots" in tables
        assert "oi_by_strike" in tables
        assert "big_expiries" in tables
        assert "expiry_results" in tables
        assert "execution_logs" in tables


def test_ibit_collection_isolation():
    init_db()
    init_eth_db()
    init_ibit_db()

    with get_db(DB_PATH) as btc_conn:
        btc_count_before = btc_conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]

    with get_db(ETH_DB_PATH) as eth_conn:
        eth_count_before = eth_conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]

    res = run_ibit_snapshot(label="test_isolation", auto_backup=False)
    assert res["status"] == "success"
    assert res["currency"] == "IBIT"
    assert res["expiries_count"] > 0
    assert res["primary"]["spot"] > 0

    with get_ibit_db() as ibit_conn:
        ibit_snaps = ibit_conn.execute("SELECT COUNT(*) FROM snapshots WHERE label='test_isolation'").fetchone()[0]
        assert ibit_snaps > 0

    # Ensure BTC and ETH databases were completely untouched
    with get_db(DB_PATH) as btc_conn:
        btc_count_after = btc_conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
        assert btc_count_after == btc_count_before

    with get_db(ETH_DB_PATH) as eth_conn:
        eth_count_after = eth_conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
        assert eth_count_after == eth_count_before

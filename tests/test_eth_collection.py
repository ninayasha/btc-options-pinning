import sqlite3
import pytest
from src.config import DB_PATH, ETH_DB_PATH
from src.db import init_db, init_eth_db, get_db, get_eth_db
from src.collector import run_snapshot, run_eth_snapshot
from src.gdrive_backup import backup_all_databases


def test_eth_db_schema():
    init_eth_db()
    with get_eth_db() as conn:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        assert "snapshots" in tables
        assert "oi_by_strike" in tables
        assert "big_expiries" in tables
        assert "expiry_results" in tables
        assert "execution_logs" in tables


def test_eth_collection_isolation():
    """Verify collecting ETH data writes exclusively to eth_pinning.db without affecting btc_pinning.db."""
    init_db()
    init_eth_db()

    # Count BTC snapshots before
    with get_db(DB_PATH) as btc_conn:
        btc_count_before = btc_conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]

    # Collect live ETH snapshot
    res = run_eth_snapshot(label="test_eth_run", auto_backup=False)
    assert res["status"] == "success"
    assert res["currency"] == "ETH"
    assert res["expiries_count"] > 0
    assert res["primary"]["spot"] > 500  # ETH spot is well above $500

    # Verify ETH database has records
    with get_eth_db() as eth_conn:
        eth_count = eth_conn.execute("SELECT COUNT(*) FROM snapshots WHERE label='test_eth_run'").fetchone()[0]
        assert eth_count > 0

        # Verify strike data exists in eth_pinning.db
        eth_strikes = eth_conn.execute("SELECT COUNT(*) FROM oi_by_strike WHERE label='test_eth_run'").fetchone()[0]
        assert eth_strikes > 0

    # Verify BTC database count has NOT changed at all
    with get_db(DB_PATH) as btc_conn:
        btc_count_after = btc_conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
        assert btc_count_after == btc_count_before

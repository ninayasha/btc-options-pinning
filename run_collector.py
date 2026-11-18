import sys
from src.collector import run_all_snapshots, run_snapshot
from src.db import init_db, init_eth_db, init_ibit_db
from src.ibit_collector import run_ibit_snapshot
from src.settle import run_all_settlements, run_settlement


def main():
    init_db()
    init_eth_db()
    init_ibit_db()
    action = sys.argv[1] if len(sys.argv) > 1 else "manual"
    currency = sys.argv[2] if len(sys.argv) > 2 else "all"

    if action == "settle":
        target_date = sys.argv[3] if len(sys.argv) > 3 else None
        if currency.upper() in ("BTC", "ETH"):
            print(f"Running settlement for {currency.upper()} on date {target_date or 'today'}...")
            res = run_settlement(target_date, currency=currency.upper())
        else:
            print(f"Running settlement for ALL (BTC & ETH) on date {target_date or 'today'}...")
            res = run_all_settlements(target_date)
        print("Result:", res)
    else:
        if currency.upper() == "IBIT":
            print(f"Running snapshot for IBIT with label '{action}'...")
            res = run_ibit_snapshot(label=action, auto_backup=True)
        elif currency.upper() in ("BTC", "ETH"):
            print(f"Running snapshot for {currency.upper()} with label '{action}'...")
            res = run_snapshot(label=action, currency=currency.upper(), auto_backup=True)
        else:
            print(f"Running snapshot for ALL (BTC, ETH & IBIT) with label '{action}'...")
            res_crypto = run_all_snapshots(label=action, auto_backup=False)
            try:
                res_ibit = run_ibit_snapshot(label=action, auto_backup=True)
            except Exception as e:
                res_ibit = {"status": "error", "error": str(e)}
            res = {**res_crypto, "ibit": res_ibit}
        print("Result:", res)


if __name__ == "__main__":
    main()

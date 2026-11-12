import sys
from src.collector import run_all_snapshots, run_snapshot
from src.db import init_db, init_eth_db
from src.settle import run_all_settlements, run_settlement


def main():
    init_db()
    init_eth_db()
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
        if currency.upper() in ("BTC", "ETH"):
            print(f"Running snapshot for {currency.upper()} with label '{action}'...")
            res = run_snapshot(label=action, currency=currency.upper(), auto_backup=True)
        else:
            print(f"Running snapshot for ALL (BTC & ETH) with label '{action}'...")
            res = run_all_snapshots(label=action, auto_backup=True)
        print("Result:", res)


if __name__ == "__main__":
    main()

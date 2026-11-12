import logging
import threading
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from src.collector import run_snapshot
from src.config import BKK_TZ
from src.db import get_db, log_execution
from src.settle import run_settlement

logger = logging.getLogger("scheduler")

scheduler = BackgroundScheduler(timezone=BKK_TZ)

_task_lock = threading.Lock()
_task_running = False


def check_and_run_hourly_tasks(source: str = "ping") -> dict:
    """
    Called whenever /ping is hit by cron-job.org (every 10 minutes) or on server startup.
    Guarantees:
    1. Hourly snapshot: if current hour has no snapshot, take one immediately.
    2. Daily settlement: if past 15:30 BKK and today's settlement not recorded, run it.
    3. Thread-safe and non-blocking if already running.
    """
    global _task_running
    if _task_running:
        return {"status": "skipped", "reason": "Task already in progress"}

    acquired = _task_lock.acquire(blocking=False)
    if not acquired:
        return {"status": "skipped", "reason": "Task lock could not be acquired"}

    _task_running = True
    try:
        now_bkk = datetime.now(BKK_TZ)
        today_str = now_bkk.strftime("%Y-%m-%d")
        current_hour_prefix = now_bkk.strftime("%Y-%m-%d %H:")
        actions_taken = []

        # 1. Check if snapshot exists for current hour
        with get_db() as conn:
            cur = conn.execute(
                "SELECT COUNT(*) as cnt FROM snapshots WHERE snapshot_time_bkk LIKE ?",
                (f"{current_hour_prefix}%",),
            )
            row = cur.fetchone()
            count = row["cnt"] if row else 0

        if count == 0:
            h = now_bkk.hour
            m = now_bkk.minute
            if h == 6 and m < 30:
                label = "0600"
            elif h == 15 and m >= 30:
                label = "1530"
            elif h == 21 and m < 30:
                label = "2100"
            else:
                label = f"hourly_{h:02d}00"

            logger.info(f"[{source}] No snapshot found for {current_hour_prefix}xx. Taking '{label}' snapshot...")
            try:
                run_snapshot(label=label, currency="BTC", auto_backup=False)
                actions_taken.append(f"snapshot_btc_{label}")
            except Exception as e:
                logger.error(f"[{source}] Hourly BTC snapshot failed: {e}")
                actions_taken.append(f"error_snapshot_btc_{e}")

            try:
                run_snapshot(label=label, currency="ETH", auto_backup=False)
                actions_taken.append(f"snapshot_eth_{label}")
            except Exception as e:
                logger.error(f"[{source}] Hourly ETH snapshot failed: {e}")
                actions_taken.append(f"error_snapshot_eth_{e}")

            try:
                from src.gdrive_sync import upload_db_to_gdrive
                upload_db_to_gdrive()
            except Exception as g_err:
                logger.warning(f"Google Drive sync warning: {g_err}")

        # 2. Check daily settlement (if >= 15:30 BKK)
        if now_bkk.hour > 15 or (now_bkk.hour == 15 and now_bkk.minute >= 30):
            with get_db() as conn:
                cur = conn.execute(
                    "SELECT COUNT(*) as cnt FROM expiry_results WHERE expiry_date = ?",
                    (today_str,),
                )
                row = cur.fetchone()
                settled_count = row["cnt"] if row else 0

            if settled_count == 0:
                logger.info(f"[{source}] Missing daily settlement for {today_str}. Running settlement...")
                try:
                    run_settlement(today_str, currency="BTC")
                    actions_taken.append("settlement_btc")
                    try:
                        from src.paper_trade import open_active_paper_trades
                        open_active_paper_trades()
                    except Exception as p_err:
                        logger.warning(f"Paper trade check warning: {p_err}")
                except Exception as e:
                    logger.error(f"[{source}] Daily BTC settlement failed: {e}")
                    actions_taken.append(f"error_settlement_btc_{e}")

                try:
                    run_settlement(today_str, currency="ETH")
                    actions_taken.append("settlement_eth")
                except Exception as e:
                    logger.error(f"[{source}] Daily ETH settlement failed: {e}")
                    actions_taken.append(f"error_settlement_eth_{e}")

                try:
                    from src.gdrive_sync import upload_db_to_gdrive
                    upload_db_to_gdrive(create_archive=True)
                except Exception as g_err:
                    logger.warning(f"Google Drive sync warning: {g_err}")

        return {"status": "ok", "actions": actions_taken}
    finally:
        _task_running = False
        _task_lock.release()


def job_0600():
    logger.info("Executing 06:00 scheduled snapshot for BTC & ETH (today's expiry)...")
    try:
        run_snapshot(label="0600", currency="BTC", auto_backup=False)
    except Exception as e:
        logger.error(f"Error in BTC 06:00 job: {e}")
    try:
        run_snapshot(label="0600", currency="ETH", auto_backup=False)
    except Exception as e:
        logger.error(f"Error in ETH 06:00 job: {e}")
    try:
        from src.gdrive_sync import upload_db_to_gdrive
        upload_db_to_gdrive()
    except Exception as e:
        logger.error(f"Google Drive sync error in 06:00 job: {e}")


def job_1530():
    logger.info("Executing 15:30 scheduled settlement & snapshot for BTC & ETH (tomorrow's expiry)...")
    ref_time_str = datetime.now(BKK_TZ).strftime("%Y-%m-%d %H:%M:%S")
    # 1. Settle today's expiry
    try:
        run_settlement(currency="BTC")
    except Exception as e:
        logger.error(f"Error in BTC 15:30 settlement: {e}")
        log_execution(ref_time_str, "1530", "settle", "ERROR", str(e))
    try:
        run_settlement(currency="ETH")
    except Exception as e:
        logger.error(f"Error in ETH 15:30 settlement: {e}")

    # 2. Snapshot tomorrow's expiry
    try:
        run_snapshot(label="1530", currency="BTC", auto_backup=False)
    except Exception as e:
        logger.error(f"Error in BTC 15:30 snapshot: {e}")
        log_execution(ref_time_str, "1530", "snapshot", "ERROR", str(e))
    try:
        run_snapshot(label="1530", currency="ETH", auto_backup=False)
    except Exception as e:
        logger.error(f"Error in ETH 15:30 snapshot: {e}")

    # 3. Upload all to Google Drive with archive
    try:
        from src.gdrive_sync import upload_db_to_gdrive
        upload_db_to_gdrive(create_archive=True)
    except Exception as e:
        logger.error(f"Google Drive archive upload error in 15:30 job: {e}")


def job_2100():
    logger.info("Executing 21:00 scheduled snapshot for BTC & ETH (tomorrow's expiry)...")
    try:
        run_snapshot(label="2100", currency="BTC", auto_backup=False)
    except Exception as e:
        logger.error(f"Error in BTC 21:00 job: {e}")
    try:
        run_snapshot(label="2100", currency="ETH", auto_backup=False)
    except Exception as e:
        logger.error(f"Error in ETH 21:00 job: {e}")
    try:
        from src.gdrive_sync import upload_db_to_gdrive
        upload_db_to_gdrive()
    except Exception as e:
        logger.error(f"Google Drive sync error in 21:00 job: {e}")


def job_hourly():
    now_bkk = datetime.now(BKK_TZ)
    hour = now_bkk.hour
    minute = now_bkk.minute

    # If it's close to 06:00, 15:30, or 21:00, the dedicated jobs will handle it
    if hour == 6 and minute < 10:
        return
    if hour == 21 and minute < 10:
        return

    label = f"hourly_{hour:02d}00"
    logger.info(f"Executing hourly scheduled snapshot ({label}) for BTC & ETH...")
    try:
        run_snapshot(label=label, currency="BTC", auto_backup=False)
    except Exception as e:
        logger.error(f"Error in BTC hourly snapshot ({label}): {e}")
    try:
        run_snapshot(label=label, currency="ETH", auto_backup=False)
    except Exception as e:
        logger.error(f"Error in ETH hourly snapshot ({label}): {e}")
    try:
        from src.gdrive_sync import upload_db_to_gdrive
        upload_db_to_gdrive()
    except Exception as e:
        logger.error(f"Google Drive sync error in hourly snapshot ({label}): {e}")


def init_scheduler():
    if not scheduler.running:
        # Milestone jobs with 1-hour misfire grace time
        scheduler.add_job(job_0600, "cron", hour=6, minute=0, id="job_0600", replace_existing=True, misfire_grace_time=3600)
        scheduler.add_job(job_1530, "cron", hour=15, minute=30, id="job_1530", replace_existing=True, misfire_grace_time=3600)
        scheduler.add_job(job_2100, "cron", hour=21, minute=0, id="job_2100", replace_existing=True, misfire_grace_time=3600)
        # Hourly job at minute 0 of every hour
        scheduler.add_job(job_hourly, "cron", minute=0, id="job_hourly", replace_existing=True, misfire_grace_time=3600)
        scheduler.start()
        logger.info("APScheduler started with hourly snapshots + milestone jobs (06:00, 15:30, 21:00 Asia/Bangkok).")


def trigger_manual(action: str = "snapshot", currency: str = "ALL") -> dict:
    """Manually trigger either a snapshot or settlement right now (for BTC, ETH, or ALL)."""
    target_currencies = ["BTC", "ETH"] if currency.upper() == "ALL" else [currency.upper()]
    results = {}

    if action == "settle":
        for curr in target_currencies:
            try:
                results[curr] = run_settlement(currency=curr)
            except Exception as e:
                results[curr] = {"status": "error", "error": str(e)}
        try:
            from src.gdrive_sync import upload_db_to_gdrive
            upload_db_to_gdrive(create_archive=True)
        except Exception as e:
            logger.warning(f"Google Drive sync warning: {e}")
        return {"action": "settle", "results": results}
    else:
        now_bkk = datetime.now(BKK_TZ)
        label = f"manual_{now_bkk.strftime('%H%M')}"
        for curr in target_currencies:
            try:
                results[curr] = run_snapshot(label=label, currency=curr, auto_backup=False)
            except Exception as e:
                results[curr] = {"status": "error", "error": str(e)}
        try:
            from src.gdrive_sync import upload_db_to_gdrive
            upload_db_to_gdrive()
        except Exception as e:
            logger.warning(f"Google Drive sync warning: {e}")
        return {"action": "snapshot", "label": label, "results": results}

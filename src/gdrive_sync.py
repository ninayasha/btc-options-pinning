"""
Google Drive Sync Bridge Module.
Delegates to src.gdrive_backup for robust backup/restore operations.
"""
from typing import Optional
from src.gdrive_backup import (
    backup_database,
    backup_all_databases,
    restore_database_if_missing,
    restore_all_databases_if_missing,
    get_access_token,
    ensure_backup_folder,
)


def upload_db_to_gdrive(create_archive: bool = False) -> bool:
    """Uploads/updates all master databases (BTC & ETH) and snapshot archive to Google Drive."""
    res = backup_all_databases(create_archive=create_archive)
    return bool(res.get("success", False))


def download_db_from_gdrive(force: bool = False) -> bool:
    """Downloads master databases from Google Drive."""
    res = restore_all_databases_if_missing(force=force)
    btc_ok = res.get("btc", {}).get("restored", False)
    eth_ok = res.get("eth", {}).get("restored", False)
    return bool(btc_ok or eth_ok)

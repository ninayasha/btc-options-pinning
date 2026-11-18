import json
import logging
import math
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
import httpx

from src.config import BKK_TZ, CBOE_IBIT_URL, IBIT_DB_PATH, RAW_DIR
from src.db import get_db, init_ibit_db, log_execution
from src.options_math import (
    bs_delta,
    bs_gamma,
    calculate_gamma_flip,
    calculate_gex_per_strike,
    calculate_max_pain,
    calculate_vol_metrics,
    classify_expiry,
    get_top_strikes,
)

logger = logging.getLogger("ibit_collector")

OCC_PATTERN = re.compile(r"^IBIT(\d{2})(\d{2})(\d{2})([CP])(\d{8})$")


def fetch_cboe_ibit_options(max_retries: int = 3, timeout: float = 20.0) -> Dict[str, Any]:
    """Fetch current IBIT options chain from Cboe delayed quotes API."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
    }
    delay = 1.5
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            with httpx.Client(follow_redirects=True, timeout=timeout, headers=headers) as client:
                r = client.get(CBOE_IBIT_URL)
                r.raise_for_status()
                payload = r.json()
                data = payload.get("data", {})
                if not data or "options" not in data:
                    raise ValueError(f"Invalid Cboe response format: {list(payload.keys())}")
                return data
        except Exception as e:
            last_error = e
            logger.warning(f"Cboe IBIT fetch attempt {attempt}/{max_retries} failed: {e}")
            if attempt < max_retries:
                time.sleep(delay)
                delay *= 2.0

    raise RuntimeError(f"Failed to fetch Cboe IBIT options after {max_retries} attempts: {last_error}")


def run_ibit_snapshot(label: str = "manual", auto_backup: bool = True) -> Dict[str, Any]:
    """
    Execute IBIT options snapshot cycle:
    1. Fetch full options chain from Cboe (3,000+ contracts across all active expiries)
    2. Parse OCC symbols (IBIT + YYMMDD + C/P + Strike)
    3. Calculate Max Pain, GEX, Gamma Flip, Strike OI distribution per expiry
    4. Save snapshots & strikes into data/ibit_pinning.db
    5. Save raw JSON dump in data/raw/
    6. Backup to Google Drive if auto_backup=True
    """
    init_ibit_db()
    ref_dt_bkk = datetime.now(BKK_TZ)
    ref_time_str = ref_dt_bkk.strftime("%Y-%m-%d %H:%M:%S")
    file_ts = ref_dt_bkk.strftime("%Y%m%d_%H%M%S")
    raw_prefix = f"ibit_{file_ts}_{label}"

    try:
        # Step 1: Fetch Cboe data
        cboe_data = fetch_cboe_ibit_options()
        spot = float(cboe_data.get("current_price", 0.0))
        if spot <= 0:
            raise ValueError(f"Invalid IBIT spot price: {spot}")

        raw_options = cboe_data.get("options", [])

        # Step 2: Parse OCC options
        # Group by expiry_date -> strike -> call/put data
        expiries_map: Dict[str, Dict[float, Dict[str, Any]]] = {}

        for item in raw_options:
            sym = item.get("option", "")
            m = OCC_PATTERN.match(sym)
            if not m:
                continue

            yy, mm, dd, cp, k_str = m.groups()
            exp_date_str = f"20{yy}-{mm}-{dd}"
            strike = float(k_str) / 1000.0
            otype = "call" if cp == "C" else "put"

            if exp_date_str not in expiries_map:
                expiries_map[exp_date_str] = {}

            if strike not in expiries_map[exp_date_str]:
                expiries_map[exp_date_str][strike] = {
                    "strike": strike,
                    "call_oi": 0.0,
                    "put_oi": 0.0,
                    "call_iv": 0.0,
                    "put_iv": 0.0,
                    "call_volume": 0.0,
                    "put_volume": 0.0,
                    "call_gamma": 0.0,
                    "put_gamma": 0.0,
                    "call_delta": 0.0,
                    "put_delta": 0.0,
                }

            oi = float(item.get("open_interest") or 0.0)
            vol = float(item.get("volume") or 0.0)
            iv = float(item.get("iv") or 0.0)
            gamma = float(item.get("gamma") or 0.0)
            delta = float(item.get("delta") or 0.0)

            st_data = expiries_map[exp_date_str][strike]
            if otype == "call":
                st_data["call_oi"] = oi
                st_data["call_volume"] = vol
                st_data["call_iv"] = iv * 100.0 if iv < 5.0 else iv  # convert to % if decimal
                st_data["call_gamma"] = gamma
                st_data["call_delta"] = delta
            else:
                st_data["put_oi"] = oi
                st_data["put_volume"] = vol
                st_data["put_iv"] = iv * 100.0 if iv < 5.0 else iv
                st_data["put_gamma"] = gamma
                st_data["put_delta"] = delta

        sorted_expiries = sorted(list(expiries_map.keys()))
        if not sorted_expiries:
            raise RuntimeError("No valid IBIT options parsed from Cboe!")

        processed_expiries = []
        primary_snap_info = {}

        with get_db(IBIT_DB_PATH) as conn:
            for exp_date_str in sorted_expiries:
                try:
                    exp_date = datetime.strptime(exp_date_str, "%Y-%m-%d").date()
                except Exception:
                    continue

                # US option expiration cutoff: ~04:00 BKK next day (16:00 EST on exp_date)
                exp_dt_bkk = datetime(exp_date.year, exp_date.month, exp_date.day, 4, 0, tzinfo=BKK_TZ) + timedelta(days=1)
                expiry_time_bkk_str = exp_dt_bkk.strftime("%Y-%m-%d %H:%M")
                hours_to_expiry = max(0.0, round((exp_dt_bkk - ref_dt_bkk).total_seconds() / 3600.0, 2))
                t_years = max(1e-6, hours_to_expiry / (24.0 * 365.0))
                expiry_type = classify_expiry(exp_date)

                strikes_dict = expiries_map[exp_date_str]
                strikes_sorted = sorted(list(strikes_dict.keys()))
                strikes_list = [strikes_dict[k] for k in strikes_sorted]

                # Options math
                max_pain = calculate_max_pain(strikes_list)
                top_strikes = get_top_strikes(strikes_list)

                strikes_gex, net_gex_total, call_gex_total, put_gex_total, max_abs_gex_strike, max_abs_gex_val = (
                    calculate_gex_per_strike(spot, strikes_list, t_years)
                )
                gamma_flip = calculate_gamma_flip(spot, strikes_list, t_years)

                spot_vs_gamma_flip = "at"
                if gamma_flip:
                    spot_vs_gamma_flip = "above" if spot > gamma_flip else "below"

                vol_metrics = calculate_vol_metrics(spot, strikes_list, t_years, dvol=None)

                total_call_oi = sum(item["call_oi"] for item in strikes_list)
                total_put_oi = sum(item["put_oi"] for item in strikes_list)
                total_oi = total_call_oi + total_put_oi
                total_oi_usd = round(total_oi * spot * 100.0)  # Standard equity options contract multiplier = 100 shares
                pc_ratio = round(total_put_oi / total_call_oi, 3) if total_call_oi > 0 else 0.0

                total_call_volume = round(sum(item.get("call_volume", 0.0) for item in strikes_list), 2)
                total_put_volume = round(sum(item.get("put_volume", 0.0) for item in strikes_list), 2)
                total_volume = round(total_call_volume + total_put_volume, 2)
                total_volume_usd = round(total_volume * spot * 100.0)
                pc_vol_ratio = round(total_put_volume / total_call_volume, 3) if total_call_volume > 0 else 0.0

                # Compare with previous snapshot
                cur_prev = conn.execute(
                    """
                    SELECT * FROM snapshots
                    WHERE expiry_date = ?
                    ORDER BY snapshot_time_bkk DESC
                    LIMIT 1
                    """,
                    (exp_date_str,),
                )
                prev_row = cur_prev.fetchone()
                prev_snap = dict(prev_row) if prev_row else None

                call_oi_chg = None
                put_oi_chg = None
                total_oi_chg = None
                top3_inc_str = ""
                top3_dec_str = ""
                prev_max_pain = None
                max_pain_moved = 0
                prev_call1_strike = None
                call1_moved = 0
                prev_put1_strike = None
                put1_moved = 0
                prev_snapshot_time_bkk = None
                prev_label = None

                if prev_snap:
                    prev_snapshot_time_bkk = prev_snap["snapshot_time_bkk"]
                    prev_label = prev_snap["label"]
                    call_oi_chg = round(total_call_oi - prev_snap["total_call_oi"], 1)
                    put_oi_chg = round(total_put_oi - prev_snap["total_put_oi"], 1)
                    total_oi_chg = round(total_oi - prev_snap["total_oi"], 1)

                    prev_max_pain = prev_snap["max_pain"]
                    max_pain_moved = 1 if prev_max_pain != max_pain else 0
                    prev_call1_strike = prev_snap["call1_strike"]
                    call1_moved = 1 if prev_call1_strike != top_strikes["call1_strike"] else 0
                    prev_put1_strike = prev_snap["put1_strike"]
                    put1_moved = 1 if prev_put1_strike != top_strikes["put1_strike"] else 0

                    cur_prev_st = conn.execute(
                        """
                        SELECT strike, call_oi, put_oi, total_oi FROM oi_by_strike
                        WHERE snapshot_time_bkk = ? AND expiry_date = ?
                        """,
                        (prev_snapshot_time_bkk, exp_date_str),
                    )
                    prev_strike_oi = {r["strike"]: dict(r) for r in cur_prev_st.fetchall()}

                    strike_diffs = []
                    for item in strikes_gex:
                        k = item["strike"]
                        p_item = prev_strike_oi.get(k, {"call_oi": 0.0, "put_oi": 0.0, "total_oi": 0.0})
                        c_chg = round(item["call_oi"] - p_item.get("call_oi", 0.0), 1)
                        p_chg = round(item["put_oi"] - p_item.get("put_oi", 0.0), 1)
                        t_chg = round((item["call_oi"] + item["put_oi"]) - p_item.get("total_oi", 0.0), 1)
                        item["call_oi_chg"] = c_chg
                        item["put_oi_chg"] = p_chg
                        item["total_oi_chg"] = t_chg
                        strike_diffs.append((k, t_chg))

                    sorted_inc = sorted([x for x in strike_diffs if x[1] > 0], key=lambda x: x[1], reverse=True)[:3]
                    sorted_dec = sorted([x for x in strike_diffs if x[1] < 0], key=lambda x: x[1])[:3]
                    top3_inc_str = ";".join([f"{k:g}:+{v}" for k, v in sorted_inc])
                    top3_dec_str = ";".join([f"{k:g}:{v}" for k, v in sorted_dec])

                top5 = sorted(strikes_list, key=lambda x: (x["call_oi"] + x["put_oi"]), reverse=True)[:5]
                top5_str = ";".join([f"{x['strike']:g}:{x['call_oi']:.0f}C/{x['put_oi']:.0f}P" for x in top5])

                # Insert into snapshots table
                snap_dict = {
                    "snapshot_time_bkk": ref_time_str,
                    "label": label,
                    "expiry_date": exp_date_str,
                    "expiry_time_bkk": expiry_time_bkk_str,
                    "hours_to_expiry": hours_to_expiry,
                    "index_price": spot,
                    "n_strikes": len(strikes_list),
                    "total_call_oi": total_call_oi,
                    "total_put_oi": total_put_oi,
                    "total_oi": total_oi,
                    "total_oi_usd": total_oi_usd,
                    "put_call_oi_ratio": pc_ratio,
                    "total_call_volume": total_call_volume,
                    "total_put_volume": total_put_volume,
                    "total_volume": total_volume,
                    "total_volume_usd": total_volume_usd,
                    "put_call_volume_ratio": pc_vol_ratio,
                    "max_pain": max_pain,
                    "price_minus_max_pain": round(spot - max_pain, 2),
                    "price_vs_max_pain_pct": round((spot - max_pain) / max_pain * 100.0, 3) if max_pain > 0 else 0.0,
                    "top_oi_strike": top_strikes["top_oi_strike"],
                    "price_minus_top_oi": round(spot - top_strikes["top_oi_strike"], 2),
                    "price_vs_top_oi_pct": round((spot - top_strikes["top_oi_strike"]) / top_strikes["top_oi_strike"] * 100.0, 3) if top_strikes["top_oi_strike"] > 0 else 0.0,
                    "top_call_strike": top_strikes["call1_strike"],
                    "top_call_oi": top_strikes["call1_oi"],
                    "top_put_strike": top_strikes["put1_strike"],
                    "top_put_oi": top_strikes["put1_oi"],
                    "call1_strike": top_strikes["call1_strike"],
                    "call1_oi": top_strikes["call1_oi"],
                    "call2_strike": top_strikes["call2_strike"],
                    "call2_oi": top_strikes["call2_oi"],
                    "put1_strike": top_strikes["put1_strike"],
                    "put1_oi": top_strikes["put1_oi"],
                    "put2_strike": top_strikes["put2_strike"],
                    "put2_oi": top_strikes["put2_oi"],
                    "top5_strikes": top5_str,
                    "raw_file": f"data/raw/{raw_prefix}.json",
                    "expiry_type": expiry_type,
                    "prev_snapshot_time_bkk": prev_snapshot_time_bkk,
                    "prev_label": prev_label,
                    "call_oi_chg": call_oi_chg,
                    "put_oi_chg": put_oi_chg,
                    "total_oi_chg": total_oi_chg,
                    "top3_oi_increase": top3_inc_str,
                    "top3_oi_decrease": top3_dec_str,
                    "prev_max_pain": prev_max_pain,
                    "max_pain_moved": max_pain_moved,
                    "prev_call1_strike": prev_call1_strike,
                    "call1_moved": call1_moved,
                    "prev_put1_strike": prev_put1_strike,
                    "put1_moved": put1_moved,
                    "net_gex_usd": round(net_gex_total),
                    "call_gex_usd": round(call_gex_total),
                    "put_gex_usd": round(put_gex_total),
                    "max_abs_gex_strike": max_abs_gex_strike,
                    "max_abs_gex_usd": round(max_abs_gex_val),
                    "gamma_flip": gamma_flip,
                    "spot_vs_gamma_flip": spot_vs_gamma_flip,
                    "gex_gamma_source": "cboe_delayed",
                    "dvol": None,
                    "atm_strike": vol_metrics["atm_strike"],
                    "atm_iv": vol_metrics["atm_iv"],
                    "atm_call_iv": vol_metrics["atm_call_iv"],
                    "atm_put_iv": vol_metrics["atm_put_iv"],
                    "call25_strike": vol_metrics["call25_strike"],
                    "call25_iv": vol_metrics["call25_iv"],
                    "put25_strike": vol_metrics["put25_strike"],
                    "put25_iv": vol_metrics["put25_iv"],
                    "skew_25d_rr": vol_metrics["skew_25d_rr"],
                }

                s_cols = ", ".join(snap_dict.keys())
                s_placeholders = ", ".join(["?"] * len(snap_dict))
                conn.execute(
                    f"INSERT OR REPLACE INTO snapshots ({s_cols}) VALUES ({s_placeholders})",
                    list(snap_dict.values()),
                )

                # Insert into oi_by_strike
                for item in strikes_gex:
                    k = item["strike"]
                    c_oi = item["call_oi"]
                    p_oi = item["put_oi"]
                    tot_oi = c_oi + p_oi
                    pct_from_spot = round((k - spot) / spot * 100.0, 2)
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO oi_by_strike (
                            snapshot_time_bkk, label, expiry_date, expiry_time_bkk, index_price,
                            strike, call_oi, put_oi, total_oi, call_oi_usd, put_oi_usd, total_oi_usd,
                            call_volume_24h, put_volume_24h, pct_from_spot, prev_snapshot_time_bkk,
                            call_oi_chg, put_oi_chg, total_oi_chg, call_iv, put_iv,
                            call_delta, put_delta, call_gamma, put_gamma,
                            call_gex_usd, put_gex_usd, net_gex_usd
                        ) VALUES (
                            ?, ?, ?, ?, ?,
                            ?, ?, ?, ?, ?, ?, ?,
                            ?, ?, ?, ?,
                            ?, ?, ?, ?, ?,
                            ?, ?, ?, ?,
                            ?, ?, ?
                        )
                        """,
                        (
                            ref_time_str, label, exp_date_str, expiry_time_bkk_str, spot,
                            k, c_oi, p_oi, tot_oi, round(c_oi * spot * 100), round(p_oi * spot * 100), round(tot_oi * spot * 100),
                            item.get("call_volume", 0.0), item.get("put_volume", 0.0), pct_from_spot, prev_snapshot_time_bkk,
                            item.get("call_oi_chg"), item.get("put_oi_chg"), item.get("total_oi_chg"),
                            item.get("call_iv"), item.get("put_iv"),
                            item.get("call_delta"), item.get("put_delta"),
                            item.get("call_gamma"), item.get("put_gamma"),
                            round(item.get("call_gex_usd", 0.0)), round(item.get("put_gex_usd", 0.0)), round(item.get("net_gex_usd", 0.0)),
                        ),
                    )

                processed_expiries.append(exp_date_str)
                if not primary_snap_info:
                    primary_snap_info = {
                        "target_date": exp_date_str,
                        "spot": spot,
                        "max_pain": max_pain,
                        "total_oi": total_oi,
                        "net_gex_usd": round(net_gex_total),
                    }

            conn.commit()

        # Step 4: Save raw JSON dump
        raw_filename = f"{raw_prefix}_all_expiries.json"
        raw_filepath = RAW_DIR / raw_filename
        raw_dump = {
            "snapshot_time_bkk": ref_dt_bkk.isoformat(),
            "currency": "IBIT",
            "label": label,
            "spot": spot,
            "expiries_processed": processed_expiries,
            "contracts_count": len(raw_options),
        }
        with open(raw_filepath, "w", encoding="utf-8") as f:
            json.dump(raw_dump, f)

        # Step 5: Log execution
        log_execution(
            run_time_bkk=ref_time_str,
            label=label,
            action="snapshot",
            status="SUCCESS",
            message=f"[IBIT] Processed ALL {len(processed_expiries)} active expiries. Spot: {spot:.2f}, Total contracts: {len(raw_options)}",
            fallback_used=0,
            db_path=IBIT_DB_PATH,
        )

        # Step 6: Auto-backup database to Google Drive
        if auto_backup:
            try:
                from src.gdrive_backup import backup_database
                backup_database(IBIT_DB_PATH, create_archive=False)
            except Exception as e:
                logger.warning(f"Google Drive auto-backup error for IBIT: {e}")

        return {
            "status": "success",
            "currency": "IBIT",
            "snapshot_time_bkk": ref_time_str,
            "expiries_count": len(processed_expiries),
            "expiries": processed_expiries,
            "primary": primary_snap_info,
        }

    except Exception as e:
        logger.error(f"IBIT Snapshot failed: {e}", exc_info=True)
        log_execution(
            run_time_bkk=ref_time_str,
            label=label,
            action="snapshot",
            status="ERROR",
            message=f"[IBIT] {e}",
            fallback_used=0,
            db_path=IBIT_DB_PATH,
        )
        raise e

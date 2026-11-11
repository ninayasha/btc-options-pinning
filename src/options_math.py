import math
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

SQRT_2PI = math.sqrt(2.0 * math.pi)


def norm_pdf(x: float) -> float:
    """Standard normal probability density function."""
    return math.exp(-0.5 * x * x) / SQRT_2PI


def norm_cdf(x: float) -> float:
    """Standard normal cumulative distribution function."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def classify_expiry(expiry_dt: date) -> str:
    """
    Classify expiry type:
    - daily: non-Friday
    - weekly: Friday, but not last Friday of month
    - monthly: last Friday of month (months other than 3, 6, 9, 12)
    - quarterly: last Friday of March, June, September, December
    """
    if expiry_dt.weekday() != 4:  # Monday=0, Friday=4
        return "daily"

    # Check if last Friday of month: adding 7 days changes the month
    month = expiry_dt.month
    day = expiry_dt.day
    # If day + 7 exceeds month length, or month of day+7 is different
    # Easiest check: check if adding 7 days results in month != expiry_dt.month
    try:
        next_week = date(expiry_dt.year, expiry_dt.month, day + 7)
        is_last_friday = False
    except ValueError:
        is_last_friday = True

    if is_last_friday:
        if month in (3, 6, 9, 12):
            return "quarterly"
        return "monthly"
    return "weekly"


def bs_gamma(spot: float, strike: float, t_years: float, iv_decimal: float, r: float = 0.0) -> float:
    """
    Calculate Black-Scholes gamma.
    Gamma = n(d1) / (S * sigma * sqrt(T))
    Safe against zero or negative values.
    """
    if spot <= 0.0 or strike <= 0.0 or t_years <= 1e-7 or iv_decimal <= 1e-4:
        return 0.0

    try:
        sigma_sqrt_t = iv_decimal * math.sqrt(t_years)
        if sigma_sqrt_t <= 0.0:
            return 0.0
        d1 = (math.log(spot / strike) + (r + 0.5 * iv_decimal * iv_decimal) * t_years) / sigma_sqrt_t
        return norm_pdf(d1) / (spot * sigma_sqrt_t)
    except (ValueError, OverflowError, ZeroDivisionError):
        return 0.0


def bs_delta(spot: float, strike: float, t_years: float, iv_decimal: float, is_call: bool, r: float = 0.0) -> float:
    """
    Calculate Black-Scholes delta.
    Call delta = N(d1), Put delta = N(d1) - 1
    """
    if spot <= 0.0 or strike <= 0.0 or t_years <= 1e-7 or iv_decimal <= 1e-4:
        if is_call:
            return 1.0 if spot >= strike else 0.0
        else:
            return 0.0 if spot >= strike else -1.0

    try:
        sigma_sqrt_t = iv_decimal * math.sqrt(t_years)
        d1 = (math.log(spot / strike) + (r + 0.5 * iv_decimal * iv_decimal) * t_years) / sigma_sqrt_t
        c_delta = norm_cdf(d1)
        return c_delta if is_call else (c_delta - 1.0)
    except (ValueError, OverflowError, ZeroDivisionError):
        return 0.0


def bs_price(spot: float, strike: float, t_years: float, iv_decimal: float, is_call: bool, r: float = 0.0) -> float:
    """
    Calculate Black-Scholes option price in USD.
    Call = S * N(d1) - K * exp(-r*T) * N(d2)
    Put = K * exp(-r*T) * N(-d2) - S * N(-d1)
    """
    if spot <= 0.0 or strike <= 0.0:
        return 0.0
    if t_years <= 1e-7 or iv_decimal <= 1e-4:
        if is_call:
            return max(0.0, spot - strike)
        else:
            return max(0.0, strike - spot)

    try:
        sigma_sqrt_t = iv_decimal * math.sqrt(t_years)
        d1 = (math.log(spot / strike) + (r + 0.5 * iv_decimal * iv_decimal) * t_years) / sigma_sqrt_t
        d2 = d1 - sigma_sqrt_t
        discount = math.exp(-r * t_years)

        if is_call:
            price = spot * norm_cdf(d1) - strike * discount * norm_cdf(d2)
        else:
            price = strike * discount * norm_cdf(-d2) - spot * norm_cdf(-d1)

        return max(0.0, price)
    except (ValueError, OverflowError, ZeroDivisionError):
        return max(0.0, spot - strike) if is_call else max(0.0, strike - spot)


def calculate_max_pain(strikes_oi: List[Dict[str, float]]) -> float:
    """
    Calculate Max Pain strike in O(N log N) / O(N) using running prefix sums.
    Loss to option buyers at price S:
    Loss(S) = sum_i(call_oi_i * max(0, S - K_i)) + sum_i(put_oi_i * max(0, K_i - S))
    Max pain is S in {K_i} that minimizes total payout / buyer loss.
    """
    if not strikes_oi:
        return 0.0

    sorted_items = sorted(strikes_oi, key=lambda x: x["strike"])
    n = len(sorted_items)
    if n == 1:
        return sorted_items[0]["strike"]

    strikes = [x["strike"] for x in sorted_items]
    call_ois = [float(x.get("call_oi", 0.0) or 0.0) for x in sorted_items]
    put_ois = [float(x.get("put_oi", 0.0) or 0.0) for x in sorted_items]

    # Initial loss at candidate S = strikes[0]
    s0 = strikes[0]
    cur_loss = sum(put_ois[i] * (strikes[i] - s0) for i in range(n))
    min_loss = cur_loss
    best_strike = s0

    cum_call = 0.0
    rem_put = sum(put_ois)

    for i in range(1, n):
        delta = strikes[i] - strikes[i - 1]
        cum_call += call_ois[i - 1]
        rem_put -= put_ois[i - 1]
        cur_loss += delta * (cum_call - rem_put)
        if cur_loss < min_loss:
            min_loss = cur_loss
            best_strike = strikes[i]

    return best_strike


def get_top_strikes(strikes_oi: List[Dict[str, float]]) -> Dict[str, any]:
    """
    Extract:
    - call1_strike, call1_oi, call2_strike, call2_oi
    - put1_strike, put1_oi, put2_strike, put2_oi
    - top_oi_strike, top_oi
    """
    sorted_calls = sorted(strikes_oi, key=lambda x: x.get("call_oi", 0.0), reverse=True)
    sorted_puts = sorted(strikes_oi, key=lambda x: x.get("put_oi", 0.0), reverse=True)
    sorted_total = sorted(strikes_oi, key=lambda x: (x.get("call_oi", 0.0) + x.get("put_oi", 0.0)), reverse=True)

    c1 = sorted_calls[0] if len(sorted_calls) > 0 else {"strike": 0.0, "call_oi": 0.0}
    c2 = sorted_calls[1] if len(sorted_calls) > 1 else {"strike": 0.0, "call_oi": 0.0}

    p1 = sorted_puts[0] if len(sorted_puts) > 0 else {"strike": 0.0, "put_oi": 0.0}
    p2 = sorted_puts[1] if len(sorted_puts) > 1 else {"strike": 0.0, "put_oi": 0.0}

    t1 = sorted_total[0] if len(sorted_total) > 0 else {"strike": 0.0, "call_oi": 0.0, "put_oi": 0.0}
    t_oi = t1.get("call_oi", 0.0) + t1.get("put_oi", 0.0)

    return {
        "call1_strike": c1["strike"],
        "call1_oi": c1.get("call_oi", 0.0),
        "call2_strike": c2["strike"],
        "call2_oi": c2.get("call_oi", 0.0),
        "put1_strike": p1["strike"],
        "put1_oi": p1.get("put_oi", 0.0),
        "put2_strike": p2["strike"],
        "put2_oi": p2.get("put_oi", 0.0),
        "top_oi_strike": t1["strike"],
        "top_oi": t_oi,
    }


def calculate_gex_per_strike(
    spot: float,
    strikes_data: List[Dict[str, float]],
    t_years: float,
) -> Tuple[List[Dict[str, float]], float, float, float, float, float]:
    """
    Calculate dealer GEX per strike.
    Dealer assumed LONG calls / SHORT puts.
    GEX_usd = gamma * OI * spot^2 * 0.01 (call +, put -)
    Returns:
    (strike_gex_list, net_gex_usd, call_gex_usd, put_gex_usd, max_abs_gex_strike, max_abs_gex_usd)
    """
    total_call_gex = 0.0
    total_put_gex = 0.0
    res_list = []

    max_abs_gex = -1.0
    max_abs_gex_strike = spot

    for item in strikes_data:
        k = item["strike"]
        c_oi = item.get("call_oi", 0.0)
        p_oi = item.get("put_oi", 0.0)

        # Gamma: prefer Deribit gamma if provided and > 0, otherwise compute via BS fallback
        gamma_c = item.get("call_gamma", 0.0)
        gamma_p = item.get("put_gamma", 0.0)

        if gamma_c <= 0.0 and "call_iv" in item and item["call_iv"] > 0:
            gamma_c = bs_gamma(spot, k, t_years, item["call_iv"] / 100.0)
        if gamma_p <= 0.0 and "put_iv" in item and item["put_iv"] > 0:
            gamma_p = bs_gamma(spot, k, t_years, item["put_iv"] / 100.0)

        # Call GEX is positive, Put GEX is negative
        # 1% spot move = spot * 0.01
        multiplier = spot * spot * 0.01
        call_gex = gamma_c * c_oi * multiplier
        put_gex = -gamma_p * p_oi * multiplier
        net_gex = call_gex + put_gex

        total_call_gex += call_gex
        total_put_gex += put_gex

        res_item = dict(item)
        res_item["call_gex_usd"] = call_gex
        res_item["put_gex_usd"] = put_gex
        res_item["net_gex_usd"] = net_gex
        res_item["call_gamma"] = gamma_c
        res_item["put_gamma"] = gamma_p
        res_list.append(res_item)

        if abs(net_gex) > max_abs_gex:
            max_abs_gex = abs(net_gex)
            max_abs_gex_strike = k

    net_gex_total = total_call_gex + total_put_gex
    return res_list, net_gex_total, total_call_gex, total_put_gex, max_abs_gex_strike, max_abs_gex


def calculate_gamma_flip(
    spot: float,
    strikes_data: List[Dict[str, float]],
    t_years: float,
) -> Optional[float]:
    """
    Gamma flip = re-price GEX total using Black-Scholes across spot +/-15% (step 0.05%),
    finding the zero crossing closest to spot.
    """
    if spot <= 0 or t_years <= 1e-7 or not strikes_data:
        return None

    # Step: 0.05% = 0.0005. Range: -15% to +15% (-0.15 to +0.15, 601 steps)
    grid_steps = 600
    p_min = -0.15
    p_max = 0.15
    step_size = (p_max - p_min) / grid_steps

    grid_spots = []
    grid_gex = []

    # Pre-filter strikes with positive OI and valid IV
    valid_strikes = []
    for item in strikes_data:
        k = item["strike"]
        c_oi = item.get("call_oi", 0.0)
        p_oi = item.get("put_oi", 0.0)
        # Use average IV of call/put or whichever is available
        c_iv = item.get("call_iv", 0.0)
        p_iv = item.get("put_iv", 0.0)
        ivs = [x for x in (c_iv, p_iv) if x > 0.0]
        avg_iv = (sum(ivs) / len(ivs)) / 100.0 if ivs else 0.50  # default 50% if unavail
        if c_oi > 0 or p_oi > 0:
            valid_strikes.append((k, c_oi, p_oi, avg_iv))

    if not valid_strikes:
        return None

    for i in range(grid_steps + 1):
        pct = p_min + i * step_size
        s_g = spot * (1.0 + pct)
        grid_spots.append(s_g)

        # Calculate net GEX at s_g
        s_g_mult = s_g * s_g * 0.01
        net_gex_sg = 0.0
        for k, c_oi, p_oi, iv in valid_strikes:
            g = bs_gamma(s_g, k, t_years, iv)
            net_gex_sg += g * (c_oi - p_oi) * s_g_mult
        grid_gex.append(net_gex_sg)

    # Find zero crossings
    crossings = []
    for i in range(len(grid_gex) - 1):
        g1 = grid_gex[i]
        g2 = grid_gex[i + 1]
        s1 = grid_spots[i]
        s2 = grid_spots[i + 1]

        if g1 == 0.0:
            crossings.append(s1)
        elif (g1 > 0 and g2 < 0) or (g1 < 0 and g2 > 0):
            # Linear interpolation for zero crossing: s = s1 - g1 * (s2 - s1) / (g2 - g1)
            denom = g2 - g1
            if denom != 0.0:
                s_zero = s1 - g1 * (s2 - s1) / denom
                crossings.append(s_zero)

    if not crossings:
        return None

    # Pick the crossing closest to current spot
    closest_flip = min(crossings, key=lambda x: abs(x - spot))
    return round(closest_flip, 2)


def calculate_vol_metrics(
    spot: float,
    strikes_data: List[Dict[str, float]],
    t_years: float,
    dvol: Optional[float] = None,
) -> Dict[str, any]:
    """
    Calculate:
    - dvol: passed in or None
    - atm_strike: strike closest to spot
    - atm_iv, atm_call_iv, atm_put_iv
    - call25_strike, call25_iv, put25_strike, put25_iv, skew_25d_rr (call25_iv - put25_iv)
    """
    if not strikes_data:
        return {
            "dvol": dvol,
            "atm_strike": spot,
            "atm_iv": None,
            "atm_call_iv": None,
            "atm_put_iv": None,
            "call25_strike": None,
            "call25_iv": None,
            "put25_strike": None,
            "put25_iv": None,
            "skew_25d_rr": None,
        }

    # ATM Strike
    atm_item = min(strikes_data, key=lambda x: abs(x["strike"] - spot))
    atm_strike = atm_item["strike"]
    atm_c_iv = atm_item.get("call_iv")
    atm_p_iv = atm_item.get("put_iv")
    atm_ivs = [x for x in (atm_c_iv, atm_p_iv) if x is not None and x > 0]
    atm_iv = round(sum(atm_ivs) / len(atm_ivs), 2) if atm_ivs else None

    # 25-delta calls and puts
    # Find call strike with delta closest to 0.25 and put strike with delta closest to -0.25
    best_c25 = None
    min_c_diff = float("inf")
    best_p25 = None
    min_p_diff = float("inf")

    for item in strikes_data:
        k = item["strike"]
        # Call delta
        c_delta = item.get("call_delta")
        c_iv = item.get("call_iv")
        if c_delta is None or c_delta == 0.0:
            if c_iv and c_iv > 0:
                c_delta = bs_delta(spot, k, t_years, c_iv / 100.0, is_call=True)

        if c_delta is not None and c_iv and c_iv > 0:
            diff = abs(c_delta - 0.25)
            if diff < min_c_diff:
                min_c_diff = diff
                best_c25 = (k, c_iv)

        # Put delta
        p_delta = item.get("put_delta")
        p_iv = item.get("put_iv")
        if p_delta is None or p_delta == 0.0:
            if p_iv and p_iv > 0:
                p_delta = bs_delta(spot, k, t_years, p_iv / 100.0, is_call=False)

        if p_delta is not None and p_iv and p_iv > 0:
            diff = abs(p_delta - (-0.25))
            if diff < min_p_diff:
                min_p_diff = diff
                best_p25 = (k, p_iv)

    call25_strike = best_c25[0] if best_c25 else None
    call25_iv = round(best_c25[1], 2) if best_c25 else None
    put25_strike = best_p25[0] if best_p25 else None
    put25_iv = round(best_p25[1], 2) if best_p25 else None

    skew_25d_rr = None
    if call25_iv is not None and put25_iv is not None:
        skew_25d_rr = round(call25_iv - put25_iv, 2)

    return {
        "dvol": dvol,
        "atm_strike": atm_strike,
        "atm_iv": atm_iv,
        "atm_call_iv": round(atm_c_iv, 2) if atm_c_iv else None,
        "atm_put_iv": round(atm_p_iv, 2) if atm_p_iv else None,
        "call25_strike": call25_strike,
        "call25_iv": call25_iv,
        "put25_strike": put25_strike,
        "put25_iv": put25_iv,
        "skew_25d_rr": skew_25d_rr,
    }


def calculate_gex_plus_matrix(
    spot: float,
    strikes_data: List[Dict[str, Any]],
    t_years: float,
    atm_iv: float,
    price_steps: int = 61,
    iv_steps: int = 31,
    price_range_pct: float = 0.20,
    iv_range_pct: float = 0.30,
) -> Dict[str, Any]:
    """
    Kingfisher GEX+ Strike-Resolved 2D Simulation Engine.
    Simulates dealer Net GEX across a 2D grid:
      - Y-axis: Spot Price scenarios [spot * (1 - price_range_pct), spot * (1 + price_range_pct)]
      - X-axis: ATM Implied Volatility scenarios [atm_iv * (1 - iv_range_pct), atm_iv * (1 + iv_range_pct)]

    Each major strike creates a localized horizontal laser band that diffuses across IV,
    with empty spaces between strikes remaining transparent.
    """
    if spot <= 0 or not strikes_data:
        return {
            "prices": [],
            "ivs": [],
            "matrix": [],
            "max_gex": 0.0,
            "min_gex": 0.0,
            "max_gex_spot": spot,
            "min_gex_spot": spot,
            "max_gex_at_atm": 0.0,
            "min_gex_at_atm": 0.0,
            "current_spot": spot,
            "current_iv": atm_iv,
            "current_net_gex": 0.0,
            "gamma_flip_spot": None,
        }

    # Normalize ATM IV
    atm_iv_pct = float(atm_iv) if (atm_iv and atm_iv > 0) else 45.0
    if atm_iv_pct <= 1.5:  # e.g. 0.45 instead of 45.0
        atm_iv_pct *= 100.0

    # Group contracts by strike price
    from collections import defaultdict
    strikes_by_k = defaultdict(list)
    total_valid_contracts = 0

    for item in strikes_data:
        k = float(item.get("strike") or 0.0)
        c_oi = float(item.get("call_oi") or 0.0)
        p_oi = float(item.get("put_oi") or 0.0)
        net_oi = c_oi - p_oi
        if abs(net_oi) < 1e-4 and c_oi == 0 and p_oi == 0:
            continue

        item_t = float(item.get("t_years") or t_years or 0.01)
        if item_t <= 1e-5:
            item_t = 0.5 / 8760.0  # min 30 minutes to expiry

        # Skew ratio relative to ATM IV
        c_iv = float(item.get("call_iv") or 0.0)
        p_iv = float(item.get("put_iv") or 0.0)
        if c_iv > 0 and p_iv > 0:
            base_iv = (c_iv + p_iv) / 2.0
        else:
            base_iv = c_iv if c_iv > 0 else (p_iv if p_iv > 0 else atm_iv_pct)

        skew_ratio = max(0.4, min(2.5, base_iv / atm_iv_pct if atm_iv_pct > 0 else 1.0))
        strikes_by_k[k].append((net_oi, item_t, skew_ratio))
        total_valid_contracts += 1

    if not strikes_by_k:
        return {
            "prices": [],
            "ivs": [],
            "matrix": [],
            "max_gex": 0.0,
            "min_gex": 0.0,
            "max_gex_spot": spot,
            "min_gex_spot": spot,
            "max_gex_at_atm": 0.0,
            "min_gex_at_atm": 0.0,
            "current_spot": spot,
            "current_iv": atm_iv_pct,
            "current_net_gex": 0.0,
            "gamma_flip_spot": None,
        }

    # Generate Price Grid (Y-axis: bottom to top)
    p_min = round(spot * (1.0 - price_range_pct), -2)
    p_max = round(spot * (1.0 + price_range_pct), -2)
    p_step = (p_max - p_min) / max(1, price_steps - 1)
    prices = [round(p_min + i * p_step, 1) for i in range(price_steps)]

    # Generate IV Grid (X-axis: left to right, in percent)
    iv_min = max(5.0, round(atm_iv_pct * (1.0 - iv_range_pct), 1))
    iv_max = min(250.0, round(atm_iv_pct * (1.0 + iv_range_pct), 1))
    iv_step = (iv_max - iv_min) / max(1, iv_steps - 1)
    ivs = [round(iv_min + j * iv_step, 1) for j in range(iv_steps)]

    # 1. Precalculate GEX for each unique strike across all IVs
    strike_gex_by_iv = {}
    for k, contracts in strikes_by_k.items():
        gex_row = []
        k_mult = k * k * 0.01
        for iv in ivs:
            iv_dec = iv / 100.0
            tot_k = 0.0
            for net_oi, strike_t, skew in contracts:
                eff_iv = max(0.04, iv_dec * skew)
                denom = math.sqrt(2.0 * math.pi) * k * eff_iv * math.sqrt(strike_t)
                gamma_k = 1.0 / denom if denom > 0 else 0.0
                tot_k += net_oi * gamma_k * k_mult
            gex_row.append(tot_k)
        strike_gex_by_iv[k] = gex_row

    # 2. Build 2D Matrix with localized strike kernel (Kingfisher laser bands)
    matrix = []
    global_max_gex = -float("inf")
    global_min_gex = float("inf")

    for p in prices:
        row = []
        for iv_idx, iv in enumerate(ivs):
            w = max(250.0, 380.0 * (iv / atm_iv_pct))
            p_val = 0.0
            for k, gex_row in strike_gex_by_iv.items():
                dist = abs(p - k)
                if dist < 3.0 * w:
                    kernel = math.exp(-0.5 * (dist / w) ** 2)
                    p_val += gex_row[iv_idx] * kernel

            cell_val = round(p_val, 2)
            row.append(cell_val)
            if cell_val > global_max_gex:
                global_max_gex = cell_val
            if cell_val < global_min_gex:
                global_min_gex = cell_val
        matrix.append(row)

    # Find closest IV column to current ATM IV
    closest_iv_idx = min(range(len(ivs)), key=lambda j: abs(ivs[j] - atm_iv_pct))

    # In current IV column, find max and min GEX prices (Magnet level & Acceleration zone)
    col_at_current_iv = [matrix[p_idx][closest_iv_idx] for p_idx in range(len(prices))]
    max_p_idx = max(range(len(prices)), key=lambda p: col_at_current_iv[p])
    min_p_idx = min(range(len(prices)), key=lambda p: col_at_current_iv[p])
    max_gex_spot = prices[max_p_idx]
    min_gex_spot = prices[min_p_idx]

    # Current Net GEX at exact spot and ATM IV
    curr_mult = spot * spot * 0.01
    curr_iv_dec = atm_iv_pct / 100.0
    current_net_gex = 0.0
    for k, contracts in strikes_by_k.items():
        for net_oi, strike_t, skew in contracts:
            gamma = bs_gamma(spot, k, strike_t, max(0.04, curr_iv_dec * skew))
            current_net_gex += net_oi * gamma * curr_mult
    current_net_gex = round(current_net_gex, 2)

    # Find Gamma Flip at current IV (zero crossing)
    gamma_flip_spot = None
    for p_idx in range(len(prices) - 1):
        g1 = col_at_current_iv[p_idx]
        g2 = col_at_current_iv[p_idx + 1]
        p1 = prices[p_idx]
        p2 = prices[p_idx + 1]
        if g1 == 0:
            gamma_flip_spot = p1
            break
        elif (g1 > 0 and g2 < 0) or (g1 < 0 and g2 > 0):
            denom = g2 - g1
            if denom != 0:
                gamma_flip_spot = round(p1 - g1 * (p2 - p1) / denom, 1)
            break

    return {
        "prices": prices,
        "ivs": ivs,
        "matrix": matrix,
        "max_gex": global_max_gex,
        "min_gex": global_min_gex,
        "max_gex_spot": max_gex_spot,
        "min_gex_spot": min_gex_spot,
        "max_gex_at_atm": col_at_current_iv[max_p_idx],
        "min_gex_at_atm": col_at_current_iv[min_p_idx],
        "current_spot": spot,
        "current_iv": round(atm_iv_pct, 2),
        "current_net_gex": current_net_gex,
        "gamma_flip_spot": gamma_flip_spot,
    }


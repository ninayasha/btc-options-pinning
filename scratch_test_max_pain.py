import time

# O(N^2) original
def max_pain_slow(strikes_oi):
    strikes = [item["strike"] for item in strikes_oi]
    min_loss = float("inf")
    max_pain_strike = strikes[0]
    for candidate in strikes:
        total_loss = 0.0
        for item in strikes_oi:
            k = item["strike"]
            c_oi = item.get("call_oi", 0.0)
            p_oi = item.get("put_oi", 0.0)
            if candidate > k:
                total_loss += c_oi * (candidate - k)
            elif candidate < k:
                total_loss += p_oi * (k - candidate)
        if total_loss < min_loss:
            min_loss = total_loss
            max_pain_strike = candidate
    return max_pain_strike

# O(N) fast
def max_pain_fast(strikes_oi):
    if not strikes_oi:
        return 0.0
    sorted_items = sorted(strikes_oi, key=lambda x: x["strike"])
    n = len(sorted_items)
    if n == 1:
        return sorted_items[0]["strike"]
    
    strikes = [x["strike"] for x in sorted_items]
    call_ois = [x.get("call_oi", 0.0) or 0.0 for x in sorted_items]
    put_ois = [x.get("put_oi", 0.0) or 0.0 for x in sorted_items]
    
    # Compute initial loss at strikes[0]
    # S = strikes[0]: all calls pay 0 (candidate <= k for all k >= strikes[0]).
    # puts pay put_oi * (k - strikes[0])
    s0 = strikes[0]
    cur_loss = sum(put_ois[i] * (strikes[i] - s0) for i in range(n))
    min_loss = cur_loss
    best_strike = s0
    
    # Prefix call OI and Suffix put OI
    # When moving from strikes[i-1] to strikes[i]:
    # delta = strikes[i] - strikes[i-1]
    # Calls below strikes[i] increase loss by delta * sum(call_ois[0..i-1])
    # Puts at or above strikes[i] decrease loss by delta * sum(put_ois[i..n-1])
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

# Test correctness and speed
import random
dummy_data = [{"strike": 50000 + i*1000, "call_oi": random.uniform(10, 500), "put_oi": random.uniform(10, 500)} for i in range(80)]

res_slow = max_pain_slow(dummy_data)
res_fast = max_pain_fast(dummy_data)
print("Correctness match:", res_slow == res_fast, f"(slow: {res_slow}, fast: {res_fast})")

# Speed comparison on 218 snapshots
t0 = time.time()
for _ in range(218):
    max_pain_slow(dummy_data)
t_slow = time.time() - t0

t0 = time.time()
for _ in range(218):
    max_pain_fast(dummy_data)
t_fast = time.time() - t0

print(f"Slow (218 runs): {t_slow:.4f}s | Fast (218 runs): {t_fast:.4f}s | Speedup: {t_slow / t_fast:.1f}x")

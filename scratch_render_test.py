import httpx, time

urls = [
    "https://btc-options-pinning.onrender.com/api/timeline?scope=active&expiry_date=group_today",
    "https://btc-options-pinning.onrender.com/api/timeline?scope=active&expiry_date=group_weekly",
    "https://btc-options-pinning.onrender.com/api/timeline?scope=active&expiry_date=all",
]

for url in urls:
    t0 = time.time()
    try:
        r = httpx.get(url, timeout=30)
        dur = time.time() - t0
        print(f"{url.split('=')[-1]}: status={r.status_code}, time={dur:.2f}s, size={len(r.content)/1024/1024:.2f}MB")
    except Exception as e:
        print(f"Error {url}: {e}")

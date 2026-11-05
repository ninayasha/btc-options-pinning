import gzip, json, sys
sys.path.append(r'C:\Users\Noname\.gemini\antigravity\scratch\btc-pinning-dashboard')
from web.app import api_timeline

res = api_timeline('all', 'active')
for s in res['snapshots']:
    trimmed = []
    for st in s['strikes']:
        trimmed.append({
            'strike': st['strike'],
            'call_oi': st['call_oi'],
            'put_oi': st['put_oi'],
            'call_volume_24h': st.get('call_volume_24h', 0.0),
            'put_volume_24h': st.get('put_volume_24h', 0.0),
            'call_gex_usd': st.get('call_gex_usd', 0.0),
            'put_gex_usd': st.get('put_gex_usd', 0.0),
            'net_gex_usd': st.get('net_gex_usd', 0.0),
            'call_iv': st.get('call_iv'),
            'put_iv': st.get('put_iv')
        })
    s['strikes'] = trimmed

raw_bytes = json.dumps(res).encode('utf-8')
gz_bytes = gzip.compress(raw_bytes)

print(f"Trimmed uncompressed: {len(raw_bytes)/1024/1024:.2f} MB")
print(f"Trimmed Gzip:         {len(gz_bytes)/1024:.1f} KB")

import gzip, json, sys
sys.path.append(r'C:\Users\Noname\.gemini\antigravity\scratch\btc-pinning-dashboard')
from web.app import api_timeline

res = api_timeline('all', 'active')
raw_bytes = json.dumps(res).encode('utf-8')
gz_bytes = gzip.compress(raw_bytes)

print(f"Raw uncompressed: {len(raw_bytes)/1024/1024:.2f} MB")
print(f"Gzip compressed:   {len(gz_bytes)/1024:.1f} KB")
print(f"Reduction ratio:   {(1 - len(gz_bytes)/len(raw_bytes))*100:.1f}%")

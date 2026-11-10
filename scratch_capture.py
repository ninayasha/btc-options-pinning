import socket, base64, os, json

def cdp_send(ws_url, method, params=None):
    host = '127.0.0.1'
    port = 9222
    path = ws_url.split(':9222')[1]
    s = socket.socket()
    s.connect((host, port))
    key = base64.b64encode(os.urandom(16)).decode()
    req = (f'GET {path} HTTP/1.1\r\n'
           f'Host: {host}:{port}\r\n'
           f'Upgrade: websocket\r\n'
           f'Connection: Upgrade\r\n'
           f'Sec-WebSocket-Key: {key}\r\n'
           f'Sec-WebSocket-Version: 13\r\n\r\n')
    s.sendall(req.encode())
    s.recv(4096)
    
    msg = json.dumps({'id': 1, 'method': method, 'params': params or {}})
    data = msg.encode('utf-8')
    frame = bytearray([0x81])
    mask = os.urandom(4)
    if len(data) < 126:
        frame.append(0x80 | len(data))
    elif len(data) < 65536:
        frame.append(0x80 | 126)
        frame.extend(len(data).to_bytes(2, 'big'))
    else:
        frame.append(0x80 | 127)
        frame.extend(len(data).to_bytes(8, 'big'))
    frame.extend(mask)
    for i, b in enumerate(data):
        frame.append(b ^ mask[i % 4])
    s.sendall(frame)
    
    chunks = []
    while True:
        chunk = s.recv(131072)
        if not chunk:
            break
        chunks.append(chunk)
        combined = b''.join(chunks)
        if b'"result":' in combined and combined.rstrip().endswith(b'}'):
            break
        if len(combined) > 10000000:
            break
    s.close()
    
    raw = b''.join(chunks)
    # find start of JSON
    json_start = raw.find(b'{"id":1')
    json_end = raw.rfind(b'}') + 1
    payload = raw[json_start:json_end].decode('utf-8', errors='replace')
    return json.loads(payload)

ws_url = 'ws://127.0.0.1:9222/devtools/page/F9744ACB4EF42EB2B76CA57D358F1C62'
res = cdp_send(ws_url, 'Page.captureScreenshot', {'format': 'png'})
img_b64 = res['result']['data']
out_path = 'C:/Users/Noname/.gemini/antigravity/brain/1d719071-464e-410b-83a6-22220fac00ff/verified_screenshot.png'
with open(out_path, 'wb') as f:
    f.write(base64.b64decode(img_b64))
print('Screenshot saved to:', out_path, 'Bytes:', len(img_b64))

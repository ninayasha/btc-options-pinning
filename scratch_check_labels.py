import socket, base64, os, json

def cdp_eval(ws_url, expr):
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
    msg = json.dumps({'id': 1, 'method': 'Runtime.evaluate', 'params': {'expression': expr, 'returnByValue': True}})
    data = msg.encode('utf-8')
    frame = bytearray([0x81])
    mask = os.urandom(4)
    if len(data) < 126:
        frame.append(0x80 | len(data))
    else:
        frame.append(0x80 | 126)
        frame.extend(len(data).to_bytes(2, 'big'))
    frame.extend(mask)
    for i, b in enumerate(data):
        frame.append(b ^ mask[i % 4])
    s.sendall(frame)
    resp_data = s.recv(65536)
    s.close()
    
    raw = resp_data
    json_start = raw.find(b'{"id":1')
    json_end = raw.rfind(b'}') + 1
    payload = raw[json_start:json_end].decode('utf-8', errors='replace')
    return json.loads(payload)

ws_url = 'ws://127.0.0.1:9222/devtools/page/F9744ACB4EF42EB2B76CA57D358F1C62'
res = cdp_eval(ws_url, 'JSON.stringify({target: currentTargetKey, totalLabels: chartOI ? chartOI.data.labels.length : 0, first: chartOI ? chartOI.data.labels[0] : null, last: chartOI ? chartOI.data.labels[chartOI.data.labels.length - 1] : null})')
print('Result:', res['result']['result']['value'])

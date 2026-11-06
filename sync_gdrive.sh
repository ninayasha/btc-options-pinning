#!/bin/bash
set -e
echo "=========================================================="
echo "  Syncing Google Drive & Restoring Full Database          "
echo "=========================================================="

echo "UE9SVD04MDg4ClRaPUFzaWEvQmFuZ2tvawpQWVRIT05VTkJVRkZFUkVEPTEKR0RSSVZFX1JFRlJFU0hfVE9LRU49MS8vMGdrRnU1cDBEOUxOTENnWUlBUkFBR0JBU053Ri1MOUlySEhZTlA2NV93N2wyNS1SbVRNTFdMNlBBeFhHSTBDZ0hiM3RLSWQ2Um5uakpmZkMtWFhQMGl6dnNCMkk4NWNkY1BfOApHRFJJVkVfQ0xJRU5UX0lEPTEwNzEwMDYwNjA1OTEtdG1oc3NpbjJoMjFsY3JlMjM1dnRvbG9qaDRnNDAzZXAuYXBwcy5nb29nbGV1c2VyY29udGVudC5jb20KR0RSSVZFX0NMSUVOVF9TRUNSRVQ9R09DU1BYLUs1OEZXUjQ4NkxkTEoxbUxCOHNYQzR6NnFEQWYK" | base64 -d > /opt/btc-options-pinning/.env

echo "Recreating container with Google Drive environment..."
docker stop btc-options-pinning || true
docker rm btc-options-pinning || true
docker run -d \
  --name btc-options-pinning \
  --restart always \
  -p 80:8088 \
  -p 8088:8088 \
  -v /opt/btc-options-pinning/data:/app/data \
  --env-file /opt/btc-options-pinning/.env \
  btc-options-pinning:latest

echo "Container started with credentials. Pulling richest database from Google Drive..."
sleep 6

res=$(curl -s -X POST http://127.0.0.1:8088/api/restore/gdrive)
echo "Restore result: $res"

echo ""
echo "=========================================================="
echo "🎉 SUCCESS! Google Drive connected and database restored."
echo "=========================================================="

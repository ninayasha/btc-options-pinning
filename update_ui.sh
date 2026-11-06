#!/bin/bash
set -e
echo "Updating btc-options-pinning UI on AWS EC2..."
cd /opt/btc-options-pinning
git fetch origin main
git reset --hard origin/main

docker stop btc-options-pinning || true
docker rm btc-options-pinning || true
docker build -t btc-options-pinning:latest .

docker run -d \
  --name btc-options-pinning \
  --restart always \
  -p 80:8088 \
  -p 8088:8088 \
  -v /opt/btc-options-pinning/data:/app/data \
  -v /opt/btc-options-pinning/web:/app/web \
  --env-file /opt/btc-options-pinning/.env \
  btc-options-pinning:latest

echo "=========================================================="
echo "🎉 UI updated successfully! Check http://13.211.177.162"
echo "=========================================================="

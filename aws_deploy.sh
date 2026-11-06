#!/bin/bash
set -e

exec > /var/log/aws_deploy.log 2>&1
echo "=========================================================="
echo "  AWS EC2 1-Click Deploy: BTC Options Pinning            "
echo "=========================================================="

# 1. Update system and install Docker & Git
echo "📦 [1/4] Updating packages and installing Docker..."
apt-get update -y
apt-get install -y git curl wget jq iptables docker.io

systemctl enable docker
systemctl start docker

# 2. Clone or pull latest repository
APP_DIR="/opt/btc-options-pinning"
echo "📂 [2/4] Setting up project directory at $APP_DIR..."

if [ -d "$APP_DIR" ]; then
    echo "Updating existing repository..."
    cd "$APP_DIR"
    git fetch origin main
    git reset --hard origin/main
else
    echo "Cloning repository..."
    git clone https://github.com/ninayasha/btc-options-pinning.git "$APP_DIR"
    cd "$APP_DIR"
fi

# 3. Setup Environment
echo "⚙️ [3/4] Setting up environment variables..."
cat << 'EOF' > "$APP_DIR/.env"
PORT=8088
TZ=Asia/Bangkok
PYTHONUNBUFFERED=1
EOF

# 4. Build and run Docker container with Auto-Restart
# Map BOTH port 80 (standard HTTP) and port 8088
echo "🚀 [4/4] Building and launching btc-options-pinning container..."
docker stop btc-options-pinning 2>/dev/null || true
docker rm btc-options-pinning 2>/dev/null || true

docker build -t btc-options-pinning:latest .

docker run -d \
  --name btc-options-pinning \
  --restart always \
  -p 80:8088 \
  -p 8088:8088 \
  -v "$APP_DIR/data:/app/data" \
  -e PORT=8088 \
  -e TZ=Asia/Bangkok \
  btc-options-pinning:latest

# Open iptables for both ports
iptables -I INPUT 1 -p tcp --dport 80 -j ACCEPT 2>/dev/null || true
iptables -I INPUT 1 -p tcp --dport 8088 -j ACCEPT 2>/dev/null || true

# 5. Start Cloudflare Tunnel in background for HTTPS
echo "🌐 Starting Cloudflare Tunnel daemon for free HTTPS..."
if [ ! -f /usr/local/bin/cloudflared ]; then
    curl -L --output /usr/local/bin/cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
    chmod +x /usr/local/bin/cloudflared
fi

nohup /usr/local/bin/cloudflared tunnel --url http://127.0.0.1:8088 --logfile /var/log/cloudflared.log >/dev/null 2>&1 &

echo "=========================================================="
echo "🎉 DEPLOYMENT COMPLETE!"
echo "Website is accessible at: http://$(curl -s http://checkip.amazonaws.com)"
echo "Cloudflare HTTPS URL will be logged in: /var/log/cloudflared.log"
echo "=========================================================="

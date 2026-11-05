#!/bin/bash
set -e

echo "=========================================================="
echo "  Oracle Cloud 1-Click Deploy: BTC Options Pinning        "
echo "=========================================================="

# 1. Update system and install Docker & Git
echo "📦 [1/5] Updating packages and installing prerequisites..."
sudo apt-get update -y
sudo apt-get install -y git curl wget jq iptables

if ! command -v docker &> /dev/null; then
    echo "🐳 Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
fi

# 2. Clone or pull latest repository
APP_DIR="/opt/btc-options-pinning"
echo "📂 [2/5] Setting up project directory at $APP_DIR..."

if [ -d "$APP_DIR" ]; then
    echo "Updating existing repository..."
    cd "$APP_DIR"
    git fetch origin main
    git reset --hard origin/main
else
    echo "Cloning repository..."
    sudo git clone https://github.com/ninayasha/btc-options-pinning.git "$APP_DIR"
    sudo chown -R $USER:$USER "$APP_DIR"
    cd "$APP_DIR"
fi

# 3. Setup Environment
echo "⚙️ [3/5] Setting up environment variables..."
cat << 'EOF' > "$APP_DIR/.env"
PORT=8088
TZ=Asia/Bangkok
PYTHONUNBUFFERED=1
EOF

# 4. Open firewall ports (Oracle Linux / Ubuntu on OCI)
echo "🛡️ [4/5] Configuring firewall rules..."
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8088 -j ACCEPT 2>/dev/null || true
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT 2>/dev/null || true
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT 2>/dev/null || true

# 5. Build and run Docker container with Auto-Restart
echo "🚀 [5/5] Building and launching btc-options-pinning container..."
docker stop btc-options-pinning 2>/dev/null || true
docker rm btc-options-pinning 2>/dev/null || true

docker build -t btc-options-pinning:latest .

docker run -d \
  --name btc-options-pinning \
  --restart always \
  -p 8088:8088 \
  -v "$APP_DIR/data:/app/data" \
  -e PORT=8088 \
  -e TZ=Asia/Bangkok \
  btc-options-pinning:latest

echo ""
echo "=========================================================="
echo "🎉 DEPLOYMENT COMPLETE!"
echo "Status: Running on port 8088"
echo "Check logs anytime with: docker logs -f btc-options-pinning"
echo "=========================================================="

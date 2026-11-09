#!/bin/bash
set -e

DOMAIN="btc-option-pinning.duckdns.org"

echo "=========================================================="
echo "  Setting up HTTPS / SSL for $DOMAIN                     "
echo "=========================================================="

# 1. Install Caddy (Production-grade automatic HTTPS reverse proxy)
echo "📦 Installing Caddy..."
sudo apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl gnupg
curl -1sLF 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLF 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt-get update -y
sudo apt-get install -y caddy

# 2. Stop docker container binding on port 80 so Caddy can take 80 & 443
echo "⚙️ Reconfiguring Docker to expose internal port 8088..."
docker stop btc-options-pinning 2>/dev/null || true
docker rm btc-options-pinning 2>/dev/null || true

# Update auto-updater script so future updates don't conflict with Caddy port 80
cat << 'EOF' > /usr/local/bin/check_update_pinning.sh
#!/bin/bash
cd /opt/btc-options-pinning || exit 0
git fetch origin main >/dev/null 2>&1 || exit 0
LOCAL=$(git rev-parse HEAD 2>/dev/null)
REMOTE=$(git rev-parse origin/main 2>/dev/null)

if [ "$LOCAL" != "$REMOTE" ] && [ -n "$REMOTE" ]; then
    echo "[$(date)] New commit found ($REMOTE). Updating..." >> /var/log/auto_update.log
    git reset --hard origin/main >> /var/log/auto_update.log 2>&1
    docker stop btc-options-pinning 2>/dev/null || true
    docker rm btc-options-pinning 2>/dev/null || true
    docker build -t btc-options-pinning:latest . >> /var/log/auto_update.log 2>&1
    docker run -d \
      --name btc-options-pinning \
      --restart always \
      -p 127.0.0.1:8088:8088 \
      -v /opt/btc-options-pinning/data:/app/data \
      -v /opt/btc-options-pinning/web:/app/web \
      --env-file /opt/btc-options-pinning/.env \
      btc-options-pinning:latest >> /var/log/auto_update.log 2>&1
    systemctl reload caddy 2>/dev/null || true
    echo "[$(date)] Successfully updated and restarted btc-options-pinning!" >> /var/log/auto_update.log
fi
EOF
chmod +x /usr/local/bin/check_update_pinning.sh

# Run docker container on localhost:8088
cd /opt/btc-options-pinning
docker run -d \
  --name btc-options-pinning \
  --restart always \
  -p 127.0.0.1:8088:8088 \
  -v /opt/btc-options-pinning/data:/app/data \
  -v /opt/btc-options-pinning/web:/app/web \
  --env-file /opt/btc-options-pinning/.env \
  btc-options-pinning:latest

# 3. Configure Caddy with automatic Let's Encrypt SSL
echo "🔒 Configuring Caddy SSL reverse proxy..."
cat << EOF > /etc/caddy/Caddyfile
$DOMAIN {
    reverse_proxy 127.0.0.1:8088
}
EOF

sudo systemctl enable caddy
sudo systemctl restart caddy

echo "=========================================================="
echo "🎉 HTTPS SETUP COMPLETE!"
echo "Your website is now secure at: https://$DOMAIN"
echo "=========================================================="

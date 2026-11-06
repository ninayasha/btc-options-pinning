#!/bin/bash
set -e

echo "=========================================================="
echo "  Installing 100% Automatic GitHub CI/CD Auto-Updater     "
echo "=========================================================="

# 1. Create the auto-update worker script
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
      -p 80:8088 \
      -p 8088:8088 \
      -v /opt/btc-options-pinning/data:/app/data \
      -v /opt/btc-options-pinning/web:/app/web \
      --env-file /opt/btc-options-pinning/.env \
      btc-options-pinning:latest >> /var/log/auto_update.log 2>&1
    echo "[$(date)] Successfully updated and restarted btc-options-pinning!" >> /var/log/auto_update.log
fi
EOF

chmod +x /usr/local/bin/check_update_pinning.sh

# 2. Add cron job to check GitHub every 3 minutes
echo "*/3 * * * * root /usr/local/bin/check_update_pinning.sh" > /etc/cron.d/btc_auto_update
chmod 644 /etc/cron.d/btc_auto_update

# 3. Trigger immediate update right now
echo "🚀 Applying current update immediately..."
FORCE=1
cd /opt/btc-options-pinning
git fetch origin main
git reset --hard origin/main
docker stop btc-options-pinning 2>/dev/null || true
docker rm btc-options-pinning 2>/dev/null || true
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

echo ""
echo "=========================================================="
echo "🎉 AUTO-UPDATER INSTALLED SUCCESSFULLY!"
echo "From now on, whenever code is updated on GitHub,"
echo "the server will automatically update within 3 minutes."
echo "YOU NEVER NEED TO TOUCH THIS TERMINAL AGAIN!"
echo "=========================================================="

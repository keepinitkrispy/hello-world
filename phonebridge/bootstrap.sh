#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

BASE="$HOME/.phonebridge"
PUB="https://raw.githubusercontent.com/keepinitkrispy/hello-world/phone-bridge/phonebridge"
mkdir -p "$BASE" "$HOME/.termux/boot"
chmod 700 "$BASE"

say() { printf '\n\033[1;36m%s\033[0m\n' "$*"; }
warn() { printf '\n\033[1;33m%s\033[0m\n' "$*"; }

say "Phone Bridge setup — installing only free packages"
pkg update -y
pkg install -y python git gh jq curl termux-api

say "Downloading the tested bridge agent"
curl -fsSL "$PUB/agent.py" -o "$BASE/agent.py"
python -m py_compile "$BASE/agent.py"
chmod 700 "$BASE/agent.py"

if ! command -v termux-battery-status >/dev/null 2>&1; then
  echo "Termux:API command package did not install correctly."
  exit 20
fi

if ! pm list packages 2>/dev/null | grep -q '^package:com.termux.api$'; then
  warn "ACTION NEEDED: install the Termux:API Android app from the same source as Termux, then rerun this one command."
  printf '%s\n' 'https://f-droid.org/packages/com.termux.api/'
  exit 21
fi

say "Checking Android API connection"
if ! timeout 10 termux-battery-status >/dev/null 2>&1; then
  warn "Android has not granted Termux:API access yet. Opening its app settings. Grant requested permissions, then return to Termux and rerun the same bootstrap command."
  am start -a android.settings.APPLICATION_DETAILS_SETTINGS -d package:com.termux.api >/dev/null 2>&1 || true
  exit 22
fi

say "Connecting the bridge to your private GitHub control channel"
if ! gh auth status >/dev/null 2>&1; then
  export BROWSER=termux-open-url
  gh auth login --hostname github.com --git-protocol https --web --scopes repo
fi

gh auth status >/dev/null
gh api repos/keepinitkrispy/antiLLM/issues/1 --jq '.number' | grep -qx '1'

say "Installing self-start files"
cat > "$BASE/start.sh" <<'EOF'
#!/data/data/com.termux/files/usr/bin/bash
set -u
BASE="$HOME/.phonebridge"
mkdir -p "$BASE"
if pgrep -f "$BASE/agent.py" >/dev/null 2>&1; then exit 0; fi
termux-wake-lock >/dev/null 2>&1 || true
nohup python "$BASE/agent.py" >>"$BASE/nohup.log" 2>&1 &
EOF
chmod 700 "$BASE/start.sh"

cat > "$HOME/.termux/boot/phonebridge" <<'EOF'
#!/data/data/com.termux/files/usr/bin/bash
sleep 15
"$HOME/.phonebridge/start.sh"
EOF
chmod 700 "$HOME/.termux/boot/phonebridge"

say "Starting the bridge and waiting for a real end-to-end heartbeat"
"$BASE/start.sh"
sleep 4
if ! pgrep -f "$BASE/agent.py" >/dev/null 2>&1; then
  echo "Bridge agent failed to stay running."
  tail -n 40 "$BASE/nohup.log" 2>/dev/null || true
  exit 30
fi

for _ in $(seq 1 6); do
  BODY="$(gh api repos/keepinitkrispy/antiLLM/issues/1 --jq '.body' 2>/dev/null || true)"
  if printf '%s' "$BODY" | grep -q '"status": "online"'; then
    say "PHONE BRIDGE READY"
    printf '%s\n' "Core bridge is online. Call-log/SMS/notification/location permissions are tested individually by the agent and reported as capabilities."
    printf '%s\n' "Optional next upgrade: Shizuku/rish for ADB-level diagnostics."
    exit 0
  fi
  sleep 3
done

echo "Agent is running but end-to-end GitHub heartbeat was not confirmed."
tail -n 60 "$BASE/agent.log" 2>/dev/null || true
exit 31

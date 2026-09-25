#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ssh_host="${1:-gx10}"
if [[ ! "$ssh_host" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "Pass an SSH host alias or hostname (letters, numbers, dots, underscores, hyphens)." >&2
  exit 2
fi
agent_dir="$HOME/Library/LaunchAgents"
agent_path="$agent_dir/ai.antling.design-lab-tunnel.plist"
mkdir -p "$agent_dir" "$project_root/private"
cat > "$agent_path" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>ai.antling.design-lab-tunnel</string>
  <key>ProgramArguments</key><array>
    <string>/usr/bin/ssh</string>
    <string>-N</string>
    <string>-o</string><string>BatchMode=yes</string>
    <string>-o</string><string>ExitOnForwardFailure=yes</string>
    <string>-o</string><string>ConnectTimeout=10</string>
    <string>-o</string><string>ServerAliveInterval=30</string>
    <string>-o</string><string>ServerAliveCountMax=3</string>
    <string>-L</string><string>127.0.0.1:8765:127.0.0.1:8765</string>
    <string>$ssh_host</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>15</integer>
  <key>StandardErrorPath</key><string>$project_root/private/web-tunnel.err.log</string>
</dict></plist>
EOF
launchctl bootout "gui/$(id -u)" "$agent_path" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$agent_path"
echo "AntLing Design Lab tunnel installed on http://127.0.0.1:8765/"

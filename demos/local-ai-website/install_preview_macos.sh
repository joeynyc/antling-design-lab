#!/usr/bin/env bash
set -euo pipefail

demo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd "$demo_root/../.." && pwd)"
python_bin="$(command -v python3)"
agent_dir="$HOME/Library/LaunchAgents"
agent_path="$agent_dir/com.joey.antling-local-ai-website.plist"
mkdir -p "$agent_dir" "$project_root/private"
cat > "$agent_path" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.joey.antling-local-ai-website</string>
  <key>ProgramArguments</key><array>
    <string>$python_bin</string>
    <string>-m</string><string>http.server</string>
    <string>8767</string>
    <string>--bind</string><string>127.0.0.1</string>
    <string>--directory</string><string>$demo_root</string>
  </array>
  <key>WorkingDirectory</key><string>$demo_root</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>15</integer>
  <key>StandardOutPath</key><string>$project_root/private/website-preview.log</string>
  <key>StandardErrorPath</key><string>$project_root/private/website-preview.log</string>
</dict></plist>
PLIST
plutil -lint "$agent_path"
launchctl bootout "gui/$(id -u)" "$agent_path" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$agent_path"
echo "Website demo preview: http://127.0.0.1:8767/"

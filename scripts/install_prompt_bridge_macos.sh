#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
agent_dir="$HOME/Library/LaunchAgents"
agent_path="$agent_dir/ai.antling.prompt-rewriter.plist"
mkdir -p "$agent_dir" "$project_root/private"
cat > "$agent_path" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>ai.antling.prompt-rewriter</string>
  <key>ProgramArguments</key><array>
    <string>/usr/bin/python3</string>
    <string>$project_root/scripts/prompt_rewriter_bridge.py</string>
  </array>
  <key>WorkingDirectory</key><string>$project_root</string>
  <key>EnvironmentVariables</key><dict>
    <key>PATH</key><string>$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$project_root/private/prompt-bridge.out.log</string>
  <key>StandardErrorPath</key><string>$project_root/private/prompt-bridge.err.log</string>
</dict></plist>
EOF
launchctl bootout "gui/$(id -u)" "$agent_path" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$agent_path"
echo "Codex prompt helper installed on 127.0.0.1:8766"

#!/usr/bin/env bash
# Installs Nautag, Finder-style colour tags for Nautilus. Safe to re-run.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
EXT="$HOME/.local/share/nautilus-python/extensions"
UNITS="$HOME/.config/systemd/user"

dpkg -s python3-nautilus libnotify-bin > /dev/null 2>&1 || sudo apt-get install -y python3-nautilus libnotify-bin

mkdir -p "$EXT" "$UNITS"
cp "$HERE/file_tags.py" "$EXT/file_tags.py"
python3 "$EXT/file_tags.py" init

cat > "$UNITS/file-tags-rescan.service" <<UNIT
[Unit]
Description=Sync colour tag folders with file xattrs

[Service]
Type=oneshot
Nice=19
IOSchedulingClass=idle
ExecStart=/usr/bin/python3 $EXT/file_tags.py rescan
UNIT
cat > "$UNITS/file-tags-rescan.timer" <<UNIT
[Unit]
Description=Periodically sync colour tag folders

[Timer]
OnStartupSec=1min
OnUnitActiveSec=10min

[Install]
WantedBy=timers.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now file-tags-rescan.timer

echo "Done. Restart Nautilus to load it (closes its windows and stops running copies): nautilus -q"

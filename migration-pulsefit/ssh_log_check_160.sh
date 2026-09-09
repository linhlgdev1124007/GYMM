#!/usr/bin/env bash
set +e
echo "===SSH recent failed/invalid/accepted==="
sudo -n journalctl -u ssh --since "24 hours ago" --no-pager | grep -Ei "failed|invalid|accepted" | tail -80
echo "===SSH service status==="
systemctl is-active ssh

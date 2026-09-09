#!/usr/bin/env bash
set +e

section() {
  printf '\n===%s===\n' "$1"
}

section SYSTEM
hostnamectl

section WHOAMI
id
who

section LISTEN
sudo -n ss -tulpn

section UFW
sudo -n ufw status verbose

section IPTABLES_DOCKER
sudo -n iptables -S DOCKER 2>/dev/null

section SSH_CONFIG
sudo -n sshd -T | grep -E '^(port|permitrootlogin|passwordauthentication|pubkeyauthentication|challengeresponseauthentication|kbdinteractiveauthentication|x11forwarding|maxauthtries|allowusers|logingracetime)'

section DOCKER_PS
cd /home/vmadmin/GYMM/gym-manager-python && docker compose ps

section DOCKER_INSPECT_APP
docker inspect pulsefit-app-1 --format 'User={{.Config.User}} Privileged={{.HostConfig.Privileged}} ReadonlyRootfs={{.HostConfig.ReadonlyRootfs}} CapDrop={{json .HostConfig.CapDrop}} SecurityOpt={{json .HostConfig.SecurityOpt}} Ports={{json .NetworkSettings.Ports}}'

section DOCKER_INSPECT_DB
docker inspect pulsefit-database-1 --format 'User={{.Config.User}} Privileged={{.HostConfig.Privileged}} ReadonlyRootfs={{.HostConfig.ReadonlyRootfs}} CapDrop={{json .HostConfig.CapDrop}} SecurityOpt={{json .HostConfig.SecurityOpt}} Ports={{json .NetworkSettings.Ports}}'

section ENV_PERMS
ls -la /home/vmadmin/GYMM/gym-manager-python/.env /home/vmadmin/GYMM/gym-manager-python/compose.yaml

section ENV_REDACTED
sed -E 's/(PASSWORD|TOKEN|SECRET)=.*/\1=<redacted>/' /home/vmadmin/GYMM/gym-manager-python/.env

section UPDATES
apt list --upgradable 2>/dev/null | head -80

section FAIL2BAN
systemctl is-active fail2ban 2>/dev/null
systemctl status fail2ban --no-pager 2>/dev/null | head -30

section APP_HEALTH
curl -fsS http://127.0.0.1:3333/api/health

section APP_LOGS
cd /home/vmadmin/GYMM/gym-manager-python && docker compose logs --tail=80 app

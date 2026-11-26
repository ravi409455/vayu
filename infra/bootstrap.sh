#!/usr/bin/env bash
# Turn a fresh Ubuntu 24.04 droplet into a Vayu server. Run ONCE, as root, from the laptop:
#   ssh root@<server ip> 'bash -s' < infra/bootstrap.sh
# Staging and production run this same file (docs/plan-deploy.md 3.1). Safe to run again.
#
# After it: root and passwords can no longer log in; you log in as `deploy` with the same SSH key.
# What it does: updates and automatic security updates, a firewall (22, 80, 443 only), Docker with
# log limits, the `deploy` user, swap on small servers, UTC clock, the code in /srv/vayu, and the
# nightly backup timer (02:00 IST).
set -euo pipefail
[[ $(id -u) -eq 0 ]] || { echo "run as root"; exit 1; }
REPO=${VAYU_REPO:-https://github.com/ravi409455/vayu.git}
export DEBIAN_FRONTEND=noninteractive

echo "== packages and automatic security updates"
apt-get update -q
apt-get upgrade -yq
apt-get install -yq ca-certificates curl git ufw unattended-upgrades age
dpkg-reconfigure -f noninteractive unattended-upgrades
timedatectl set-timezone UTC

echo "== Docker (from Docker's own repository)"
if ! command -v docker >/dev/null; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -q
  apt-get install -yq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
# logs can never fill the disk
cat > /etc/docker/daemon.json <<'EOF'
{"log-driver": "json-file", "log-opts": {"max-size": "20m", "max-file": "5"}}
EOF
systemctl restart docker

echo "== the deploy user (your SSH key, no password)"
id deploy >/dev/null 2>&1 || useradd -m -s /bin/bash -G docker,systemd-journal deploy
install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
if [[ ! -s /home/deploy/.ssh/authorized_keys ]]; then
  install -m 600 -o deploy -g deploy /root/.ssh/authorized_keys /home/deploy/.ssh/authorized_keys
fi

echo "== SSH: keys only, no root"
cat > /etc/ssh/sshd_config.d/10-vayu.conf <<'EOF'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
EOF
sshd -t && systemctl reload ssh

echo "== firewall: SSH, HTTP, HTTPS only"
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp   # HTTP/3
ufw --force enable

echo "== swap on small servers (PDF rendering needs memory)"
if [[ $(free -g | awk '/Mem:/ {print $2}') -lt 6 && ! -f /swapfile ]]; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

echo "== the code in /srv/vayu"
install -d -o deploy -g deploy /srv/vayu
[[ -d /srv/vayu/.git ]] || sudo -u deploy git clone --quiet "$REPO" /srv/vayu
install -d -m 700 -o deploy -g deploy /srv/vayu/secrets /srv/vayu/backups

echo "== nightly backup at 02:00 IST (20:30 UTC)"
cat > /etc/systemd/system/vayu-backup.service <<'EOF'
[Unit]
Description=Vayu database backup to R2
[Service]
Type=oneshot
User=deploy
ExecStart=/srv/vayu/infra/backup.sh nightly
EOF
cat > /etc/systemd/system/vayu-backup.timer <<'EOF'
[Unit]
Description=Vayu nightly database backup
[Timer]
OnCalendar=*-*-* 20:30:00 UTC
Persistent=true
[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now vayu-backup.timer

echo
echo "Done. Next (docs/runbook-new-server.md): log in as deploy@<this server>, write the env file,"
echo "copy the Firebase file, add the GitHub robot key, then run the first deploy from GitHub."

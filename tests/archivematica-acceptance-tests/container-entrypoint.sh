#!/usr/bin/env bash
set -euo pipefail

DISABLE_IPV6="${DISABLE_IPV6:-0}"
DISABLE_SELINUX="${DISABLE_SELINUX:-0}"

# Ensure logins work even if nologin was left behind during boot
rm -f /run/nologin /var/run/nologin || true

# Force sshd to skip PAM (avoid pam_nologin blocking during boot) and require keys
mkdir -p /etc/ssh/sshd_config.d
cat >/etc/ssh/sshd_config.d/99-no-pam.conf <<'EOF'
UsePAM no
PasswordAuthentication yes
KbdInteractiveAuthentication no
EOF

if [[ "${DISABLE_IPV6}" == "1" ]]; then
  mkdir -p /etc/sysctl.d
  cat >/etc/sysctl.d/99-disable-ipv6.conf <<'EOF'
net.ipv6.conf.all.disable_ipv6 = 1
net.ipv6.conf.default.disable_ipv6 = 1
net.ipv6.conf.lo.disable_ipv6 = 1
EOF
  sysctl -p /etc/sysctl.d/99-disable-ipv6.conf || true
fi

if [[ "${DISABLE_SELINUX}" == "1" ]]; then
  if command -v setenforce >/dev/null 2>&1; then
    setenforce 0 || true
  fi
  if [[ -f /etc/selinux/config ]]; then
    sed -i 's/^SELINUX=.*/SELINUX=permissive/' /etc/selinux/config
  fi
fi

# Keep journald logs available for collection
mkdir -p /var/log/journal
systemd-tmpfiles --create --prefix /var/log/journal || true

SYSTEMD_BIN="/lib/systemd/systemd"
if [[ ! -x "${SYSTEMD_BIN}" ]]; then
  SYSTEMD_BIN="/usr/lib/systemd/systemd"
fi

exec "${SYSTEMD_BIN}" "$@"

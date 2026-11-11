#!/usr/bin/env bash
# EC2 최초 1회 설정 (Amazon Linux 2023, user-data 로 root 실행)
#   __DEPLOY_BRANCH__ / __AWS_REGION__ 은 create_ec2.sh 가 채워 넣는다.
set -euxo pipefail

DEPLOY_BRANCH="__DEPLOY_BRANCH__"
AWS_REGION="__AWS_REGION__"
GITHUB_REPO="4naii/cloud-nkios-team-6"

dnf install -y git python3.11 python3.11-pip
id app || useradd -m app
[ -d /home/app/repo ] || runuser -u app -- git clone "https://github.com/$GITHUB_REPO.git" /home/app/repo
[ -d /home/app/venv ] || runuser -u app -- python3.11 -m venv /home/app/venv

cat > /etc/income-predictor.env <<EOF
DEPLOY_BRANCH=$DEPLOY_BRANCH
GITHUB_REPO=$GITHUB_REPO
CW_LOG_GROUP=/mlops/team6-adult-income
AWS_REGION=$AWS_REGION
EOF

cat > /etc/systemd/system/income-predictor.service <<'EOF'
[Unit]
Description=Adult income predictor API
After=network-online.target

[Service]
User=app
WorkingDirectory=/home/app/repo/adult-income
EnvironmentFile=/etc/income-predictor.env
ExecStart=/home/app/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/income-predictor-deploy.service <<'EOF'
[Unit]
Description=Pull and deploy commits that passed CI

[Service]
Type=oneshot
ExecStart=/bin/bash /home/app/repo/adult-income/deploy/deploy.sh
EOF

cat > /etc/systemd/system/income-predictor-deploy.timer <<'EOF'
[Unit]
Description=Check for new commits every minute

[Timer]
OnBootSec=60s
OnActiveSec=10s
OnUnitActiveSec=60s

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable income-predictor
systemctl enable --now income-predictor-deploy.timer

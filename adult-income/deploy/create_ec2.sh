#!/usr/bin/env bash
# AWS CloudShell 에서 1회 실행: 배포용 EC2 생성
#   - IAM 역할: 학교 제공 yeonsung-ec2-ssm-cloudwatch-role (CloudWatch Logs + SSM 접속)
#     다른 역할을 쓰려면 INSTANCE_PROFILE=<이름> bash deploy/create_ec2.sh ...
#   - 보안 그룹: 8000 포트만 공개 (SSH 포트 안 엶)
#   - user-data: deploy/setup_ec2.sh (이후 배포는 EC2 가 CI 통과 커밋을 스스로 가져감)
#
# 사용법 (adult-income 폴더에서): bash deploy/create_ec2.sh [배포할 브랜치, 기본 main]
set -euo pipefail

BRANCH="${1:-main}"
REGION="${AWS_REGION:-ap-northeast-2}"
NAME=team6-income-predictor
ROLE="${INSTANCE_PROFILE:-yeonsung-ec2-ssm-cloudwatch-role}"  # CloudWatch Logs + SSM 권한
export AWS_REGION="$REGION" AWS_DEFAULT_REGION="$REGION" AWS_PAGER=""

EXISTING=$(aws ec2 describe-instances --filters "Name=tag:Name,Values=$NAME" \
  "Name=instance-state-name,Values=pending,running" --query 'Reservations[].Instances[].InstanceId' --output text)
if [ -n "$EXISTING" ]; then
  IP=$(aws ec2 describe-instances --instance-ids $EXISTING --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
  echo "이미 실행 중: $EXISTING  http://$IP:8000"
  exit 0
fi

echo "== 1. IAM 역할 (수업 계정은 역할 생성이 막혀 있어 학교 제공 역할 사용)"
aws iam get-instance-profile --instance-profile-name "$ROLE" --query 'InstanceProfile.Roles[0].RoleName' --output text

echo "== 2. 보안 그룹 (8000 포트)"
VPC=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)
SG=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=$NAME" "Name=vpc-id,Values=$VPC" \
  --query 'SecurityGroups[0].GroupId' --output text)
if [ "$SG" = "None" ]; then
  SG=$(aws ec2 create-security-group --group-name "$NAME" --description "income predictor API" \
    --vpc-id "$VPC" --query GroupId --output text)
  aws ec2 authorize-security-group-ingress --group-id "$SG" --protocol tcp --port 8000 --cidr 0.0.0.0/0 > /dev/null
fi

echo "== 3. EC2 생성 (브랜치 $BRANCH)"
AMI=$(aws ssm get-parameter --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
  --query Parameter.Value --output text)
sed -e "s#__DEPLOY_BRANCH__#$BRANCH#" -e "s#__AWS_REGION__#$REGION#" "$(dirname "$0")/setup_ec2.sh" > /tmp/user-data.sh
ID=$(aws ec2 run-instances --image-id "$AMI" --instance-type t3.small \
  --iam-instance-profile Name="$ROLE" --security-group-ids "$SG" \
  --block-device-mappings 'DeviceName=/dev/xvda,Ebs={VolumeSize=16,VolumeType=gp3}' \
  --metadata-options HttpTokens=required \
  --user-data file:///tmp/user-data.sh \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$NAME}]" \
  --query 'Instances[0].InstanceId' --output text)
aws ec2 wait instance-running --instance-ids "$ID"
IP=$(aws ec2 describe-instances --instance-ids "$ID" --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)

echo
echo "완료: $ID"
echo "약 5분 뒤 (패키지 설치 + 첫 학습) 접속: http://$IP:8000"
echo "상태 확인: curl http://$IP:8000/health"

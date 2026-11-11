#!/usr/bin/env bash
# AWS CloudShell 에서 1회 실행: 배포용 EC2 생성
#   - IAM 역할: CloudWatch Logs 쓰기/읽기 + SSM 접속(콘솔에서 SSH 없이 접속)
#   - 보안 그룹: 8000 포트만 공개 (SSH 포트 안 엶)
#   - user-data: deploy/setup_ec2.sh (이후 배포는 EC2 가 CI 통과 커밋을 스스로 가져감)
#
# 사용법 (adult-income 폴더에서): bash deploy/create_ec2.sh [배포할 브랜치, 기본 main]
set -euo pipefail

BRANCH="${1:-main}"
REGION="${AWS_REGION:-ap-northeast-2}"
NAME=team6-income-predictor
ROLE=team6-income-predictor-ec2
export AWS_REGION="$REGION" AWS_DEFAULT_REGION="$REGION"

EXISTING=$(aws ec2 describe-instances --filters "Name=tag:Name,Values=$NAME" \
  "Name=instance-state-name,Values=pending,running" --query 'Reservations[].Instances[].InstanceId' --output text)
if [ -n "$EXISTING" ]; then
  IP=$(aws ec2 describe-instances --instance-ids $EXISTING --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
  echo "이미 실행 중: $EXISTING  http://$IP:8000"
  exit 0
fi

echo "== 1. IAM 역할"
if ! aws iam get-role --role-name "$ROLE" > /dev/null 2>&1; then
  aws iam create-role --role-name "$ROLE" --assume-role-policy-document \
    '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}' > /dev/null
  aws iam attach-role-policy --role-name "$ROLE" --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
  aws iam put-role-policy --role-name "$ROLE" --policy-name cloudwatch-logs --policy-document \
    '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["logs:CreateLogGroup","logs:CreateLogStream","logs:PutLogEvents","logs:DescribeLogStreams","logs:FilterLogEvents","logs:GetLogEvents"],"Resource":"*"}]}'
  aws iam create-instance-profile --instance-profile-name "$ROLE" > /dev/null
  aws iam add-role-to-instance-profile --instance-profile-name "$ROLE" --role-name "$ROLE"
  echo "   생성 완료, IAM 반영 대기 15초"; sleep 15
fi

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

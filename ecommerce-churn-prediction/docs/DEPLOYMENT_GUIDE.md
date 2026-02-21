# Production Deployment Guide

Complete step-by-step guide for deploying the Churn Prediction system to AWS and Kubernetes.

---

## Table of Contents
1. [AWS Deployment](#aws-deployment)
2. [Kubernetes Deployment](#kubernetes-deployment)
3. [Post-Deployment Verification](#post-deployment-verification)
4. [Monitoring & Alerting](#monitoring--alerting)
5. [Troubleshooting](#troubleshooting)

---

## AWS Deployment

### Prerequisites
- AWS Account with appropriate IAM permissions
- AWS CLI v2 installed and configured
- Docker installed locally
- Terraform installed (optional but recommended)

### Option A: Manual Deployment (Step-by-Step)

#### Step 1: Setup AWS Infrastructure

**1.1 Create VPC and Networking**

```bash
# Create VPC
aws ec2 create-vpc --cidr-block 10.0.0.0/16 --tag-specifications 'ResourceType=vpc,Tags=[{Key=Name,Value=churn-vpc}]'

# Capture VPC ID from output
export VPC_ID="vpc-xxxxxxxx"

# Create public subnets (for ALB)
aws ec2 create-subnet \
  --vpc-id $VPC_ID \
  --cidr-block 10.0.1.0/24 \
  --availability-zone us-east-1a \
  --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=churn-public-1a}]'

aws ec2 create-subnet \
  --vpc-id $VPC_ID \
  --cidr-block 10.0.2.0/24 \
  --availability-zone us-east-1b \
  --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=churn-public-1b}]'

# Create private subnets (for ECS tasks)
aws ec2 create-subnet \
  --vpc-id $VPC_ID \
  --cidr-block 10.0.10.0/24 \
  --availability-zone us-east-1a \
  --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=churn-private-1a}]'

aws ec2 create-subnet \
  --vpc-id $VPC_ID \
  --cidr-block 10.0.11.0/24 \
  --availability-zone us-east-1b \
  --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=churn-private-1b}]'
```

**1.2 Create Security Groups**

```bash
# ALB Security Group (allows internet traffic)
aws ec2 create-security-group \
  --group-name churn-alb-sg \
  --description "Security group for Churn Prediction ALB" \
  --vpc-id $VPC_ID

export ALB_SG_ID="sg-xxxxxxxx"

# Allow HTTP (80) and HTTPS (443)
aws ec2 authorize-security-group-ingress \
  --group-id $ALB_SG_ID \
  --protocol tcp --port 80 --cidr 0.0.0.0/0

aws ec2 authorize-security-group-ingress \
  --group-id $ALB_SG_ID \
  --protocol tcp --port 443 --cidr 0.0.0.0/0

# ECS Security Group
aws ec2 create-security-group \
  --group-name churn-ecs-sg \
  --description "Security group for Churn Prediction ECS tasks" \
  --vpc-id $VPC_ID

export ECS_SG_ID="sg-yyyyyyyy"

# Allow traffic from ALB to ECS (port 8000)
aws ec2 authorize-security-group-ingress \
  --group-id $ECS_SG_ID \
  --protocol tcp --port 8000 \
  --source-security-group-id $ALB_SG_ID

# RDS Security Group
aws ec2 create-security-group \
  --group-name churn-rds-sg \
  --description "Security group for Churn Prediction RDS" \
  --vpc-id $VPC_ID

export RDS_SG_ID="sg-zzzzzzzz"

# Allow PostgreSQL from ECS
aws ec2 authorize-security-group-ingress \
  --group-id $RDS_SG_ID \
  --protocol tcp --port 5432 \
  --source-security-group-id $ECS_SG_ID
```

**1.3 Create RDS PostgreSQL Database**

```bash
# Create DB subnet group
aws rds create-db-subnet-group \
  --db-subnet-group-name churn-db-subnet-group \
  --db-subnet-group-description "Subnet group for Churn RDS" \
  --subnet-ids subnet-1a subnet-1b

# Create RDS instance (Multi-AZ for reliability)
aws rds create-db-instance \
  --db-instance-identifier churn-db \
  --db-instance-class db.t3.medium \
  --engine postgres \
  --engine-version 15.1 \
  --master-username postgres \
  --master-user-password $(openssl rand -base64 32) \
  --allocated-storage 100 \
  --storage-type gp3 \
  --multi-az \
  --db-subnet-group-name churn-db-subnet-group \
  --vpc-security-group-ids $RDS_SG_ID \
  --backup-retention-period 30 \
  --preferred-backup-window "03:00-04:00" \
  --publicly-accessible false \
  --enable-cloudwatch-logs-exports '["postgresql"]'

# Wait for DB to be available
aws rds wait db-instance-available --db-instance-identifier churn-db

# Get DB endpoint
export DB_ENDPOINT=$(aws rds describe-db-instances \
  --db-instance-identifier churn-db \
  --query 'DBInstances[0].Endpoint.Address' --output text)
```

**1.4 Create ElastiCache Redis Cluster**

```bash
# Create cache subnet group
aws elasticache create-cache-subnet-group \
  --cache-subnet-group-name churn-cache-subnet-group \
  --description "Subnet group for Churn Redis" \
  --subnet-ids subnet-1a subnet-1b

# Create Redis cluster
aws elasticache create-replication-group \
  --replication-group-description "Churn Prediction Redis" \
  --replication-group-id churn-redis \
  --engine redis \
  --engine-version 7.0 \
  --cache-node-type cache.t3.micro \
  --num-cache-clusters 2 \
  --automatic-failover-enabled \
  --cache-subnet-group-name churn-cache-subnet-group \
  --security-group-ids $ECS_SG_ID \
  --multi-az-enabled

# Get Redis endpoint
export REDIS_ENDPOINT=$(aws elasticache describe-replication-groups \
  --replication-group-id churn-redis \
  --query 'ReplicationGroups[0].PrimaryEndpoint.Address' --output text)
```

#### Step 2: Create ECR Repository and Push Docker Image

```bash
# Create ECR repository
aws ecr create-repository --repository-name churn-prediction

export ECR_URI="123456789.dkr.ecr.us-east-1.amazonaws.com/churn-prediction"

# Login to ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin $ECR_URI

# Build and push image
docker build \
  -f deployment/Dockerfile \
  --target production \
  -t churn-prediction:latest \
  -t $ECR_URI:latest \
  .

docker push $ECR_URI:latest

# Tag for versioning
IMAGE_TAG=$(date +%Y%m%d-%H%M%S)
docker tag $ECR_URI:latest $ECR_URI:$IMAGE_TAG
docker push $ECR_URI:$IMAGE_TAG
```

#### Step 3: Create ECS Cluster and Task Definition

**3.1 Create ECS Cluster**

```bash
# Create cluster
aws ecs create-cluster --cluster-name churn-prod

# Create CloudWatch log group
aws logs create-log-group --log-group-name /ecs/churn-prediction
```

**3.2 Create Task Definition**

```bash
# Create task definition JSON
cat > task-definition.json <<EOF
{
  "family": "churn-prediction",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "containerDefinitions": [
    {
      "name": "churn-api",
      "image": "$ECR_URI:latest",
      "portMappings": [
        {
          "containerPort": 8000,
          "hostPort": 8000,
          "protocol": "tcp"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/churn-prediction",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "ecs"
        }
      },
      "environment": [
        {
          "name": "ENVIRONMENT",
          "value": "production"
        },
        {
          "name": "DATABASE_URL",
          "value": "postgresql://postgres:password@$DB_ENDPOINT:5432/churn"
        },
        {
          "name": "REDIS_URL",
          "value": "redis://$REDIS_ENDPOINT:6379/0"
        },
        {
          "name": "MLFLOW_TRACKING_URI",
          "value": "https://mlflow.company.com"
        }
      ],
      "healthCheck": {
        "command": ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"],
        "interval": 30,
        "timeout": 5,
        "retries": 3,
        "startPeriod": 60
      }
    }
  ],
  "executionRoleArn": "arn:aws:iam::123456789:role/ecsTaskExecutionRole",
  "taskRoleArn": "arn:aws:iam::123456789:role/ecsTaskRole"
}
EOF

# Register task definition
aws ecs register-task-definition --cli-input-json file://task-definition.json
```

**3.3 Create ECS Service**

```bash
# Get VPC subnets
export SUBNET_1=$(aws ec2 describe-subnets --filters Name=tag:Name,Values=churn-private-1a --query 'Subnets[0].SubnetId' --output text)
export SUBNET_2=$(aws ec2 describe-subnets --filters Name=tag:Name,Values=churn-private-1b --query 'Subnets[0].SubnetId' --output text)

# Create Application Load Balancer
aws elbv2 create-load-balancer \
  --name churn-alb \
  --subnets $SUBNET_1 $SUBNET_2 \
  --security-groups $ALB_SG_ID \
  --scheme internet-facing

export ALB_ARN=$(aws elbv2 describe-load-balancers --names churn-alb --query 'LoadBalancers[0].LoadBalancerArn' --output text)
export ALB_DNS=$(aws elbv2 describe-load-balancers --names churn-alb --query 'LoadBalancers[0].DNSName' --output text)

# Create target group
aws elbv2 create-target-group \
  --name churn-api \
  --protocol HTTP \
  --port 8000 \
  --vpc-id $VPC_ID \
  --target-type ip \
  --health-check-protocol HTTP \
  --health-check-path /health \
  --health-check-interval-seconds 30

export TG_ARN=$(aws elbv2 describe-target-groups --names churn-api --query 'TargetGroups[0].TargetGroupArn' --output text)

# Create listener
aws elbv2 create-listener \
  --load-balancer-arn $ALB_ARN \
  --protocol HTTP \
  --port 80 \
  --default-actions Type=forward,TargetGroupArn=$TG_ARN

# Create ECS service
aws ecs create-service \
  --cluster churn-prod \
  --service-name churn-api \
  --task-definition churn-prediction:1 \
  --desired-count 2 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_1,$SUBNET_2],securityGroups=[$ECS_SG_ID],assignPublicIp=DISABLED}" \
  --load-balancers targetGroupArn=$TG_ARN,containerName=churn-api,containerPort=8000 \
  --deployment-configuration maximumPercent=200,minimumHealthyPercent=100

# Setup Auto Scaling
aws application-autoscaling register-scalable-target \
  --service-namespace ecs \
  --resource-id service/churn-prod/churn-api \
  --scalable-dimension ecs:service:DesiredCount \
  --min-capacity 2 \
  --max-capacity 10

# Target tracking scaling policy (CPU)
aws application-autoscaling put-scaling-policy \
  --policy-name churn-cpu-scaling \
  --service-namespace ecs \
  --resource-id service/churn-prod/churn-api \
  --scalable-dimension ecs:service:DesiredCount \
  --policy-type TargetTrackingScaling \
  --target-tracking-scaling-policy-configuration '{
    "TargetValue": 70.0,
    "PredefinedMetricSpecification": {
      "PredefinedMetricType": "ECSServiceAverageCPUUtilization"
    },
    "ScaleOutCooldown": 60,
    "ScaleInCooldown": 300
  }'
```

#### Step 4: Setup Monitoring and Logging

```bash
# Create CloudWatch Alarms
# High Error Rate
aws cloudwatch put-metric-alarm \
  --alarm-name churn-api-errors \
  --alarm-description "Alert when error rate > 5%" \
  --metric-name HTTPCode_Target_5XX_Count \
  --namespace AWS/ApplicationELB \
  --statistic Sum \
  --period 300 \
  --threshold 50 \
  --comparison-operator GreaterThanThreshold \
  --alarm-actions arn:aws:sns:us-east-1:123456789:alerts

# High Latency
aws cloudwatch put-metric-alarm \
  --alarm-name churn-api-latency \
  --alarm-description "Alert when p99 latency > 500ms" \
  --metric-name TargetResponseTime \
  --namespace AWS/ApplicationELB \
  --statistic Average \
  --period 300 \
  --threshold 0.5 \
  --comparison-operator GreaterThanThreshold

# Low Health
aws cloudwatch put-metric-alarm \
  --alarm-name churn-api-unhealthy \
  --alarm-description "Alert when unhealthy hosts > 0" \
  --metric-name UnHealthyHostCount \
  --namespace AWS/ApplicationELB \
  --statistic Maximum \
  --period 60 \
  --threshold 0 \
  --comparison-operator GreaterThanThreshold
```

#### Step 5: Setup Secrets Manager

```bash
# Store database password
aws secretsmanager create-secret \
  --name churn/db/password \
  --description "PostgreSQL password for Churn DB" \
  --secret-string "your-secure-password"

# Store API keys
aws secretsmanager create-secret \
  --name churn/api/key \
  --description "API key for Churn Prediction API" \
  --secret-string "$(openssl rand -base64 32)"

# Store MLflow credentials
aws secretsmanager create-secret \
  --name churn/mlflow/token \
  --description "MLflow API token" \
  --secret-string "your-mlflow-token"
```

### Option B: Infrastructure-as-Code (Terraform)

Create `terraform/main.tf`:

```hcl
# Configure AWS Provider
provider "aws" {
  region = var.aws_region
}

# VPC
resource "aws_vpc" "churn" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "churn-vpc"
  }
}

# Public Subnets
resource "aws_subnet" "public_1a" {
  vpc_id                  = aws_vpc.churn.id
  cidr_block              = "10.0.1.0/24"
  availability_zone       = "${var.aws_region}a"
  map_public_ip_on_launch = true

  tags = {
    Name = "churn-public-1a"
  }
}

resource "aws_subnet" "public_1b" {
  vpc_id                  = aws_vpc.churn.id
  cidr_block              = "10.0.2.0/24"
  availability_zone       = "${var.aws_region}b"
  map_public_ip_on_launch = true

  tags = {
    Name = "churn-public-1b"
  }
}

# Private Subnets
resource "aws_subnet" "private_1a" {
  vpc_id            = aws_vpc.churn.id
  cidr_block        = "10.0.10.0/24"
  availability_zone = "${var.aws_region}a"

  tags = {
    Name = "churn-private-1a"
  }
}

resource "aws_subnet" "private_1b" {
  vpc_id            = aws_vpc.churn.id
  cidr_block        = "10.0.11.0/24"
  availability_zone = "${var.aws_region}b"

  tags = {
    Name = "churn-private-1b"
  }
}

# Internet Gateway
resource "aws_internet_gateway" "churn" {
  vpc_id = aws_vpc.churn.id

  tags = {
    Name = "churn-igw"
  }
}

# Route table for public subnets
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.churn.id

  route {
    cidr_block      = "0.0.0.0/0"
    gateway_id      = aws_internet_gateway.churn.id
  }

  tags = {
    Name = "churn-public-rt"
  }
}

# Associate route table with subnets
resource "aws_route_table_association" "public_1a" {
  subnet_id      = aws_subnet.public_1a.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "public_1b" {
  subnet_id      = aws_subnet.public_1b.id
  route_table_id = aws_route_table.public.id
}

# Security Groups
resource "aws_security_group" "alb" {
  name        = "churn-alb-sg"
  description = "Security group for Churn ALB"
  vpc_id      = aws_vpc.churn.id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# RDS PostgreSQL
resource "aws_db_subnet_group" "churn" {
  name       = "churn-db-subnet-group"
  subnet_ids = [aws_subnet.private_1a.id, aws_subnet.private_1b.id]

  tags = {
    Name = "churn-db-subnet-group"
  }
}

resource "aws_security_group" "rds" {
  name        = "churn-rds-sg"
  description = "Security group for Churn RDS"
  vpc_id      = aws_vpc.churn.id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id]
  }
}

resource "aws_db_instance" "churn" {
  identifier            = "churn-db"
  allocated_storage    = 100
  storage_type         = "gp3"
  engine               = "postgres"
  engine_version       = "15.1"
  instance_class       = "db.t3.medium"
  username             = "postgres"
  password             = random_password.db_password.result
  db_name              = "churn"
  parameter_group_name = "default.postgres15"
  skip_final_snapshot  = false
  multi_az             = true

  db_subnet_group_name   = aws_db_subnet_group.churn.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  backup_retention_period = 30
  backup_window          = "03:00-04:00"

  enable_cloudwatch_logs_exports = ["postgresql"]

  tags = {
    Name = "churn-db"
  }
}

# ... (continued in next section)
```

Deploy with Terraform:

```bash
cd terraform
terraform init
terraform plan -out=tfplan
terraform apply tfplan

# Save outputs
terraform output -json > outputs.json
```

---

## Kubernetes Deployment

### Prerequisites
- Kubernetes cluster (EKS, GKE, or on-premises)
- kubectl CLI installed
- Helm installed (optional but recommended)

### Step 1: Create Kubernetes Namespace

```bash
kubectl create namespace churn-prediction
kubectl label namespace churn-prediction environment=production
```

### Step 2: Create ConfigMap for Configuration

```bash
kubectl create configmap churn-config \
  --from-literal=ENVIRONMENT=production \
  --from-literal=DATABASE_HOST=postgres.default.svc.cluster.local \
  --from-literal=REDIS_HOST=redis.default.svc.cluster.local \
  --namespace churn-prediction
```

### Step 3: Create Secrets

```bash
# Database password
kubectl create secret generic db-secret \
  --from-literal=password='your-secure-password' \
  --namespace churn-prediction

# API key
kubectl create secret generic api-secret \
  --from-literal=api-key="$(openssl rand -base64 32)" \
  --namespace churn-prediction

# MLflow credentials
kubectl create secret generic mlflow-secret \
  --from-literal=token='your-mlflow-token' \
  --namespace churn-prediction
```

### Step 4: Create PostgreSQL StatefulSet

Create `k8s/postgres-statefulset.yaml`:

```yaml
---
apiVersion: v1
kind: Service
metadata:
  name: postgres
  namespace: churn-prediction
spec:
  selector:
    app: postgres
  ports:
    - port: 5432
      targetPort: 5432
  clusterIP: None  # Headless service

---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
  namespace: churn-prediction
spec:
  serviceName: postgres
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
      - name: postgres
        image: postgres:15-alpine
        ports:
        - containerPort: 5432
          name: postgres
        env:
        - name: POSTGRES_DB
          value: churn
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: db-secret
              key: password
        volumeMounts:
        - name: postgres-storage
          mountPath: /var/lib/postgresql/data
        livenessProbe:
          exec:
            command:
            - /bin/sh
            - -c
            - pg_isready -U postgres
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          exec:
            command:
            - /bin/sh
            - -c
            - pg_isready -U postgres
          initialDelaySeconds: 5
          periodSeconds: 10
        resources:
          requests:
            cpu: 250m
            memory: 512Mi
          limits:
            cpu: 500m
            memory: 1Gi
  volumeClaimTemplates:
  - metadata:
      name: postgres-storage
    spec:
      accessModes: ["ReadWriteOnce"]
      resources:
        requests:
          storage: 50Gi
```

### Step 5: Create Redis Deployment

Create `k8s/redis-deployment.yaml`:

```yaml
---
apiVersion: v1
kind: Service
metadata:
  name: redis
  namespace: churn-prediction
spec:
  selector:
    app: redis
  ports:
    - port: 6379
      targetPort: 6379

---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis
  namespace: churn-prediction
spec:
  replicas: 1
  selector:
    matchLabels:
      app: redis
  template:
    metadata:
      labels:
        app: redis
    spec:
      containers:
      - name: redis
        image: redis:7-alpine
        ports:
        - containerPort: 6379
        livenessProbe:
          tcpSocket:
            port: 6379
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          exec:
            command:
            - redis-cli
            - ping
          initialDelaySeconds: 5
          periodSeconds: 10
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 200m
            memory: 512Mi
```

### Step 6: Create FastAPI Deployment

Create `k8s/api-deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: churn-api
  namespace: churn-prediction
  labels:
    app: churn-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: churn-api
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0  # Zero downtime
  template:
    metadata:
      labels:
        app: churn-api
    spec:
      containers:
      - name: api
        image: 123456789.dkr.ecr.us-east-1.amazonaws.com/churn-prediction:latest
        imagePullPolicy: Always
        ports:
        - containerPort: 8000
          name: http
        env:
        - name: ENVIRONMENT
          valueFrom:
            configMapKeyRef:
              name: churn-config
              key: ENVIRONMENT
        - name: DATABASE_HOST
          valueFrom:
            configMapKeyRef:
              name: churn-config
              key: DATABASE_HOST
        - name: DATABASE_PASSWORD
          valueFrom:
            secretKeyRef:
              name: db-secret
              key: password
        - name: REDIS_HOST
          valueFrom:
            configMapKeyRef:
              name: churn-config
              key: REDIS_HOST
        - name: API_KEY
          valueFrom:
            secretKeyRef:
              name: api-secret
              key: api-key
        - name: MLFLOW_TRACKING_URI
          value: "https://mlflow.company.com"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
          failureThreshold: 3
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 5
          failureThreshold: 2
        resources:
          requests:
            cpu: 250m
            memory: 512Mi
          limits:
            cpu: 500m
            memory: 1Gi
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            podAffinityTerm:
              labelSelector:
                matchExpressions:
                - key: app
                  operator: In
                  values:
                  - churn-api
              topologyKey: kubernetes.io/hostname

---
apiVersion: v1
kind: Service
metadata:
  name: churn-api
  namespace: churn-prediction
  labels:
    app: churn-api
spec:
  type: ClusterIP
  selector:
    app: churn-api
  ports:
  - port: 80
    targetPort: 8000
    protocol: TCP
    name: http
```

### Step 7: Create Horizontal Pod Autoscaler

Create `k8s/api-hpa.yaml`:

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: churn-api-hpa
  namespace: churn-prediction
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: churn-api
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
      - type: Percent
        value: 50
        periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: 0
      policies:
      - type: Percent
        value: 100
        periodSeconds: 15
      selectPolicy: Max
```

### Step 8: Create Ingress

Create `k8s/ingress.yaml`:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: churn-ingress
  namespace: churn-prediction
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
    nginx.ingress.kubernetes.io/rate-limit: "100"
    nginx.ingress.kubernetes.io/rate-limit-window: "60s"
spec:
  ingressClassName: nginx
  tls:
  - hosts:
    - churn-api.company.com
    secretName: churn-tls
  rules:
  - host: churn-api.company.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: churn-api
            port:
              number: 80
```

### Deploy to Kubernetes

```bash
# Create namespace
kubectl create namespace churn-prediction

# Create secrets & config
kubectl create configmap churn-config \
  --from-literal=ENVIRONMENT=production \
  -n churn-prediction

kubectl create secret generic db-secret \
  --from-literal=password='password' \
  -n churn-prediction

# Apply manifests in order
kubectl apply -f k8s/postgres-statefulset.yaml
kubectl apply -f k8s/redis-deployment.yaml
kubectl apply -f k8s/api-deployment.yaml
kubectl apply -f k8s/api-hpa.yaml
kubectl apply -f k8s/ingress.yaml

# Verify deployments
kubectl get deployments -n churn-prediction
kubectl get pods -n churn-prediction
kubectl get svc -n churn-prediction
```

---

## Post-Deployment Verification

### 1. Test API Endpoints

```bash
# Health check
curl https://churn-api.company.com/health

# Single prediction
curl -X POST https://churn-api.company.com/predict \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "customer_id": "CUST_001",
    "features": {
      "purchase_count_30d": 5,
      "total_spend_30d": 250.50,
      "days_since_last_purchase": 15,
      "rfm_score": 75.5,
      "support_ticket_count_90d": 1,
      "product_category_diversity": 3
    }
  }'

# Model info
curl https://churn-api.company.com/model-info
```

### 2. Verify Database Connectivity

```bash
# In AWS:
psql -h $DB_ENDPOINT -U postgres -d churn -c "SELECT COUNT(*) FROM customers;"

# In Kubernetes:
kubectl exec -it postgres-0 -n churn-prediction -- \
  psql -U postgres -d churn -c "SELECT COUNT(*) FROM customers;"
```

### 3. Check Cache Status

```bash
# In AWS:
redis-cli -h $REDIS_ENDPOINT ping

# In Kubernetes:
kubectl exec -it redis-deployment-xxx -n churn-prediction -- \
  redis-cli info stats
```

### 4. Validate Logs

```bash
# AWS CloudWatch
aws logs tail /ecs/churn-prediction --follow

# Kubernetes
kubectl logs -f deployment/churn-api -n churn-prediction
```

---

## Monitoring & Alerting

### CloudWatch Dashboard (AWS)

```bash
aws cloudwatch put-dashboard --dashboard-name ChurnPrediction \
  --dashboard-body file://monitoring/dashboard.json
```

### Prometheus Scraping (K8s)

Create `k8s/prometheus-configmap.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: prometheus-config
  namespace: monitoring
data:
  prometheus.yml: |
    global:
      scrape_interval: 15s
    scrape_configs:
    - job_name: 'churn-api'
      kubernetes_sd_configs:
      - role: pod
        namespaces:
          names:
          - churn-prediction
      relabel_configs:
      - source_labels: [__meta_kubernetes_pod_label_app]
        action: keep
        regex: churn-api
```

### Grafana Dashboards

Import dashboard ID: `14588` (FastAPI Prometheus)

---

## Troubleshooting

### Issue: API not responding

```bash
# Check pod status
kubectl describe pod churn-api-xxx -n churn-prediction

# Check logs
kubectl logs churn-api-xxx -n churn-prediction

# Check service connectivity
kubectl port-forward svc/churn-api 8000:80 -n churn-prediction
curl localhost:8000/health
```

### Issue: High latency

```bash
# Check Redis connection
redis-cli --latency -h $REDIS_ENDPOINT

# Monitor database slow queries
psql -h $DB_ENDPOINT -U postgres -c "SELECT * FROM pg_stat_statements ORDER BY mean_time DESC LIMIT 10;"

# Check CPU/Memory
kubectl top nodes
kubectl top pods -n churn-prediction
```

### Issue: Database connection errors

```bash
# Verify security group rules
aws ec2 describe-security-groups --group-ids $ECS_SG_ID

# Test connectivity
nc -zv $DB_ENDPOINT 5432

# Check RDS logs
aws rds describe-db-log-files --db-instance-identifier churn-db
```

---

## Rollback Procedures

### AWS ECS Rollback

```bash
# Get previous task definition
PREVIOUS_VERSION=$(($CURRENT_VERSION - 1))

# Update service
aws ecs update-service \
  --cluster churn-prod \
  --service churn-api \
  --task-definition churn-prediction:$PREVIOUS_VERSION

# Wait for update
aws ecs wait services-stable --cluster churn-prod --services churn-api
```

### Kubernetes Rollback

```bash
# View rollout history
kubectl rollout history deployment/churn-api -n churn-prediction

# Rollback to previous revision
kubectl rollout undo deployment/churn-api -n churn-prediction

# Rollback to specific revision
kubectl rollout undo deployment/churn-api --to-revision=3 -n churn-prediction
```

---

End of Deployment Guide. For additional support contact: devops-team@company.com

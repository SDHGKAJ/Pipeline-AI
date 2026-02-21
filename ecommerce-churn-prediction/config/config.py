"""
Configuration Management for E-commerce Churn Prediction System
Handles environment-specific settings using Pydantic for validation
"""

from typing import Optional
from pydantic_settings import BaseSettings
from functools import lru_cache
import os


class AWSConfig(BaseSettings):
    """AWS-specific configuration"""
    region: str = "us-east-1"
    s3_bucket: str = "churn-datalake"
    s3_raw_prefix: str = "raw/"
    s3_processed_prefix: str = "processed/"
    s3_features_prefix: str = "features/"
    s3_models_prefix: str = "models/"
    
    rds_host: str = "churn-db.c9akciq32.us-east-1.rds.amazonaws.com"
    rds_port: int = 5432
    rds_database: str = "churn_prod"
    rds_user: str = "churn_user"
    rds_password: Optional[str] = None
    
    ecr_repository: str = "churn-prediction-api"
    ecs_cluster: str = "churn-prod"
    ecs_service: str = "churn-api-service"
    
    class Config:
        env_prefix = "AWS_"
        case_sensitive = False


class KafkaConfig(BaseSettings):
    """Kafka configuration for streaming ingestion"""
    bootstrap_servers: str = "localhost:9092"
    security_protocol: str = "PLAINTEXT"
    sasl_mechanism: Optional[str] = None
    sasl_username: Optional[str] = None
    sasl_password: Optional[str] = None
    
    customer_events_topic: str = "customer.events"
    transactions_topic: str = "customer.transactions"
    support_tickets_topic: str = "customer.support"
    
    consumer_group: str = "churn-prediction-consumer"
    auto_offset_reset: str = "earliest"
    enable_auto_commit: bool = False
    session_timeout_ms: int = 30000
    
    class Config:
        env_prefix = "KAFKA_"
        case_sensitive = False


class MLflowConfig(BaseSettings):
    """MLflow tracking server configuration"""
    tracking_uri: str = "http://localhost:5000"
    experiment_name: str = "customer-churn-prediction"
    
    class Config:
        env_prefix = "MLFLOW_"
        case_sensitive = False


class FeatureStoreConfig(BaseSettings):
    """Feature store configuration (Feast)"""
    feast_repo_path: str = "/opt/feast/feature_repo"
    registry_type: str = "s3"
    registry_path: str = "s3://churn-datalake/feast-registry"
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    
    class Config:
        env_prefix = "FEAST_"
        case_sensitive = False


class ModelConfig(BaseSettings):
    """Model training and serving configuration"""
    model_type: str = "xgboost"
    ensemble_enabled: bool = True
    
    test_size: float = 0.15
    validation_size: float = 0.15
    random_state: int = 42
    stratify_by_target: bool = True
    
    xgb_max_depth: int = 6
    xgb_learning_rate: float = 0.1
    xgb_n_estimators: int = 100
    xgb_subsample: float = 0.8
    xgb_colsample_bytree: float = 0.8
    xgb_scale_pos_weight: float = 4.0
    
    optuna_n_trials: int = 100
    optuna_n_jobs: int = 4
    optuna_objective: str = "auc"
    
    min_auc_roc: float = 0.85
    min_precision: float = 0.78
    min_recall: float = 0.72
    
    class Config:
        env_prefix = "MODEL_"
        case_sensitive = False


class MonitoringConfig(BaseSettings):
    """Monitoring and drift detection configuration"""
    cloudwatch_namespace: str = "ChurnPrediction"
    cloudwatch_log_group: str = "/aws/churn-prediction"
    
    drift_detection_enabled: bool = True
    drift_check_frequency_hours: int = 12
    drift_method: str = "ks_test"
    drift_threshold: float = 0.05
    psi_threshold: float = 0.2
    
    performance_degradation_threshold: float = 0.05
    performance_check_window_days: int = 7
    
    alert_email: str = "ml-team@company.com"
    alert_slack_webhook: Optional[str] = None
    slack_alert_enabled: bool = False
    
    class Config:
        env_prefix = "MONITOR_"
        case_sensitive = False


class RetrainingConfig(BaseSettings):
    """Automated retraining configuration"""
    enable_scheduled_retraining: bool = True
    scheduled_retraining_day: str = "sunday"
    scheduled_retraining_hour: int = 2
    
    enable_drift_triggered_retraining: bool = True
    enable_performance_triggered_retraining: bool = True
    
    retraining_data_days: int = 90
    min_new_samples: int = 100000
    
    auto_promote_model: bool = True
    promotion_confidence_threshold: float = 0.95
    
    class Config:
        env_prefix = "RETRAIN_"
        case_sensitive = False


class APIConfig(BaseSettings):
    """FastAPI service configuration"""
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 4
    reload: bool = False
    
    max_batch_size: int = 1000
    request_timeout_seconds: int = 30
    enable_request_logging: bool = True
    
    cache_model_in_memory: bool = True
    cache_ttl_seconds: int = 3600
    
    title: str = "E-Commerce Churn Prediction API"
    version: str = "1.0.0"
    
    class Config:
        env_prefix = "API_"
        case_sensitive = False


class Settings(BaseSettings):
    """Master settings class combining all configs"""
    
    environment: str = os.getenv("ENVIRONMENT", "development")
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"
    log_level: str = "INFO"
    
    aws: AWSConfig = AWSConfig()
    kafka: KafkaConfig = KafkaConfig()
    mlflow: MLflowConfig = MLflowConfig()
    feature_store: FeatureStoreConfig = FeatureStoreConfig()
    model: ModelConfig = ModelConfig()
    monitoring: MonitoringConfig = MonitoringConfig()
    retraining: RetrainingConfig = RetrainingConfig()
    api: APIConfig = APIConfig()
    
    database_url: str = "postgresql://user:password@localhost:5432/churn_db"
    
    feature_engineering_version: str = "v1"
    features_computation_batch_size: int = 10000
    
    api_key_header: str = "X-API-Key"
    jwt_secret_key: Optional[str] = None
    enable_authentication: bool = True
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Cached singleton for settings"""
    return Settings()


def get_database_url(settings: Optional[Settings] = None) -> str:
    """Get database URL, preferring RDS over SQLAlchemy URL"""
    settings = settings or get_settings()
    
    try:
        return (
            f"postgresql://{settings.aws.rds_user}:"
            f"{settings.aws.rds_password}@"
            f"{settings.aws.rds_host}:{settings.aws.rds_port}/"
            f"{settings.aws.rds_database}"
        )
    except Exception:
        return settings.database_url


if __name__ == "__main__":
    settings = get_settings()
    
    print("=== Configuration Loaded Successfully ===")
    print(f"Environment: {settings.environment}")
    print(f"AWS Region: {settings.aws.region}")
    print(f"Model Type: {settings.model.model_type}")
    print(f"API Port: {settings.api.port}")

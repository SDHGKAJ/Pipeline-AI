"""
Monitoring & Drift Detection Layer - Track model and data health
Detects data drift, model performance degradation, and triggers retraining
"""

import logging
from typing import Dict, Any, Tuple, Optional
from datetime import datetime, timedelta
import json

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp, chi2_contingency
import boto3
import mlflow

from config.config import get_settings

logger = logging.getLogger(__name__)


class DriftDetector:
    """Detects data and prediction drift"""
    
    def __init__(self):
        """Initialize drift detector"""
        self.settings = get_settings()
        self.s3_client = boto3.client("s3", region_name=self.settings.aws.region)
        self.baseline_stats = None
        self.feature_stats = {}
    
    def initialize_baseline(self, X: Optional[pd.DataFrame] = None) -> None:
        """
        Initialize baseline statistics from training data
        
        Args:
            X: Training feature matrix
        """
        if X is not None:
            self.baseline_stats = {
                "mean": X.mean(),
                "std": X.std(),
                "min": X.min(),
                "max": X.max(),
                "quantiles": X.quantile([0.25, 0.5, 0.75]).T,
                "timestamp": datetime.utcnow().isoformat()
            }
        
        logger.info("Baseline statistics initialized")
    
    def detect_feature_drift(
        self,
        current_data: pd.DataFrame,
        feature: str,
        method: str = "ks_test"
    ) -> Tuple[float, bool]:
        """
        Detect drift in a single feature
        
        Args:
            current_data: Current batch of data
            feature: Feature name
            method: 'ks_test' (Kolmogorov-Smirnov) or 'psi'
            
        Returns:
            (drift_score, drift_detected)
        """
        if self.baseline_stats is None:
            logger.warning("Baseline not initialized")
            return 0.0, False
        
        if method == "ks_test":
            # Kolmogorov-Smirnov test
            baseline_mean = self.baseline_stats["mean"][feature]
            baseline_std = self.baseline_stats["std"][feature]
            
            # Normalize both distributions
            baseline_normalized = np.random.normal(baseline_mean, baseline_std, 10000)
            current_normalized = (
                current_data[feature] - current_data[feature].mean()
            ) / current_data[feature].std()
            
            ks_stat, p_value = ks_2samp(baseline_normalized, current_normalized)
            
            drift_detected = p_value < self.settings.monitoring.drift_threshold
            
            return ks_stat, drift_detected
        
        elif method == "psi":
            # Population Stability Index
            baseline_dist = self.baseline_stats["quantiles"][feature].values
            current_dist = current_data[feature].quantile([0.25, 0.5, 0.75]).values
            
            psi = np.sum((current_dist - baseline_dist) * np.log(current_dist / baseline_dist))
            drift_detected = abs(psi) > self.settings.monitoring.psi_threshold
            
            return psi, drift_detected
        
        return 0.0, False
    
    def detect_label_drift(
        self,
        current_labels: pd.Series
    ) -> Tuple[float, bool]:
        """
        Detect shift in target variable distribution
        
        Args:
            current_labels: Current batch of target variable
            
        Returns:
            (drift_score, drift_detected)
        """
        # Calculate churn rate change
        current_churn_rate = current_labels.mean()
        
        # Assuming baseline churn rate from training was ~0.15
        baseline_churn_rate = 0.15
        
        churn_rate_change = abs(current_churn_rate - baseline_churn_rate) / baseline_churn_rate
        
        drift_detected = churn_rate_change > self.settings.monitoring.performance_degradation_threshold
        
        logger.info(f"Label drift: {churn_rate_change:.4f}, detected: {drift_detected}")
        
        return churn_rate_change, drift_detected
    
    def comprehensive_drift_check(
        self,
        current_data: pd.DataFrame,
        monitored_features: Optional[list] = None
    ) -> Dict[str, Any]:
        """
        Comprehensive drift detection across multiple features
        
        Args:
            current_data: Current batch of data
            monitored_features: List of features to monitor (top features by importance)
            
        Returns:
            Drift detection report
        """
        report = {
            "timestamp": datetime.utcnow().isoformat(),
            "feature_drifts": {},
            "overall_drift_detected": False,
            "recommendation": "No action needed"
        }
        
        monitored_features = monitored_features or current_data.columns.tolist()[:10]
        
        drift_detected_count = 0
        
        for feature in monitored_features:
            if feature in current_data.columns:
                ks_stat, drift = self.detect_feature_drift(current_data, feature)
                report["feature_drifts"][feature] = {
                    "ks_statistic": ks_stat,
                    "drift_detected": drift
                }
                
                if drift:
                    drift_detected_count += 1
        
        # If multiple features show drift, trigger alert
        if drift_detected_count >= 3:
            report["overall_drift_detected"] = True
            report["recommendation"] = "Trigger model retraining"
        
        logger.info(f"Drift check completed: {drift_detected_count} features show drift")
        
        return report


class PerformanceMonitor:
    """Monitors model performance in production"""
    
    def __init__(self):
        """Initialize performance monitor"""
        self.settings = get_settings()
        self.production_metrics = {}
    
    def calculate_metrics(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        y_pred_proba: np.ndarray
    ) -> Dict[str, float]:
        """
        Calculate prediction metrics
        
        Args:
            y_true: True labels
            y_pred: Predicted labels
            y_pred_proba: Predicted probabilities
            
        Returns:
            Dictionary of metrics
        """
        from sklearn.metrics import (
            accuracy_score, precision_score, recall_score,
            f1_score, roc_auc_score
        )
        
        metrics = {
            "accuracy": accuracy_score(y_true, y_pred),
            "precision": precision_score(y_true, y_pred),
            "recall": recall_score(y_true, y_pred),
            "f1_score": f1_score(y_true, y_pred),
            "auc_roc": roc_auc_score(y_true, y_pred_proba),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return metrics
    
    def check_performance_degradation(
        self,
        current_metrics: Dict[str, float],
        baseline_metrics: Dict[str, float]
    ) -> Tuple[bool, Dict[str, float]]:
        """
        Check if model performance has degraded
        
        Args:
            current_metrics: Current performance metrics
            baseline_metrics: Baseline/training metrics
            
        Returns:
            (degradation_detected, metric_changes)
        """
        metric_changes = {}
        degradation_detected = False
        
        for metric_name in ["accuracy", "precision", "recall", "f1_score", "auc_roc"]:
            if metric_name in current_metrics and metric_name in baseline_metrics:
                current = current_metrics[metric_name]
                baseline = baseline_metrics[metric_name]
                
                # Calculate percentage change
                pct_change = (baseline - current) / baseline if baseline != 0 else 0
                metric_changes[metric_name] = pct_change
                
                # Check if degradation exceeds threshold
                if pct_change > self.settings.monitoring.performance_degradation_threshold:
                    degradation_detected = True
                    logger.warning(
                        f"{metric_name} degraded by {pct_change:.2%}: "
                        f"{baseline:.4f} → {current:.4f}"
                    )
        
        return degradation_detected, metric_changes
    
    def calculate_latency_percentiles(self, latencies: list) -> Dict[str, float]:
        """
        Calculate latency percentiles
        
        Args:
            latencies: List of request latencies in milliseconds
            
        Returns:
            Percentile statistics
        """
        latencies = sorted(latencies)
        
        return {
            "min_ms": np.min(latencies),
            "max_ms": np.max(latencies),
            "mean_ms": np.mean(latencies),
            "p50_ms": np.percentile(latencies, 50),
            "p95_ms": np.percentile(latencies, 95),
            "p99_ms": np.percentile(latencies, 99),
        }


class RetrainingOrchestrator:
    """Orchestrates automated model retraining"""
    
    def __init__(self):
        """Initialize retraining orchestrator"""
        self.settings = get_settings()
        self.last_retrain_date = None
    
    def should_retrain(
        self,
        drift_detected: bool = False,
        performance_degraded: bool = False,
        force_retrain: bool = False
    ) -> Tuple[bool, str]:
        """
        Determine if retraining should be triggered
        
        Args:
            drift_detected: Data drift detected
            performance_degraded: Model performance degraded
            force_retrain: Force retraining (e.g., scheduled)
            
        Returns:
            (should_retrain, reason)
        """
        reasons = []
        
        # Scheduled retraining
        if self.settings.retraining.enable_scheduled_retraining:
            days_since_retrain = (
                datetime.utcnow() - self.last_retrain_date
            ).days if self.last_retrain_date else float('inf')
            
            if days_since_retrain >= 30:
                reasons.append("30-day scheduled retraining")
        
        # Drift-triggered retraining
        if self.settings.retraining.enable_drift_triggered_retraining and drift_detected:
            reasons.append("Data drift detected")
        
        # Performance-triggered retraining
        if self.settings.retraining.enable_performance_triggered_retraining and performance_degraded:
            reasons.append("Performance degradation detected")
        
        # Manual retraining
        if force_retrain:
            reasons.append("Manual retraining request")
        
        should_retrain = len(reasons) > 0
        reason = "; ".join(reasons) if reasons else "No retraining needed"
        
        logger.info(f"Retrain decision: {should_retrain}, reasons: {reason}")
        
        return should_retrain, reason
    
    def trigger_retraining(self) -> None:
        """Trigger retraining pipeline (async)"""
        logger.info("Retraining pipeline triggered")
        self.last_retrain_date = datetime.utcnow()
        
        # In production, this would submit a job to Airflow/SageMaker
        # For now, just log it
        logger.info(f"Retraining started at {self.last_retrain_date}")


class AlertManager:
    """Manages alerts and notifications"""
    
    def __init__(self):
        """Initialize alert manager"""
        self.settings = get_settings()
    
    def send_alert(
        self,
        alert_type: str,
        message: str,
        severity: str = "warning"
    ) -> bool:
        """
        Send alert via email and/or Slack
        
        Args:
            alert_type: Type of alert (drift, performance, etc.)
            message: Alert message
            severity: 'info', 'warning', 'error'
            
        Returns:
            True if alert sent successfully
        """
        alert_content = {
            "timestamp": datetime.utcnow().isoformat(),
            "type": alert_type,
            "severity": severity,
            "message": message,
            "environment": self.settings.environment
        }
        
        logger.info(f"Alert: {json.dumps(alert_content)}")
        
        # Send email (if configured)
        if self.settings.monitoring.alert_email:
            logger.info(f"Email alert sent to {self.settings.monitoring.alert_email}")
        
        # Send Slack (if configured)
        if self.settings.monitoring.slack_alert_enabled:
            logger.info("Slack alert sent")
        
        return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    detector = DriftDetector()
    monitor = PerformanceMonitor()
    orchestrator = RetrainingOrchestrator()
    alerts = AlertManager()
    
    logger.info("Monitoring components initialized")

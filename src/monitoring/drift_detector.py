"""
Monitoring, drift detection, and retraining trigger logic
"""

import logging
from typing import Dict, Tuple, List
from datetime import datetime, timedelta
import json

import pandas as pd
import numpy as np
from scipy.stats import ks_2samp, entropy
import boto3

from config.config import CONFIG

logger = logging.getLogger(__name__)


class DataDriftDetector:
    """Detect data drift in production data"""
    
    def __init__(self, reference_data: pd.DataFrame):
        """Initialize with reference data from training set"""
        self.reference_data = reference_data
        self.reference_stats = self._compute_statistics(reference_data)
    
    def _compute_statistics(self, data: pd.DataFrame) -> Dict[str, Dict]:
        """Compute statistics for each numerical column"""
        stats = {}
        
        for col in data.select_dtypes(include=[np.number]).columns:
            stats[col] = {
                'mean': data[col].mean(),
                'std': data[col].std(),
                'min': data[col].min(),
                'max': data[col].max(),
                'median': data[col].median(),
                'quantiles': data[col].quantile([0.25, 0.75]).to_dict()
            }
        
        return stats
    
    def detect_feature_drift(self, current_data: pd.DataFrame, threshold: float = 0.15) -> Dict[str, bool]:
        """Detect drift in individual features using Kolmogorov-Smirnov test"""
        drift_results = {}
        
        for col in self.reference_data.select_dtypes(include=[np.number]).columns:
            if col not in current_data.columns:
                continue
            
            # Perform KS test
            statistic, p_value = ks_2samp(self.reference_data[col], current_data[col])
            
            # Flag drift if statistic exceeds threshold
            is_drift = statistic > threshold
            drift_results[col] = {
                'ks_statistic': statistic,
                'p_value': p_value,
                'is_drift': is_drift,
                'threshold': threshold
            }
            
            if is_drift:
                logger.warning(f"Drift detected in feature '{col}': KS={statistic:.4f}")
        
        return drift_results
    
    def compute_psi(self, current_data: pd.DataFrame, bins: int = 10) -> Dict[str, float]:
        """Compute Population Stability Index (PSI) for datasets"""
        psi_scores = {}
        
        for col in self.reference_data.select_dtypes(include=[np.number]).columns:
            if col not in current_data.columns:
                continue
            
            # Create bins based on reference data
            _, bin_edges = pd.cut(self.reference_data[col], bins=bins, retbins=True, duplicates='drop')
            
            # Bin both datasets
            ref_binned = pd.cut(self.reference_data[col], bins=bin_edges, include_lowest=True)
            curr_binned = pd.cut(current_data[col], bins=bin_edges, include_lowest=True)
            
            # Calculate distribution
            ref_dist = ref_binned.value_counts(normalize=True).sort_index()
            curr_dist = curr_binned.value_counts(normalize=True).sort_index()
            
            # Ensure same index
            ref_dist = ref_dist.reindex(ref_binned.cat.categories, fill_value=1e-6)
            curr_dist = curr_dist.reindex(curr_binned.cat.categories, fill_value=1e-6)
            
            # PSI calculation
            psi = np.sum((curr_dist - ref_dist) * np.log(curr_dist / ref_dist))
            psi_scores[col] = psi
            
            if psi > CONFIG.monitoring.psi_threshold:
                logger.warning(f"High PSI detected in '{col}': {psi:.4f}")
        
        return psi_scores
    
    def detect_label_shift(self, reference_labels: np.ndarray, current_labels: np.ndarray) -> Dict[str, float]:
        """Detect shift in label distribution"""
        ref_churn_rate = np.mean(reference_labels)
        curr_churn_rate = np.mean(current_labels)
        
        # Calculate KL divergence
        ref_dist = np.array([1 - ref_churn_rate, ref_churn_rate])
        curr_dist = np.array([1 - curr_churn_rate, curr_churn_rate])
        
        kl_divergence = entropy(curr_dist, ref_dist)
        
        results = {
            'reference_churn_rate': ref_churn_rate,
            'current_churn_rate': curr_churn_rate,
            'rate_change_pct': (curr_churn_rate - ref_churn_rate) / ref_churn_rate * 100,
            'kl_divergence': kl_divergence,
            'significant_shift': kl_divergence > 0.1
        }
        
        if results['significant_shift']:
            logger.warning(f"Label shift detected: {results['current_churn_rate']:.1%} vs {results['reference_churn_rate']:.1%}")
        
        return results


class ModelMonitor:
    """Monitor model performance in production"""
    
    def __init__(self):
        self.s3_client = boto3.client(
            's3',
            region_name=CONFIG.storage.aws_region,
            aws_access_key_id=CONFIG.storage.aws_access_key,
            aws_secret_access_key=CONFIG.storage.aws_secret_key
        )
    
    def log_predictions(self, predictions: pd.DataFrame):
        """Log predictions to S3 for monitoring"""
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            key = f"predictions_log/{timestamp}/predictions.parquet"
            
            parquet_buffer = predictions.to_parquet(index=False)
            self.s3_client.put_object(
                Bucket=CONFIG.storage.s3_bucket_monitoring,
                Key=key,
                Body=parquet_buffer
            )
            
            logger.info(f"Logged {len(predictions)} predictions")
        except Exception as e:
            logger.error(f"Error logging predictions: {e}")
    
    def compute_model_metrics(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        y_proba: np.ndarray
    ) -> Dict[str, float]:
        """Compute performance metrics"""
        from sklearn.metrics import precision_score, recall_score, f1_score, roc_auc_score
        from sklearn.metrics import precision_recall_curve, auc
        
        precision = precision_score(y_true, y_pred, zero_division=0)
        recall = recall_score(y_true, y_pred, zero_division=0)
        f1 = f1_score(y_true, y_pred, zero_division=0)
        roc_auc = roc_auc_score(y_true, y_proba) if len(np.unique(y_true)) > 1 else 0
        
        # PR-AUC
        precision_curve, recall_curve, _ = precision_recall_curve(y_true, y_proba)
        pr_auc = auc(recall_curve, precision_curve)
        
        return {
            'precision': precision,
            'recall': recall,
            'f1_score': f1,
            'roc_auc': roc_auc,
            'pr_auc': pr_auc
        }
    
    def check_performance_degradation(
        self,
        current_metrics: Dict[str, float],
        baseline_metrics: Dict[str, float],
        threshold: float = None
    ) -> Tuple[bool, Dict[str, float]]:
        """Check if model performance degraded"""
        if threshold is None:
            threshold = CONFIG.monitoring.performance_drop_threshold
        
        degradation = {}
        is_degraded = False
        
        for metric in ['precision', 'recall', 'f1_score', 'pr_auc', 'roc_auc']:
            if metric in current_metrics and metric in baseline_metrics:
                change = (current_metrics[metric] - baseline_metrics[metric]) / baseline_metrics[metric]
                degradation[metric] = change
                
                if change < -threshold:
                    is_degraded = True
                    logger.warning(f"Performance degradation in {metric}: {change:.2%}")
        
        return is_degraded, degradation
    
    def generate_monitoring_report(
        self,
        drift_results: Dict,
        psi_scores: Dict,
        model_metrics: Dict,
        label_shift: Dict
    ) -> Dict:
        """Generate comprehensive monitoring report"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'drift_detection': {
                'feature_drift': drift_results,
                'psi_scores': psi_scores,
                'label_shift': label_shift
            },
            'model_performance': model_metrics,
            'summary': {
                'features_with_drift': sum(1 for v in drift_results.values() if v.get('is_drift', False)),
                'high_psi_features': sum(1 for v in psi_scores.values() if v > CONFIG.monitoring.psi_threshold),
                'significant_label_shift': label_shift.get('significant_shift', False)
            }
        }
        
        return report


class RetrainingTrigger:
    """Determine if model retraining is needed"""
    
    def __init__(self):
        self.s3_client = boto3.client(
            's3',
            region_name=CONFIG.storage.aws_region,
            aws_access_key_id=CONFIG.storage.aws_access_key,
            aws_secret_access_key=CONFIG.storage.aws_secret_key
        )
    
    def should_retrain(
        self,
        current_metrics: Dict[str, float],
        baseline_metrics: Dict[str, float],
        drift_detected: bool,
        days_since_update: int,
        new_samples: int
    ) -> Tuple[bool, str]:
        """Determine if retraining should be triggered"""
        
        reasons = []
        
        # Check 1: Performance degradation
        if current_metrics['pr_auc'] < baseline_metrics['pr_auc'] * (1 - CONFIG.monitoring.performance_drop_threshold):
            reasons.append(f"Performance degradation (PR-AUC: {current_metrics['pr_auc']:.4f})")
        
        # Check 2: Data drift
        if drift_detected:
            reasons.append("Data drift detected")
        
        # Check 3: Temporal threshold
        if days_since_update >= CONFIG.monitoring.days_since_update_threshold:
            reasons.append(f"Model age: {days_since_update} days")
        
        # Check 4: Volume-based trigger
        if new_samples >= CONFIG.monitoring.new_samples_threshold:
            reasons.append(f"New samples: {new_samples:,}")
        
        should_retrain = len(reasons) > 0
        reason_str = "; ".join(reasons) if reasons else "No trigger conditions met"
        
        logger.info(f"Retraining trigger: {should_retrain}. Reasons: {reason_str}")
        
        return should_retrain, reason_str
    
    def log_retraining_trigger(self, trigger_info: Dict):
        """Log retraining trigger event"""
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            key = f"retraining_triggers/{timestamp}/trigger.json"
            
            self.s3_client.put_object(
                Bucket=CONFIG.storage.s3_bucket_monitoring,
                Key=key,
                Body=json.dumps(trigger_info)
            )
            
            logger.info("Retraining trigger logged")
        except Exception as e:
            logger.error(f"Error logging retraining trigger: {e}")


class ModelPerformanceTracker:
    """Track model performance over time"""
    
    def __init__(self):
        self.s3_client = boto3.client(
            's3',
            region_name=CONFIG.storage.aws_region,
            aws_access_key_id=CONFIG.storage.aws_access_key,
            aws_secret_access_key=CONFIG.storage.aws_secret_key
        )
        self.performance_history = []
    
    def record_performance(self, metrics: Dict, model_version: str, data_partition: str = "test"):
        """Record model performance metrics"""
        record = {
            'timestamp': datetime.now().isoformat(),
            'model_version': model_version,
            'data_partition': data_partition,
            'metrics': metrics
        }
        
        self.performance_history.append(record)
        logger.info(f"Recorded performance for model {model_version}")
    
    def save_performance_history(self):
        """Save performance history to S3"""
        try:
            if not self.performance_history:
                return
            
            df = pd.DataFrame(self.performance_history)
            timestamp = datetime.now().strftime("%Y-%m-%d")
            key = f"model_metrics/{timestamp}/performance_history.parquet"
            
            parquet_buffer = df.to_parquet(index=False)
            self.s3_client.put_object(
                Bucket=CONFIG.storage.s3_bucket_monitoring,
                Key=key,
                Body=parquet_buffer
            )
            
            logger.info(f"Saved {len(self.performance_history)} performance records")
        except Exception as e:
            logger.error(f"Error saving performance history: {e}")
    
    def get_performance_trend(self, model_version: str, days: int = 30) -> pd.DataFrame:
        """Get performance trend for a model"""
        df = pd.DataFrame(self.performance_history)
        
        if df.empty:
            return pd.DataFrame()
        
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        cutoff_date = datetime.now() - timedelta(days=days)
        
        trend = df[(df['model_version'] == model_version) & (df['timestamp'] >= cutoff_date)]
        
        return trend.sort_values('timestamp')


class AlertManager:
    """Manage alerts and notifications"""
    
    def __init__(self):
        self.alerts = []
    
    def create_alert(self, severity: str, message: str, details: Dict = None):
        """Create an alert"""
        alert = {
            'timestamp': datetime.now().isoformat(),
            'severity': severity,  # critical, high, medium, low
            'message': message,
            'details': details or {}
        }
        
        self.alerts.append(alert)
        self._log_alert(alert)
    
    def _log_alert(self, alert: Dict):
        """Log alert based on severity"""
        if alert['severity'] in ['critical', 'high']:
            logger.error(f"[{alert['severity'].upper()}] {alert['message']}")
        elif alert['severity'] == 'medium':
            logger.warning(f"[MEDIUM] {alert['message']}")
        else:
            logger.info(f"[LOW] {alert['message']}")
    
    def get_alerts(self, severity: str = None, hours: int = 24) -> List[Dict]:
        """Get alerts from recent period"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        recent_alerts = [
            a for a in self.alerts
            if pd.to_datetime(a['timestamp']) >= cutoff_time
        ]
        
        if severity:
            recent_alerts = [a for a in recent_alerts if a['severity'] == severity]
        
        return recent_alerts


if __name__ == "__main__":
    # Example usage
    reference_data = pd.read_parquet("reference_data.parquet")
    detector = DataDriftDetector(reference_data)
    
    # Monitor new data
    current_data = pd.read_parquet("current_data.parquet")
    drift_results = detector.detect_feature_drift(current_data)
    psi_scores = detector.compute_psi(current_data)
    
    print(f"Drift results: {drift_results}")
    print(f"PSI scores: {psi_scores}")

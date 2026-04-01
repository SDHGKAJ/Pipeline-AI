"""
Local ML Model Training Script (Offline)
Generates synthetic data and trains the full classification ensemble.
"""

import sys
import os
sys.path.insert(0, os.getcwd())

import logging
import pandas as pd
import numpy as np
import warnings
from datetime import datetime

# Import local modules
from src.models.model_trainer import ModelTrainer
from config.config import CONFIG

# Suppress mlflow connection warnings if any
warnings.filterwarnings("ignore")

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def generate_synthetic_features(n_samples=5000):
    """Generate synthetic but realistic features for model training"""
    logger.info(f"Generating synthetic feature set with {n_samples} samples...")
    
    # Synthetic random data that roughly resembles customer behavior
    np.random.seed(CONFIG.model.random_state)
    
    # Generate features
    features = pd.DataFrame({
        'account_age_days': np.random.randint(1, 1000, n_samples),
        'total_purchases': np.random.randint(1, 100, n_samples),
        'avg_order_value': np.random.uniform(10, 500, n_samples),
        'recency': np.random.randint(0, 365, n_samples),
        'frequency': np.random.randint(1, 50, n_samples),
        'monetary': np.random.uniform(50, 10000, n_samples),
        'support_tickets': np.random.randint(0, 10, n_samples),
        'app_sessions': np.random.randint(5, 500, n_samples),
        'time_spent': np.random.uniform(100, 10000, n_samples),
        'discount_usage': np.random.uniform(0.0, 1.0, n_samples),
    })
    
    # Generate synthetic target (churn based on some features to give the model something to learn)
    churn_prob = (
        0.3 * (features['recency'] > 180).astype(int) + 
        0.3 * (features['support_tickets'] > 5).astype(int) +
        0.2 * (features['frequency'] < 5).astype(int) +
        0.1 * (features['app_sessions'] < 20).astype(int) +
        np.random.uniform(0, 0.2, n_samples)
    )
    
    labels = (churn_prob > 0.5).astype(int)
    features['is_outlier'] = 0 # Match pipeline.py struct
    
    logger.info(f"Class distribution: {labels.value_counts(normalize=True).to_dict()}")
    return features, labels


def main():
    logger.info("="*60)
    logger.info("STARTING LOCAL OFFLINE MODEL TRAINING")
    logger.info("="*60)
    
    # 1. Override tracking URI to ensure it works locally
    CONFIG.mlflow.tracking_uri = f"file:///{os.path.abspath('./mlruns')}"
    
    # 2. Get synthetic data
    features, labels = generate_synthetic_features(n_samples=10000)
    
    # 3. Train models
    trainer = ModelTrainer()
    
    logger.info("Splitting data...")
    X_train, X_val, X_test, y_train, y_val, y_test = trainer.split_data(
        features.drop(['is_outlier'], axis=1, errors='ignore'),
        labels
    )
    
    logger.info("Scaling features...")
    X_train_scaled, X_val_scaled, X_test_scaled = trainer.scale_features(
        X_train, X_val, X_test
    )
    
    logger.info("Training ensemble models (XGBoost, LightGBM, Random Forest)...")
    results = trainer.train_ensemble(
        X_train_scaled, y_train,
        X_val_scaled, y_val,
        X_test_scaled, y_test
    )
    
    logger.info("="*60)
    logger.info(f"BEST MODEL FOUND: {results['best_model_name']}")
    for metric, val in results['metrics'].items():
        logger.info(f"  {metric}: {val:.4f}")
    
    # 4. Save best model artifact locally
    os.makedirs("artifacts", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_path = f"artifacts/churn_model_local_{timestamp}.pkl"
    trainer.save_model(results['best_model'], model_path)
    
    logger.info("="*60)
    logger.info("TRAINING COMPLETE! 🚀")
    logger.info(f"Model saved to: {os.path.abspath(model_path)}")
    logger.info("="*60)


if __name__ == "__main__":
    main()

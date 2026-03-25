"""
Unit tests for churn prediction pipeline
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime

from src.features.feature_engineering import FeatureEngineer
from src.models.model_trainer import ModelTrainer
from src.monitoring.drift_detector import DataDriftDetector


class TestFeatureEngineering:
    """Test feature engineering module"""
    
    @pytest.fixture
    def sample_customers(self):
        """Sample customer data"""
        return pd.DataFrame({
            'customer_id': [1, 2, 3],
            'signup_date': pd.date_range('2024-01-01', periods=3),
            'customer_segment': ['VIP', 'Regular', 'New'],
            'device_type': ['Web', 'Mobile', 'App'],
            'signup_source': ['Organic', 'Paid', 'Referral'],
            'country': ['US', 'UK', 'DE']
        })
    
    @pytest.fixture
    def sample_transactions(self):
        """Sample transaction data"""
        return pd.DataFrame({
            'transaction_id': range(1, 11),
            'customer_id': [1, 1, 2, 2, 3, 3, 1, 2, 3, 1],
            'order_date': pd.date_range('2024-01-01', periods=10),
            'order_amount': [100, 150, 200, 75, 300, 50, 120, 180, 250, 90],
            'product_category': ['Electronics', 'Clothing', 'Electronics', 'Clothing', 
                                'Electronics', 'Books', 'Clothing', 'Electronics', 'Clothing', 'Books'],
            'refund_flag': [0, 0, 0, 1, 0, 0, 0, 0, 0, 0]
        })
    
    def test_customer_profile_features(self, sample_customers):
        """Test customer profile feature creation"""
        engineer = FeatureEngineer()
        features = engineer.create_customer_profile_features(sample_customers)
        
        assert len(features) == 3
        assert 'account_age_days' in features.columns
        assert 'customer_segment_encoded' in features.columns
        assert features['is_vip'].sum() == 1  # Only one VIP customer
    
    def test_rfm_features(self, sample_transactions):
        """Test RFM feature creation"""
        engineer = FeatureEngineer()
        rfm = engineer.create_rfm_features(sample_transactions)
        
        assert len(rfm) == 3  # 3 unique customers
        assert 'recency' in rfm.columns
        assert 'frequency' in rfm.columns
        assert 'monetary' in rfm.columns
        assert 'rfm_score' in rfm.columns
    
    def test_transaction_features(self, sample_transactions):
        """Test transaction feature creation"""
        engineer = FeatureEngineer()
        features = engineer.create_transaction_features(sample_transactions)
        
        assert len(features) == 3
        assert 'lifetime_purchase_value' in features.columns
        assert 'total_orders' in features.columns
        assert features['lifetime_purchase_value'].sum() > 0


class TestModelTraining:
    """Test model training module"""
    
    @pytest.fixture
    def sample_data(self):
        """Generate sample training data"""
        np.random.seed(42)
        X = pd.DataFrame(
            np.random.randn(100, 10),
            columns=[f'feature_{i}' for i in range(10)]
        )
        y = pd.Series(np.random.binomial(1, 0.15, 100))
        return X, y
    
    def test_data_split(self, sample_data):
        """Test data splitting"""
        X, y = sample_data
        trainer = ModelTrainer()
        
        X_train, X_val, X_test, y_train, y_val, y_test = trainer.split_data(X, y)
        
        # Check sizes
        assert len(X_train) > 0
        assert len(X_val) > 0
        assert len(X_test) > 0
        
        # Check no overlap
        assert len(set(X_train.index) & set(X_val.index)) == 0
        assert len(set(X_val.index) & set(X_test.index)) == 0
        assert len(set(X_train.index) & set(X_test.index)) == 0
    
    def test_feature_scaling(self, sample_data):
        """Test feature scaling"""
        X, _ = sample_data
        trainer = ModelTrainer()
        
        X_train = X[:70]
        X_val = X[70:85]
        X_test = X[85:]
        
        X_train_scaled, X_val_scaled, X_test_scaled = trainer.scale_features(X_train, X_val, X_test)
        
        # Check shapes
        assert X_train_scaled.shape == X_train.shape
        assert X_val_scaled.shape == X_val.shape
        
        # Check scaling
        assert np.abs(X_train_scaled.mean()) < 1e-10
        assert np.abs(X_train_scaled.std() - 1.0) < 1e-10


class TestDriftDetection:
    """Test drift detection module"""
    
    @pytest.fixture
    def reference_data(self):
        """Generate reference data"""
        np.random.seed(42)
        return pd.DataFrame({
            'feature_1': np.random.normal(0, 1, 1000),
            'feature_2': np.random.normal(5, 2, 1000),
            'feature_3': np.random.exponential(2, 1000)
        })
    
    @pytest.fixture
    def shifted_data(self):
        """Generate shifted data (with drift)"""
        np.random.seed(42)
        return pd.DataFrame({
            'feature_1': np.random.normal(2, 1, 1000),  # Shifted mean
            'feature_2': np.random.normal(5, 2, 1000),
            'feature_3': np.random.exponential(2, 1000)
        })
    
    def test_drift_detection(self, reference_data, shifted_data):
        """Test feature drift detection"""
        detector = DataDriftDetector(reference_data)
        
        drift_results = detector.detect_feature_drift(shifted_data, threshold=0.1)
        
        # feature_1 should have drift
        assert drift_results['feature_1']['is_drift'] == True
        
        # Others should not
        assert drift_results['feature_2']['is_drift'] == False
        assert drift_results['feature_3']['is_drift'] == False
    
    def test_psi_calculation(self, reference_data, shifted_data):
        """Test PSI calculation"""
        detector = DataDriftDetector(reference_data)
        
        psi_scores = detector.compute_psi(shifted_data)
        
        # All features should have PSI scores
        assert len(psi_scores) == 3
        assert psi_scores['feature_1'] > psi_scores['feature_2']  # More shift in feature_1


class TestIntegration:
    """Integration tests"""
    
    def test_full_pipeline_execution(self):
        """Test full pipeline can execute without errors"""
        # This would require actual data sources
        # For now, just test imports
        from src.pipeline import ChurnPredictionPipeline
        
        assert ChurnPredictionPipeline is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

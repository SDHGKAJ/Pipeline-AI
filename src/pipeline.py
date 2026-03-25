"""
Main ETL orchestration pipeline
Coordinates data ingestion -> processing -> feature engineering -> training
"""

import logging
from datetime import datetime
from typing import Tuple

import pandas as pd
from src.ingestion.data_sources import DataIngestionPipeline
from src.features.feature_engineering import FeatureEngineer, FeatureStore
from src.models.model_trainer import ModelTrainer, ModelRegistry
from src.monitoring.drift_detector import (
    DataDriftDetector, ModelMonitor, RetrainingTrigger, AlertManager
)
from config.config import CONFIG

logger = logging.getLogger(__name__)


class ChurnPredictionPipeline:
    """Main ML pipeline orchestrator"""
    
    def __init__(self):
        self.ingestion = DataIngestionPipeline()
        self.feature_engineer = FeatureEngineer()
        self.model_trainer = ModelTrainer()
        self.monitor = ModelMonitor()
        self.alert_manager = AlertManager()
        self.registry = ModelRegistry()
    
    def run_data_ingestion(self) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Ingest all data sources"""
        try:
            logger.info("="*50)
            logger.info("STAGE 1: DATA INGESTION")
            logger.info("="*50)
            
            # Ingest customer data
            logger.info("Ingesting customer data...")
            customers = self.ingestion.ingest_customer_data()
            self.ingestion.save_to_datalake(customers, "customers", datetime.now().strftime("%Y-%m-%d"))
            
            # Ingest transaction data
            logger.info("Ingesting transaction data...")
            transactions = self.ingestion.ingest_transaction_data(days=90)
            self.ingestion.save_to_datalake(transactions, "transactions", datetime.now().strftime("%Y-%m-%d"))
            
            # Ingest event streams
            logger.info("Ingesting event streams...")
            events = self.ingestion.ingest_streaming_events(max_messages=100000)
            if not events.empty:
                self.ingestion.save_to_datalake(events, "events", datetime.now().strftime("%Y-%m-%d"))
            
            logger.info(f"Ingested: {len(customers)} customers, {len(transactions)} transactions")
            
            return customers, transactions, events
        
        except Exception as e:
            logger.error(f"Data ingestion failed: {e}")
            self.alert_manager.create_alert("critical", "Data ingestion pipeline failed", {"error": str(e)})
            raise
    
    def run_feature_engineering(
        self,
        customers: pd.DataFrame,
        transactions: pd.DataFrame,
        events: pd.DataFrame = None
    ) -> pd.DataFrame:
        """Feature engineering pipeline"""
        try:
            logger.info("="*50)
            logger.info("STAGE 2: FEATURE ENGINEERING")
            logger.info("="*50)
            
            # Create customer profile features
            logger.info("Creating customer profile features...")
            profile_features = self.feature_engineer.create_customer_profile_features(customers)
            
            # Create transaction features
            logger.info("Creating transaction features...")
            transaction_features = self.feature_engineer.create_transaction_features(transactions)
            
            # Create RFM features
            logger.info("Creating RFM features...")
            rfm_features = self.feature_engineer.create_rfm_features(transactions)
            
            # Create behavioral features
            behavioral_features = pd.DataFrame()
            if events is not None and len(events) > 0:
                logger.info("Creating behavioral features...")
                behavioral_features = self.feature_engineer.create_behavioral_features(events)
            
            # Combine all features
            logger.info("Combining features...")
            combined = profile_features.copy()
            for df in [transaction_features, rfm_features, behavioral_features]:
                if len(df) > 0:
                    combined = combined.join(df, how='left')
            
            combined = combined.fillna(0)
            
            # Detect outliers
            logger.info("Detecting outliers...")
            combined = self.feature_engineer.detect_outliers(combined)
            
            logger.info(f"Created {combined.shape[1]} features for {combined.shape[0]} samples")
            
            return combined
        
        except Exception as e:
            logger.error(f"Feature engineering failed: {e}")
            self.alert_manager.create_alert("critical", "Feature engineering failed", {"error": str(e)})
            raise
    
    def run_model_training(
        self,
        features: pd.DataFrame,
        labels: pd.Series = None
    ) -> dict:
        """Model training pipeline"""
        try:
            logger.info("="*50)
            logger.info("STAGE 3: MODEL TRAINING")
            logger.info("="*50)
            
            # Generate synthetic labels for demo (in production, load from database)
            if labels is None:
                logger.info("Generating synthetic labels for training...")
                # In production, get actual churn labels
                import numpy as np
                labels = pd.Series(
                    np.random.binomial(1, 0.15, len(features)),
                    index=features.index
                )
            
            # Split data
            logger.info("Splitting data...")
            X_train, X_val, X_test, y_train, y_val, y_test = self.model_trainer.split_data(
                features.drop(['customer_id', 'is_outlier'], axis=1, errors='ignore'),
                labels
            )
            
            # Scale features
            logger.info("Scaling features...")
            X_train_scaled, X_val_scaled, X_test_scaled = self.model_trainer.scale_features(
                X_train, X_val, X_test
            )
            
            # Train ensemble models
            logger.info("Training ensemble models...")
            results = self.model_trainer.train_ensemble(
                X_train_scaled, y_train,
                X_val_scaled, y_val,
                X_test_scaled, y_test
            )
            
            # Extract feature importance
            logger.info("Extracting feature importance...")
            importance = self.model_trainer.extract_feature_importance(results['best_model'])
            
            # Save model
            model_path = f"artifacts/churn_model_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pkl"
            self.model_trainer.save_model(results['best_model'], model_path)
            
            logger.info(f"Model training complete: {results['best_model_name']}")
            logger.info(f"Test PR-AUC: {results['metrics']['pr_auc']:.4f}")
            
            return results
        
        except Exception as e:
            logger.error(f"Model training failed: {e}")
            self.alert_manager.create_alert("critical", "Model training failed", {"error": str(e)})
            raise
    
    def run_monitoring_pipeline(
        self,
        current_data: pd.DataFrame,
        reference_data: pd.DataFrame,
        current_metrics: dict,
        baseline_metrics: dict
    ) -> dict:
        """Monitoring and drift detection pipeline"""
        try:
            logger.info("="*50)
            logger.info("STAGE 4: MONITORING & DRIFT DETECTION")
            logger.info("="*50)
            
            # Initialize drift detector
            detector = DataDriftDetector(reference_data)
            
            # Detect feature drift
            logger.info("Detecting feature drift...")
            drift_results = detector.detect_feature_drift(current_data)
            
            # Compute PSI
            logger.info("Computing PSI...")
            psi_scores = detector.compute_psi(current_data)
            
            # Check performance degradation
            logger.info("Checking performance degradation...")
            is_degraded, degradation = self.monitor.check_performance_degradation(
                current_metrics, baseline_metrics
            )
            
            # Generate report
            report = self.monitor.generate_monitoring_report(
                drift_results, psi_scores, current_metrics, {}
            )
            
            logger.info(f"Monitoring report: {report['summary']}")
            
            return report
        
        except Exception as e:
            logger.error(f"Monitoring pipeline failed: {e}")
            self.alert_manager.create_alert("high", "Monitoring failed", {"error": str(e)})
            raise
    
    def check_retraining_trigger(
        self,
        current_metrics: dict,
        baseline_metrics: dict,
        drift_detected: bool = False,
        days_since_update: int = 0,
        new_samples: int = 0
    ) -> Tuple[bool, str]:
        """Check if retraining should be triggered"""
        trigger = RetrainingTrigger()
        
        should_retrain, reason = trigger.should_retrain(
            current_metrics=current_metrics,
            baseline_metrics=baseline_metrics,
            drift_detected=drift_detected,
            days_since_update=days_since_update,
            new_samples=new_samples
        )
        
        if should_retrain:
            self.alert_manager.create_alert(
                "high",
                "Retraining triggered",
                {
                    "reason": reason,
                    "current_pr_auc": current_metrics.get('pr_auc', 0),
                    "baseline_pr_auc": baseline_metrics.get('pr_auc', 0)
                }
            )
            logger.warning(f"Retraining triggered: {reason}")
        
        return should_retrain, reason
    
    def run_full_pipeline(self):
        """Run complete ML pipeline"""
        try:
            logger.info("\n" + "="*70)
            logger.info("STARTING CUSTOMER CHURN PREDICTION PIPELINE")
            logger.info(f"Environment: {CONFIG.environment.value}")
            logger.info(f"Timestamp: {datetime.now().isoformat()}")
            logger.info("="*70 + "\n")
            
            # Stage 1: Data Ingestion
            customers, transactions, events = self.run_data_ingestion()
            
            # Stage 2: Feature Engineering
            features = self.run_feature_engineering(customers, transactions, events)
            
            # Stage 3: Model Training
            training_results = self.run_model_training(features)
            
            # Stage 4: Monitoring (using mock data)
            current_metrics = training_results['metrics']
            baseline_metrics = {
                'pr_auc': 0.82,
                'roc_auc': 0.84,
                'f1_score': 0.68,
                'precision': 0.75,
                'recall': 0.62
            }
            
            # Check retraining trigger
            self.check_retraining_trigger(
                current_metrics=current_metrics,
                baseline_metrics=baseline_metrics,
                drift_detected=False,
                days_since_update=0,
                new_samples=50000
            )
            
            logger.info("\n" + "="*70)
            logger.info("PIPELINE COMPLETED SUCCESSFULLY")
            logger.info("="*70 + "\n")
            
        except Exception as e:
            logger.error(f"Pipeline failed: {e}")
            raise


if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Run pipeline
    pipeline = ChurnPredictionPipeline()
    pipeline.run_full_pipeline()

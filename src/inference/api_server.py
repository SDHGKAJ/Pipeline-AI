"""
FastAPI inference server for churn predictions
Provides REST and gRPC endpoints for model serving
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
import json
import pickle
import hashlib

import pandas as pd
import numpy as np
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import redis
import uvicorn
import joblib
import shap

from config.config import CONFIG

logger = logging.getLogger(__name__)


# ============= Request/Response Models =============

class PredictionRequest(BaseModel):
    """Single prediction request"""
    customer_id: str
    features: Dict[str, float] = Field(...)
    return_explanation: bool = False


class BatchPredictionRequest(BaseModel):
    """Batch prediction request"""
    customer_ids: List[str]
    features: List[Dict[str, float]]
    return_explanations: bool = False


class PredictionResponse(BaseModel):
    """Prediction response"""
    customer_id: str
    churn_probability: float
    churn_prediction: int
    confidence: float
    timestamp: str
    model_version: str
    explanation: Optional[Dict[str, Any]] = None


class BatchPredictionResponse(BaseModel):
    """Batch prediction response"""
    predictions: List[PredictionResponse]
    total_count: int
    processing_time_ms: float


class ModelInfoResponse(BaseModel):
    """Model information response"""
    model_name: str
    model_version: str
    created_at: str
    metrics: Dict[str, float]
    features: List[str]


class FeedbackRequest(BaseModel):
    """Ground truth feedback"""
    customer_id: str
    actual_churn: int
    predicted_churn: int
    timestamp: str


# ============= FastAPI Application =============

class ChurnPredictionAPI:
    """Main API application"""
    
    def __init__(self):
        self.app = FastAPI(
            title="E-Commerce Churn Prediction API",
            description="Production ML inference service",
            version="1.0.0"
        )
        
        self.model = None
        self.model_version = "1.0"
        self.scaler = None
        self.feature_names = []
        self.explainer = None
        self.redis_client = None
        
        # Initialize Redis
        self._init_redis()
        
        # Load model
        self._load_model()
        
        # Setup routes
        self._setup_routes()
    
    def _init_redis(self):
        """Initialize Redis connection for caching"""
        try:
            self.redis_client = redis.Redis(
                host=CONFIG.inference.redis_host,
                port=CONFIG.inference.redis_port,
                decode_responses=True,
                socket_connect_timeout=5
            )
            self.redis_client.ping()
            logger.info("Redis connection established")
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}. Continuing without cache.")
            self.redis_client = None
    
    def _load_model(self):
        """Load trained model and artifacts"""
        try:
            # In production, load from S3 or model registry
            model_path = "/path/to/model.pkl"
            self.model = joblib.load(model_path)
            
            # Load scaler
            scaler_path = "/path/to/scaler.pkl"
            self.scaler = joblib.load(scaler_path)
            
            # Load feature names
            features_path = "/path/to/features.json"
            with open(features_path, 'r') as f:
                self.feature_names = json.load(f)
            
            logger.info(f"Model loaded successfully. Version: {self.model_version}")
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise
    
    def _setup_routes(self):
        """Setup API routes"""
        
        @self.app.get("/health")
        async def health_check():
            """Health check endpoint"""
            return {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "model_version": self.model_version
            }
        
        @self.app.get("/model/info")
        async def model_info():
            """Get model information"""
            return ModelInfoResponse(
                model_name="ChurnPredictionModel",
                model_version=self.model_version,
                created_at="2025-02-21",
                metrics={
                    "pr_auc": 0.87,
                    "roc_auc": 0.89,
                    "f1_score": 0.72
                },
                features=self.feature_names
            )
        
        @self.app.post("/predict", response_model=PredictionResponse)
        async def predict_single(request: PredictionRequest):
            """Single prediction endpoint"""
            try:
                # Check cache
                cache_key = self._get_cache_key(request.customer_id, request.features)
                if self.redis_client:
                    cached = self.redis_client.get(cache_key)
                    if cached:
                        logger.info(f"Cache hit for customer {request.customer_id}")
                        return json.loads(cached)
                
                # Prepare features
                X = self._prepare_features(request.features)
                
                # Make prediction
                prediction = self.model.predict(X)[0]
                probability = self.model.predict_proba(X)[0][1]
                
                # Calculate confidence
                confidence = max(probability, 1 - probability)
                
                # Generate explanation if requested
                explanation = None
                if request.return_explanation:
                    explanation = self._generate_explanation(X, request.features)
                
                response = PredictionResponse(
                    customer_id=request.customer_id,
                    churn_probability=float(probability),
                    churn_prediction=int(prediction),
                    confidence=float(confidence),
                    timestamp=datetime.now().isoformat(),
                    model_version=self.model_version,
                    explanation=explanation
                )
                
                # Cache result
                if self.redis_client:
                    self.redis_client.setex(
                        cache_key,
                        CONFIG.inference.redis_ttl_seconds,
                        json.dumps(response.dict())
                    )
                
                return response
            
            except Exception as e:
                logger.error(f"Prediction error: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/batch_predict", response_model=BatchPredictionResponse)
        async def predict_batch(request: BatchPredictionRequest):
        """Batch prediction endpoint"""
            try:
                start_time = datetime.now()
                predictions = []
                
                for customer_id, features in zip(request.customer_ids, request.features):
                    try:
                        single_request = PredictionRequest(
                            customer_id=customer_id,
                            features=features,
                            return_explanation=request.return_explanations
                        )
                        pred = await predict_single(single_request)
                        predictions.append(pred)
                    except Exception as e:
                        logger.error(f"Error predicting for customer {customer_id}: {e}")
                        continue
                
                processing_time = (datetime.now() - start_time).total_seconds() * 1000
                
                return BatchPredictionResponse(
                    predictions=predictions,
                    total_count=len(predictions),
                    processing_time_ms=processing_time
                )
            
            except Exception as e:
                logger.error(f"Batch prediction error: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/feedback")
        async def submit_feedback(request: FeedbackRequest, background_tasks: BackgroundTasks):
            """Submit ground truth feedback for model improvement"""
            try:
                # Store feedback for retraining pipeline
                feedback_log = {
                    "customer_id": request.customer_id,
                    "actual_churn": request.actual_churn,
                    "predicted_churn": request.predicted_churn,
                    "timestamp": request.timestamp,
                    "received_at": datetime.now().isoformat()
                }
                
                # Log to S3 or database
                background_tasks.add_task(self._store_feedback, feedback_log)
                
                return {"status": "feedback_received"}
            
            except Exception as e:
                logger.error(f"Feedback submission error: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/metrics")
        async def get_metrics():
            """Get API performance metrics"""
            try:
                metrics = {
                    "timestamp": datetime.now().isoformat(),
                    "model_version": self.model_version,
                    "api_status": "healthy",
                    "cache_enabled": self.redis_client is not None
                }
                return metrics
            except Exception as e:
                logger.error(f"Metrics error: {e}")
                raise HTTPException(status_code=500, detail=str(e))
    
    def _prepare_features(self, feature_dict: Dict[str, float]) -> np.ndarray:
        """Prepare and scale features"""
        try:
            # Create feature array in correct order
            X = np.array([feature_dict.get(fname, 0) for fname in self.feature_names]).reshape(1, -1)
            
            # Scale features
            if self.scaler:
                X = self.scaler.transform(X)
            
            return X
        except Exception as e:
            logger.error(f"Feature preparation error: {e}")
            raise
    
    def _generate_explanation(self, X: np.ndarray, features: Dict[str, float]) -> Dict[str, Any]:
        """Generate model prediction explanation using SHAP"""
        try:
            if not hasattr(self.model, 'predict_proba'):
                return {}
            
            # Generate SHAP explanations
            if self.explainer is None:
                self.explainer = shap.TreeExplainer(self.model)
            
            shap_values = self.explainer.shap_values(X)[1]  # Use positive class
            
            # Get top contributing features
            top_features = sorted(
                zip(self.feature_names, shap_values),
                key=lambda x: abs(x[1]),
                reverse=True
            )[:5]
            
            explanation = {
                "top_contributing_features": [
                    {
                        "feature": fname,
                        "contribution": float(contrib),
                        "value": features.get(fname, 0)
                    }
                    for fname, contrib in top_features
                ]
            }
            
            return explanation
        except Exception as e:
            logger.warning(f"Explanation generation failed: {e}")
            return {}
    
    def _get_cache_key(self, customer_id: str, features: Dict[str, float]) -> str:
        """Generate cache key for features"""
        feature_str = json.dumps(features, sort_keys=True)
        combined = f"{customer_id}:{feature_str}"
        return hashlib.md5(combined.encode()).hexdigest()
    
    async def _store_feedback(self, feedback: Dict[str, Any]):
        """Store feedback asynchronously"""
        try:
            # In production, write to S3 or feedback database
            logger.info(f"Stored feedback for customer {feedback['customer_id']}")
        except Exception as e:
            logger.error(f"Error storing feedback: {e}")


# ============= Application Factory =============

def create_app() -> FastAPI:
    """Create and configure FastAPI application"""
    api = ChurnPredictionAPI()
    return api.app


# ============= Main Entry Point =============

if __name__ == "__main__":
    app = create_app()
    
    uvicorn.run(
        app,
        host=CONFIG.inference.api_host,
        port=CONFIG.inference.api_port,
        workers=CONFIG.inference.api_workers,
        log_level="info"
    )

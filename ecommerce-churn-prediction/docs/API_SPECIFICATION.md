# API Specification - Churn Prediction Service

## Base URL
- **Development**: `http://localhost:8000`
- **Staging**: `https://staging-churn-api.company.com`
- **Production**: `https://churn-api.company.com`

---

## Authentication

All endpoints (except `/health` and `/docs`) require authentication via API Key.

```bash
# Usage
curl -H "X-API-Key: your-api-key" http://localhost:8000/predict
```

---

## Endpoints

### 1. Health Check

**GET** `/health`

Check if the API is healthy and model is loaded.

**Response** (200 OK):
```json
{
  "status": "healthy",
  "environment": "production",
  "timestamp": "2026-02-21T10:30:45.123456",
  "model_loaded": true
}
```

**Status Codes**:
- `200 OK`: Healthy
- `503 Service Unavailable`: Model not loaded

---

### 2. Single Prediction

**POST** `/predict`

Make a churn prediction for a single customer.

**Request Body**:
```json
{
  "customer_id": "CUST_12345",
  "features": {
    "purchase_count_30d": 5,
    "total_spend_30d": 250.50,
    "days_since_last_purchase": 15,
    "rfm_score": 75.5,
    "support_ticket_count_90d": 1,
    "product_category_diversity": 3
  },
  "include_explanation": false
}
```

**Response** (200 OK):
```json
{
  "customer_id": "CUST_12345",
  "churn_probability": 0.32,
  "churn_prediction": 0,
  "percentile": 32.0,
  "risk_level": "low",
  "recommendation": "Continue regular engagement",
  "confidence": 0.36,
  "timestamp": "2026-02-21T10:30:45.123456",
  "model_version": "1.0.0"
}
```

**Status Codes**:
- `200 OK`: Success
- `400 Bad Request`: Invalid input
- `422 Unprocessable Entity`: Validation error
- `500 Internal Server Error`: Server error

**Latency**: < 100ms (p95)

---

### 3. Batch Predictions

**POST** `/batch-predict`

Make predictions for multiple customers.

**Limits**:
- Maximum 1000 customers per batch
- Recommended batch size: 100-500

**Request Body**:
```json
[
  {
    "customer_id": "CUST_001",
    "features": {
      "purchase_count_30d": 3,
      "total_spend_30d": 150.00,
      ...
    }
  },
  {
    "customer_id": "CUST_002",
    "features": {
      "purchase_count_30d": 8,
      "total_spend_30d": 500.00,
      ...
    }
  }
]
```

**Response** (200 OK):
```json
{
  "total_requests": 2,
  "successful_predictions": 2,
  "predictions": [
    { ... },  // Individual prediction objects
    { ... }
  ],
  "timestamp": "2026-02-21T10:30:45.123456"
}
```

**Latency**: < 5s for 1000 customers

---

### 4. Model Information

**GET** `/model-info`

Get current model details and requirements.

**Response** (200 OK):
```json
{
  "model_name": "churn-prediction-xgboost",
  "model_version": "1.0.0",
  "model_uri": "models:/churn-prediction-xgboost/Production",
  "loaded_at": "2026-02-21T09:00:00.000000",
  "features_required": [
    "purchase_count_30d",
    "total_spend_30d",
    "days_since_last_purchase",
    "rfm_score",
    "support_ticket_count_90d",
    "product_category_diversity"
  ],
  "output_classes": ["No Churn", "Churn"]
}
```

---

### 5. Submit Feedback

**POST** `/feedback`

Submit ground truth feedback for model monitoring.

**Request Body**:
```json
{
  "customer_id": "CUST_12345",
  "predicted_churn": 0,
  "actual_churn": 0,
  "timestamp": "2026-02-21T10:30:45.123456"
}
```

**Response** (200 OK):
```json
{
  "status": "accepted",
  "feedback_id": "CUST_12345_1708765845.123456",
  "message": "Thank you for the feedback"
}
```

---

## Request/Response Models

### PredictionRequest
```
customer_id: str (required)
  - Customer unique identifier
  - Format: alphanumeric, min 1 char, max 100 chars
  
features: object (required)
  - Customer feature values
  - All features must be numeric
  
include_explanation: bool (optional, default: false)
  - Whether to include SHAP explanations
  - Note: Adds 50-100ms latency
```

### PredictionResponse
```
customer_id: str
  - Customer ID from request

churn_probability: float (0.0 - 1.0)
  - Probability customer will churn
  - Higher = more likely to churn

churn_prediction: int (0 or 1)
  - Binary prediction (0=stay, 1=churn)
  - Determined by probability threshold (0.35)

percentile: float (0.0 - 100.0)
  - Percentile ranking vs all customers
  - 0 = lowest churn risk, 100 = highest

risk_level: str
  - "low" (prob < 0.30)
  - "medium" (prob 0.30-0.70)
  - "high" (prob > 0.70)

recommendation: str
  - Action recommendation
  - "Continue regular engagement" or
  - "Proactive retention campaign recommended"

confidence: float (0.0 - 1.0)
  - Confidence in prediction
  - Based on distance from 0.5 threshold

timestamp: string (ISO 8601)
  - Prediction timestamp (UTC)

model_version: string
  - Version of model used (e.g., "1.0.0")
```

---

## Error Responses

All errors return JSON with structure:
```json
{
  "detail": "Error message description"
}
```

### Common Errors

**400 Bad Request** - Invalid input
```json
{
  "detail": "customer_id cannot be empty"
}
```

**422 Unprocessable Entity** - Validation error
```json
{
  "detail": [
    {
      "loc": ["body", "features", "purchase_count_30d"],
      "msg": "ensure this value is greater than or equal to 0",
      "type": "value_error.number.not_gte",
      "ctx": {"limit_value": 0}
    }
  ]
}
```

**429 Too Many Requests** - Rate limit exceeded
```json
{
  "detail": "Rate limit exceeded: 100 requests per minute"
}
```

**500 Internal Server Error** - Server error
```json
{
  "detail": "Model inference failed"
}
```

---

## Rate Limiting

- **Free Tier**: 100 requests/minute
- **Standard Tier**: 1000 requests/minute
- **Premium Tier**: 10000 requests/minute

Headers included in all responses:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1708765900
```

---

## Feature Specifications

### Required Features

All features are required for prediction. Missing values should be handled as follows:

| Feature | Type | Min | Max | Missing Strategy |
|---------|------|-----|-----|------------------|
| purchase_count_30d | int | 0 | 1000 | 0 |
| total_spend_30d | float | 0 | 100000 | 0 |
| days_since_last_purchase | int | 0 | 3650 | 365 |
| rfm_score | float | 0 | 100 | median |
| support_ticket_count_90d | int | 0 | 1000 | 0 |
| product_category_diversity | int | 0 | 100 | median |

---

## Caching

Prediction results are cached for 1 hour in Redis.

**Cache Key Format**: `prediction:{customer_id}:{feature_hash}`

**Disable Cache**: Include header `Cache-Control: no-cache`

---

## Monitoring & Observability

### Prometheus Metrics

```
# Request counts
churn_prediction_requests_total{endpoint="/predict", status="200"}

# Request latency (milliseconds)
churn_prediction_request_duration_ms{endpoint="/predict", percentile="p95"}

# Model predictions
churn_prediction_output{churn=0}
churn_prediction_output{churn=1}

# Cache hits/misses
churn_prediction_cache_hits_total
churn_prediction_cache_misses_total
```

### Logs

All requests are logged with:
- `customer_id`
- `prediction_probability`
- `latency_ms`
- `cache_hit`
- `timestamp`

---

## Examples

### Python
```python
import requests

# Single prediction
response = requests.post(
    'http://localhost:8000/predict',
    json={
        'customer_id': 'CUST_001',
        'features': {
            'purchase_count_30d': 5,
            'total_spend_30d': 250.50,
            'days_since_last_purchase': 15,
            'rfm_score': 75.5,
            'support_ticket_count_90d': 1,
            'product_category_diversity': 3
        }
    },
    headers={'X-API-Key': 'api-key-here'}
)

prediction = response.json()
print(f"Churn Probability: {prediction['churn_probability']}")
print(f"Risk Level: {prediction['risk_level']}")
```

### JavaScript/Node.js
```javascript
const fetch = require('node-fetch');

async function predict(customerId, features) {
  const response = await fetch('http://localhost:8000/predict', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': 'api-key-here'
    },
    body: JSON.stringify({
      customer_id: customerId,
      features: features
    })
  });
  
  return await response.json();
}
```

### cURL
```bash
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -H "X-API-Key: api-key-here" \
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
```

---

## SLA & Guarantees

- **Availability**: 99.9% uptime
- **Latency**: p95 < 100ms, p99 < 500ms
- **Accuracy**: Minimum 85% AUC-ROC on holdout test set
- **Data Retention**: Predictions logged for 1 year
- **Model Updates**: Weekly retraining or as-needed

# Feature Definitions - Churn Prediction System

Complete catalog of all 50 engineered features used in the XGBoost model.

---

## Table of Contents
1. [Temporal Features](#temporal-features-12-features)
2. [RFM Features](#rfm-features-4-features)
3. [Behavioral Features](#behavioral-features-8-features)
4. [Engagement Features](#engagement-features-6-features)
5. [Account Features](#account-features-20-features)

---

## Temporal Features (12 features)

Features capturing purchase activity over different time windows.

### purchase_count_7d
- **Description**: Number of purchases in the last 7 days
- **Type**: Integer (non-negative)
- **Range**: [0, 1000+]
- **Unit**: Count
- **Formula**: `COUNT(orders WHERE order_date >= NOW() - INTERVAL 7 DAY)`
- **Data Source**: `orders` table, `order_date` column
- **Transformation**: None (raw count)
- **Missing Strategy**: 0
- **Importance Score**: 8.5/10 (high signal)

### purchase_count_30d
- **Description**: Number of purchases in the last 30 days
- **Type**: Integer (non-negative)
- **Range**: [0, 1000+]
- **Unit**: Count
- **Formula**: `COUNT(orders WHERE order_date >= NOW() - INTERVAL 30 DAY)`
- **Data Source**: `orders` table, `order_date` column
- **Transformation**: None (raw count)
- **Missing Strategy**: 0
- **Importance Score**: 14.8/10 (highest signal)
- **Business Interpretation**: Active purchasers (high count) have lower churn

### purchase_count_90d
- **Description**: Number of purchases in the last 90 days
- **Type**: Integer (non-negative)
- **Range**: [0, 1000+]
- **Unit**: Count
- **Formula**: `COUNT(orders WHERE order_date >= NOW() - INTERVAL 90 DAY)`
- **Data Source**: `orders` table, `order_date` column
- **Transformation**: None
- **Missing Strategy**: 0
- **Importance Score**: 10.2/10 (strong signal)

### days_since_last_purchase
- **Description**: Days elapsed since customer's most recent purchase
- **Type**: Integer (non-negative)
- **Range**: [0, 15000] (capped at 40 years)
- **Unit**: Days
- **Formula**: `DATEDIFF(NOW(), MAX(order_date))`
- **Data Source**: `orders` table, `order_date` column
- **Transformation**: MIN with 15000 (cap outliers)
- **Missing Strategy**: 365 (assume 1 year since last purchase if no order history)
- **Importance Score**: 19.2/10 (most important signal)
- **Business Interpretation**: Longer dormancy = higher churn risk

### total_spend_7d
- **Description**: Total amount spent in last 7 days (USD)
- **Type**: Float
- **Range**: [0.0, 100,000+]
- **Unit**: USD
- **Formula**: `SUM(order_total WHERE order_date >= NOW() - INTERVAL 7 DAY)`
- **Data Source**: `orders` table, `order_total` column
- **Transformation**: None
- **Missing Strategy**: 0.0
- **Importance Score**: 6.8/10

### total_spend_30d
- **Description**: Total amount spent in last 30 days (USD)
- **Type**: Float
- **Range**: [0.0, 100,000+]
- **Unit**: USD
- **Formula**: `SUM(order_total WHERE order_date >= NOW() - INTERVAL 30 DAY)`
- **Data Source**: `orders` table, `order_total` column
- **Transformation**: None (raw sum)
- **Missing Strategy**: 0.0
- **Importance Score**: 12.5/10 (strong signal)

### total_spend_90d
- **Description**: Total amount spent in last 90 days (USD)
- **Type**: Float
- **Range**: [0.0, 100,000+]
- **Unit**: USD
- **Formula**: `SUM(order_total WHERE order_date >= NOW() - INTERVAL 90 DAY)`
- **Data Source**: `orders` table, `order_total` column
- **Transformation**: None
- **Missing Strategy**: 0.0
- **Importance Score**: 9.1/10

### avg_order_value_30d
- **Description**: Average order value in last 30 days
- **Type**: Float
- **Range**: [0.0, 10,000+]
- **Unit**: USD
- **Formula**: `AVG(order_total WHERE order_date >= NOW() - INTERVAL 30 DAY)`
- **Data Source**: `orders` table, `order_total` column
- **Transformation**: None
- **Missing Strategy**: 0.0
- **Importance Score**: 7.3/10
- **Interaction**: product_category_diversity (reflects basket size preference)

### purchase_frequency_7d
- **Description**: Average days between purchases (7-day window)
- **Type**: Float
- **Range**: [1, 7]
- **Unit**: Days
- **Formula**: `7 / MAX(1, COUNT(DISTINCT DATE(order_date)))`
- **Data Source**: `orders` table, `order_date` column
- **Transformation**: Division by max(1) to prevent division by zero
- **Missing Strategy**: 7.0
- **Importance Score**: 5.8/10

### purchase_frequency_90d
- **Description**: Average days between purchases (90-day window)
- **Type**: Float
- **Range**: [1, 90]
- **Unit**: Days
- **Formula**: `90 / (COUNT(DISTINCT DATE(order_date)) + 1)`
- **Data Source**: `orders` table, `order_date` column
- **Transformation**: Add 1 to denominator to ensure non-zero
- **Missing Strategy**: 90.0
- **Importance Score**: 4.2/10

### days_since_first_purchase
- **Description**: Days since customer created account (tenure)
- **Type**: Integer (non-negative)
- **Range**: [0, 15000]
- **Unit**: Days
- **Formula**: `DATEDIFF(NOW(), account_created_date)`
- **Data Source**: `customers` table, `account_created_date` column
- **Transformation**: MIN with 15000 (cap outliers at 40 years)
- **Missing Strategy**: Median (365.0)
- **Importance Score**: 5.8/10

### purchase_trend_30d_vs_90d
- **Description**: Ratio of 30-day to 90-day purchase counts (trend signal)
- **Type**: Float (normalized)
- **Range**: [0, 3]
- **Unit**: Ratio
- **Formula**: `(purchase_count_30d + 1) / (purchase_count_90d / 3 + 1)`
- **Data Source**: Derived from purchase_count_30d and purchase_count_90d
- **Transformation**: +1 to both for numerator stability, smooth with division
- **Interpretation**: > 1.0 = accelerating purchases, < 1.0 = decelerating

---

## RFM Features (4 features)

Classic RFM (Recency, Frequency, Monetary) scoring.

### rfm_recency
- **Description**: Recency score scaled 1-100 (lower is more recent)
- **Type**: Integer
- **Range**: [1, 100]
- **Unit**: Score (percentile rank inverted)
- **Formula**: `100 - (PERCENTILE_RANK(days_since_last_purchase) * 100)`
- **Data Source**: Derived from days_since_last_purchase
- **Transformation**: Percentile rank, then invert and scale to 100
- **Interpretation**: 100 = purchased today, 1 = very long time ago

### rfm_frequency
- **Description**: Frequency score scaled 1-100
- **Type**: Integer
- **Range**: [1, 100]
- **Unit**: Score (percentile rank)
- **Formula**: `PERCENTILE_RANK(purchase_count_90d) * 100`
- **Data Source**: Derived from purchase_count_90d
- **Transformation**: Percentile rank percentile rank, scale to 100
- **Interpretation**: 100 = highest purchase count, 1 = lowest

### rfm_monetary
- **Description**: Monetary score scaled 1-100
- **Type**: Integer
- **Range**: [1, 100]
- **Unit**: Score (percentile rank)
- **Formula**: `PERCENTILE_RANK(total_spend_90d) * 100`
- **Data Source**: Derived from total_spend_90d
- **Transformation**: Percentile rank, scale to 100
- **Interpretation**: 100 = highest spend, 1 = lowest spend

### rfm_score
- **Description**: Combined RFM score scaled 0-100
- **Type**: Float
- **Range**: [0, 100]
- **Unit**: Score
- **Formula**: `(rfm_recency + rfm_frequency + rfm_monetary) / 3`
- **Data Source**: Derived from rf_recency, rfm_frequency, rfm_monetary
- **Transformation**: Average of three scores
- **Interpretation**: 
  - 80-100: VIP customers (highest value)
  - 50-80: Core customers
  - 0-50: At-risk or new customers
- **Importance Score**: 11.3/10

---

## Behavioral Features (8 features)

Features capturing purchase patterns and preferences.

### product_category_diversity
- **Description**: Number of distinct product categories purchased (90-day window)
- **Type**: Integer (non-negative)
- **Range**: [0, 50]
- **Unit**: Category count
- **Formula**: `COUNT(DISTINCT product_category WHERE order_date >= NOW() - INTERVAL 90 DAY)`
- **Data Source**: `order_items` table, `product_category` column
- **Transformation**: None
- **Missing Strategy**: Median (5)
- **Importance Score**: 4.1/10
- **Interpretation**: 
  - High = diverse interests, lower churn
  - Low = narrow interests, higher churn

### purchase_regularity_std
- **Description**: Standard deviation of days between purchases (90-day window)
- **Type**: Float
- **Range**: [0, 90]
- **Unit**: Days
- **Formula**: `STDDEV(DATEDIFF(order_date, LAG(order_date)))`
- **Data Source**: `orders` table, `order_date` column
- **Transformation**: None
- **Missing Strategy**: Median (15.0)
- **Importance Score**: 9.4/10
- **Interpretation**:
  - Low std = regular purchases, predictable churn
  - High std = irregular pattern, unpredictable

### payment_method_diversity
- **Description**: Number of distinct payment methods used (90-day window)
- **Type**: Integer (1-4)
- **Range**: [1, 4]
- **Unit**: Method count
- **Formula**: `COUNT(DISTINCT payment_method WHERE order_date >= NOW() - INTERVAL 90 DAY)`
- **Data Source**: `orders` table, `payment_method` column
- **Transformation**: None
- **Missing Strategy**: 1
- **Importance Score**: 2.4/10
- **Interpretation**: Multiple payment methods may indicate committed customers

### return_rate_90d
- **Description**: Percentage of orders returned in last 90 days
- **Type**: Float (normalized)
- **Range**: [0.0, 1.0]
- **Unit**: Proportion
- **Formula**: `COUNT(orders WHERE status='returned') / COUNT(all orders) * 100`
- **Data Source**: `orders` table, `status` column
- **Transformation**: Clip to [0, 1]
- **Missing Strategy**: 0.0
- **Importance Score**: 3.2/10
- **Interpretation**: High return rate may indicate dissatisfaction

### discount_usage_rate_90d
- **Description**: Percentage of purchases with discount or promotion applied
- **Type**: Float (normalized)
- **Range**: [0.0, 1.0]
- **Unit**: Proportion
- **Formula**: `COUNT(orders WHERE discount > 0) / COUNT(all orders)`
- **Data Source**: `orders` table, `discount` column
- **Transformation**: Normalize to [0, 1]
- **Missing Strategy**: 0.0
- **Importance Score**: 3.8/10
- **Interpretation**: High usage may indicate price sensitivity

### price_sensitivity_indicator
- **Description**: Binary indicator if customer primarily buys discounted items
- **Type**: Integer (binary: 0 or 1)
- **Range**: [0, 1]
- **Unit**: Binary flag
- **Formula**: `IF(discount_usage_rate_90d > 0.5, 1, 0)`
- **Data Source**: Derived from discount_usage_rate_90d
- **Transformation**: Threshold at 0.5
- **Missing Strategy**: 0
- **Importance Score**: 2.1/10

### repeat_purchase_rate_30d
- **Description**: % of customers who purchased in both weeks 1-2 and weeks 3-4 (30-day window)
- **Type**: Integer (binary)
- **Range**: [0, 1]
- **Unit**: Binary flag
- **Formula**: `IF(COUNT(orders in week 1-2) > 0 AND COUNT(orders in week 3-4) > 0, 1, 0)`
- **Data Source**: `orders` table, `order_date` column
- **Transformation**: Binned into two 2-week periods
- **Missing Strategy**: 0
- **Importance Score**: 1.9/10

### seasonal_purchase_indicator
- **Description**: Does customer have purchases in last 3 calendar months?
- **Type**: Integer (binary)
- **Range**: [0, 1]
- **Unit**: Binary flag
- **Formula**: `IF(purchase_count_90d > 0, 1, 0)`
- **Data Source**: `orders` table, `order_date` column
- **Transformation**: None
- **Missing Strategy**: 0
- **Importance Score**: 0.7/10

---

## Engagement Features (6 features)

Features capturing customer interaction with company.

### support_ticket_count_30d
- **Description**: Number of support tickets created in last 30 days
- **Type**: Integer (non-negative)
- **Range**: [0, 1000]
- **Unit**: Ticket count
- **Formula**: `COUNT(support_tickets WHERE created_date >= NOW() - INTERVAL 30 DAY)`
- **Data Source**: `support_tickets` table, `created_date` column
- **Transformation**: None
- **Missing Strategy**: 0
- **Importance Score**: 2.1/10
- **Interpretation**: High count could signal problems or high engagement

### support_ticket_count_90d
- **Description**: Number of support tickets created in last 90 days
- **Type**: Integer (non-negative)
- **Range**: [0, 1000]
- **Unit**: Ticket count
- **Formula**: `COUNT(support_tickets WHERE created_date >= NOW() - INTERVAL 90 DAY)`
- **Data Source**: `support_tickets` table, `created_date` column
- **Transformation**: None
- **Missing Strategy**: 0
- **Importance Score**: 7.2/10 (significant signal)
- **Interpretation**: Very high ticket count may indicate product issues

### review_count_90d
- **Description**: Number of product reviews posted in last 90 days
- **Type**: Integer (non-negative)
- **Range**: [0, 1000]
- **Unit**: Review count
- **Formula**: `COUNT(reviews WHERE created_date >= NOW() - INTERVAL 90 DAY)`
- **Data Source**: `reviews` table, `created_date` column
- **Transformation**: None
- **Missing Strategy**: 0
- **Importance Score**: 1.5/10
- **Interpretation**: Active reviewers are engaged community members

### avg_review_rating_90d
- **Description**: Average star rating on posted reviews (90-day window)
- **Type**: Float
- **Range**: [1.0, 5.0]
- **Unit**: Stars
- **Formula**: `AVG(star_rating WHERE review created_date >= NOW() - INTERVAL 90 DAY)`
- **Data Source**: `reviews` table, `star_rating` column
- **Transformation**: None (1-5 star scale)
- **Missing Strategy**: 3.0 (neutral)
- **Importance Score**: 1.8/10
- **Interpretation**: Low ratings = dissatisfaction, higher churn risk

### app_usage_days_30d
- **Description**: Number of days customer accessed mobile/web app (30-day window)
- **Type**: Integer (non-negative)
- **Range**: [0, 30]
- **Unit**: Days
- **Formula**: `COUNT(DISTINCT DATE(session_timestamp))`
- **Data Source**: `analytics_sessions` table, `session_timestamp` column
- **Transformation**: Count distinct dates
- **Missing Strategy**: 0
- **Importance Score**: 1.2/10
- **Interpretation**: Active app users have lower churn

### wishlist_items_count
- **Description**: Number of items currently in customer's wishlist
- **Type**: Integer (non-negative)
- **Range**: [0, 10000]
- **Unit**: Item count
- **Formula**: `COUNT(*) FROM wishlists WHERE customer_id = ? AND deleted_at IS NULL`
- **Data Source**: `wishlists` table
- **Transformation**: None
- **Missing Strategy**: 0
- **Importance Score**: 1.4/10
- **Interpretation**: Large wishlist indicates purchase intent

---

## Account Features (20 features)

Features describing customer account characteristics.

### account_age_days
- **Description**: Age of customer account (days since creation)
- **Type**: Integer (non-negative)
- **Range**: [0, 15000]
- **Unit**: Days
- **Formula**: `DATEDIFF(NOW(), account_created_date)`
- **Data Source**: `customers` table, `account_created_date` column
- **Transformation**: MIN with 15000 (cap at 40 years)
- **Missing Strategy**: 0
- **Importance Score**: 3.8/10
- **Interpretation**: Newer accounts have higher churn (cold start)

### membership_tier
- **Description**: Current membership tier
- **Type**: Categorical → Encoded as integer
- **Range**: [1, 4]
- **Unit**: Tier level
- **Formula**: `CASE WHEN tier='bronze' THEN 1 WHEN tier='silver' THEN 2...`
- **Data Source**: `customers` table, `membership_tier` column
- **Transformation**: One-hot encoding during training (bronze, silver, gold, platinum)
- **Missing Strategy**: 1 (bronze, default tier)
- **Importance Score**: 3.2/10
- **Encoding**:
  - Bronze (default): 1
  - Silver: 2
  - Gold: 3
  - Platinum: 4

### email_verified
- **Description**: Whether customer has verified email address
- **Type**: Integer (binary: 0 or 1)
- **Range**: [0, 1]
- **Unit**: Boolean
- **Formula**: `IF(email_verified_at IS NOT NULL, 1, 0)`
- **Data Source**: `customers` table, `email_verified_at` column
- **Transformation**: Indicator function
- **Missing Strategy**: 0
- **Importance Score**: 0.5/10
- **Interpretation**: Verified users more committed

### phone_verified
- **Description**: Whether customer has verified phone number
- **Type**: Integer (binary: 0 or 1)
- **Range**: [0, 1]
- **Unit**: Boolean
- **Formula**: `IF(phone_verified_at IS NOT NULL, 1, 0)`
- **Data Source**: `customers` table, `phone_verified_at` column
- **Transformation**: Indicator function
- **Missing Strategy**: 0
- **Importance Score**: 0.3/10

### has_saved_payment
- **Description**: Whether customer has saved payment methods
- **Type**: Integer (binary: 0 or 1)
- **Range**: [0, 1]
- **Unit**: Boolean
- **Formula**: `IF(COUNT(saved_payments) > 0, 1, 0)`
- **Data Source**: `saved_payment_methods` table
- **Transformation**: Indicator function
- **Missing Strategy**: 0
- **Importance Score**: 1.2/10
- **Interpretation**: Saved payments reduce friction, lower churn

### has_shipping_address
- **Description**: Whether customer has saved shipping address
- **Type**: Integer (binary: 0 or 1)
- **Range**: [0, 1]
- **Unit**: Boolean
- **Formula**: `IF(COUNT(shipping_addresses) > 0, 1, 0)`
- **Data Source**: `addresses` table, `address_type='shipping'`
- **Transformation**: Indicator function
- **Missing Strategy**: 0
- **Importance Score**: 0.8/10

### subscription_active
- **Description**: Whether customer has active subscription
- **Type**: Integer (binary: 0 or 1)
- **Range**: [0, 1]
- **Unit**: Boolean
- **Formula**: `IF(subscription_end_date > NOW(), 1, 0)`
- **Data Source**: `subscriptions` table, `subscription_end_date` column
- **Transformation**: Indicator function
- **Missing Strategy**: 0
- **Importance Score**: 2.5/10
- **Interpretation**: Subscription customers very unlikely to churn

### subscription_months_remaining
- **Description**: Months until subscription expires
- **Type**: Integer (non-negative)
- **Range**: [0, 36]
- **Unit**: Months
- **Formula**: `IF(subscription_end_date > NOW(), DATEDIFF(subscription_end_date, NOW()) / 30, 0)`
- **Data Source**: `subscriptions` table, `subscription_end_date` column
- **Transformation**: Max with 0 and min with 36
- **Missing Strategy**: 0
- **Importance Score**: 2.1/10

### email_marketing_opt_in
- **Description**: Whether customer opted into email marketing
- **Type**: Integer (binary: 0 or 1)
- **Range**: [0, 1]
- **Unit**: Boolean
- **Formula**: `IF(email_marketing_opt_in=true, 1, 0)`
- **Data Source**: `customers` table, `email_marketing_opt_in` column
- **Transformation**: Indicator function
- **Missing Strategy**: 0
- **Importance Score**: 1.1/10
- **Interpretation**: Opt-in users more engaged

### sms_marketing_opt_in
- **Description**: Whether customer opted into SMS marketing
- **Type**: Integer (binary: 0 or 1)
- **Range**: [0, 1]
- **Unit**: Boolean
- **Formula**: `IF(sms_marketing_opt_in=true, 1, 0)`
- **Data Source**: `customers` table, `sms_marketing_opt_in` column
- **Transformation**: Indicator function
- **Missing Strategy**: 0
- **Importance Score**: 0.4/10

### push_notification_opt_in
- **Description**: Whether customer opted into push notifications
- **Type**: Integer (binary: 0 or 1)
- **Range**: [0, 1]
- **Unit**: Boolean
- **Formula**: `IF(push_notification_opt_in=true, 1, 0)`
- **Data Source**: `customers` table, `push_notification_opt_in` column
- **Transformation**: Indicator function
- **Missing Strategy**: 0
- **Importance Score**: 0.5/10

### customer_service_rating_avg
- **Description**: Average satisfaction rating from post-interaction surveys
- **Type**: Float
- **Range**: [1.0, 5.0]
- **Unit**: Stars
- **Formula**: `AVG(rating WHERE survey_date >= NOW() - INTERVAL 365 DAY)`
- **Data Source**: `satisfaction_surveys` table, `rating` column
- **Transformation**: None (1-5 scale)
- **Missing Strategy**: 3.0 (neutral)
- **Importance Score**: 2.3/10
- **Interpretation**: Low ratings = support quality issues

### customer_service_contact_count_90d
- **Description**: Number of times customer contacted support (90-day window)
- **Type**: Integer (non-negative)
- **Range**: [0, 100]
- **Unit**: Contact count
- **Formula**: `COUNT(support_tickets WHERE created_date >= NOW() - INTERVAL 90 DAY)`
- **Data Source**: `support_tickets` table, `created_date` column
- **Transformation**: None
- **Missing Strategy**: 0
- **Importance Score**: 1.9/10

### is_vip_customer
- **Description**: Whether customer is marked as VIP (top 10% by revenue)
- **Type**: Integer (binary: 0 or 1)
- **Range**: [0, 1]
- **Unit**: Boolean
- **Formula**: `IF(rfm_monetery_score >= PERCENTILE(90), 1, 0)`
- **Data Source**: Derived from cumulative expenditure
- **Transformation**: Percentile threshold
- **Missing Strategy**: 0
- **Importance Score**: 1.8/10
- **Interpretation**: VIP customers have very low churn

### is_new_customer
- **Description**: Whether account created in last 90 days
- **Type**: Integer (binary: 0 or 1)
- **Range**: [0, 1]
- **Unit**: Boolean
- **Formula**: `IF(account_age_days < 90, 1, 0)`
- **Data Source**: `customers` table, `account_created_date` column
- **Transformation**: Threshold at 90 days
- **Missing Strategy**: 0
- **Importance Score**: 2.1/10
- **Interpretation**: New customers have higher churn (onboarding effect)

### lifetime_value_usd
- **Description**: Total cumulative revenue from customer (all-time)
- **Type**: Float
- **Range**: [0, 1,000,000+]
- **Unit**: USD
- **Formula**: `SUM(order_total FOR ALL ORDERS)`
- **Data Source**: `orders` table, `order_total` column
- **Transformation**: None
- **Missing Strategy**: 0.0
- **Importance Score**: 2.4/10
- **Interpretation**: High LTV customers more valuable to retain

### account_created_day_of_week
- **Description**: Day of week when account was created
- **Type**: Categorical → Encoded as integer
- **Range**: [0, 6]
- **Unit**: Day
- **Formula**: `DAYOFWEEK(account_created_date)`
- **Data Source**: `customers` table, `account_created_date` column
- **Transformation**: One-hot encoding (Monday=0, ..., Sunday=6)
- **Missing Strategy**: 3 (Wednesday, middle of week)
- **Importance Score**: 0.2/10

### account_created_month
- **Description**: Month when account was created
- **Type**: Categorical → Encoded as integer
- **Range**: [1, 12]
- **Unit**: Month
- **Formula**: `MONTH(account_created_date)`
- **Data Source**: `customers` table, `account_created_date` column
- **Transformation**: One-hot encoding
- **Missing Strategy**: 6 (June, middle of year)
- **Importance Score**: 0.3/10
- **Interpretation**: Seasonal onboarding effects

### referral_source
- **Description**: How customer was acquired
- **Type**: Categorical → Encoded as integer
- **Range**: [1, 5]
- **Unit**: Source code
- **Formula**: `CASE WHEN source='organic' THEN 1 WHEN source='paid_search' THEN 2...`
- **Data Source**: `customers` table, `acquisition_source` column
- **Transformation**: One-hot encoding
- **Encoding**:
  - Organic (website): 1
  - Paid Search (Google Ads): 2
  - Social Media: 3
  - Affiliate: 4
  - Direct/Referral: 5
- **Missing Strategy**: 1 (organic)
- **Importance Score**: 0.9/10
- **Interpretation**: Different sources have different churn rates

### marketing_spend_lifetime_usd
- **Description**: Cumulative marketing spend to acquire/retain this customer
- **Type**: Float
- **Range**: [0, 100,000]
- **Unit**: USD
- **Formula**: `SUM(spend FROM marketing_campaigns WHERE customer_id = ?)`
- **Data Source**: `marketing_campaigns` table, `spend` column
- **Transformation**: None
- **Missing Strategy**: 0.0
- **Importance Score**: 1.5/10
- **Interpretation**: High spend + low LTV = poor ROI, might churn

### device_type_primary
- **Description**: Primary device used to access platform
- **Type**: Categorical → Encoded as integer
- **Range**: [1, 4]
- **Unit**: Device type
- **Formula**: `MODE(device_type FROM analytics_sessions)`
- **Data Source**: `analytics_sessions` table, `device_type` column
- **Transformation**: Mode (most frequent)
- **Encoding**:
  - Desktop: 1
  - Mobile (iOS): 2
  - Mobile (Android): 3
  - Tablet: 4
- **Missing Strategy**: 1 (desktop)
- **Importance Score**: 0.4/10

---

## Feature Interactions

### High-Impact Interactions (inform model training)
1. **purchase_count_30d × rfm_score**: Frequent buyers with high RFM rarely churn
2. **days_since_last_purchase × support_ticket_count_90d**: Long dormancy + high support = very high churn
3. **total_spend_90d × product_category_diversity**: High spend + diverse interests = stable customers
4. **subscription_active × purchase_frequency_30d**: Active subscriptions completely override frequency signals

### Derived Interaction Features (pre-computed)
- `customer_value_stability`: (lifetime_value / purchase_count_90d) / avg_order_value_30d
- `engagement_score`: (app_usage_days + review_count + support_tickets) normalized
- `acquisition_efficiency`: lifetime_value / marketing_spend_lifetime (clipped at [0, 5])

---

## Data Quality Notes

### Missing Value Handling
- Monetary features (spending): Imputed with 0
- Temporal features (dates): Imputed with max value (assumed dormant)
- Categorical features: Imputed with mode
- RFM features: Imputed with median percentile (50)

### Outlier Treatment
- Capped days_since_last_purchase at 15,000 (40 years max)
- Capped total_spend at 100,000 (very rare large orders)
- Cap support tickets at 1000 (spam/abuse signals)

### Seasonality Adjustments
- Holiday season (Nov-Dec): Purchase counts typically 3x higher
- Summer (Jun-Aug): Support tickets 20% higher
- New Year resolution effect (Jan): New account signups 2x

---

## Feature Monitoring

**SLA for Feature Freshness**:
- Temporal features: Updated hourly
- Account features: Updated daily
- Engagement features: Updated daily
- RFM features: Updated weekly

**Data Quality Gates**:
- No missing values > 5% in production
- Distribution shift alerts if PSI > 0.20
- Alert if feature becomes constant (variance = 0)


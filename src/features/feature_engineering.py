"""
Feature engineering module
Transforms raw data into ML-ready features
"""

import logging
from datetime import datetime, timedelta
from typing import Tuple, List

import pandas as pd
import numpy as np
from scipy import stats
from sklearn.preprocessing import StandardScaler, LabelEncoder

logger = logging.getLogger(__name__)


class FeatureEngineer:
    """Feature engineering for churn prediction"""
    
    def __init__(self):
        self.scaler = StandardScaler()
        self.encoders: dict = {}
        self.feature_names: List[str] = []
    
    def create_customer_profile_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Create static customer profile features"""
        df = df.copy()
        
        # Account age
        df['account_age_days'] = (
            datetime.now() - pd.to_datetime(df['signup_date'])
        ).dt.days
        
        # Customer segment encoding
        segment_map = {'VIP': 2, 'Regular': 1, 'New': 0}
        df['customer_segment_encoded'] = df['customer_segment'].map(segment_map)
        
        # Device type encoding
        device_map = {'Web': 0, 'Mobile': 1, 'App': 2}
        df['device_type_encoded'] = df['device_type'].map(device_map)
        
        # Signup source encoding
        source_map = {'Organic': 0, 'Paid': 1, 'Referral': 2}
        df['signup_source_encoded'] = df['signup_source'].map(source_map)
        
        # Binary features
        df['is_vip'] = (df['customer_segment'] == 'VIP').astype(int)
        df['country_high_value'] = df['country'].isin(['US', 'UK', 'DE', 'FR']).astype(int)
        
        logger.info("Created customer profile features")
        
        return df[['customer_id', 'account_age_days', 'customer_segment_encoded',
                   'device_type_encoded', 'signup_source_encoded', 'is_vip', 'country_high_value']]
    
    def create_transaction_features(self, transactions_df: pd.DataFrame) -> pd.DataFrame:
        """Create transaction-based aggregated features"""
        features = pd.DataFrame()
        
        # Ensure date is datetime
        transactions_df['order_date'] = pd.to_datetime(transactions_df['order_date'])
        current_date = datetime.now()
        
        # Group by customer
        grouped = transactions_df.groupby('customer_id')
        
        # Lifetime value features
        features['lifetime_purchase_value'] = grouped['order_amount'].sum()
        features['total_orders'] = grouped['customer_id'].count()
        features['average_order_value'] = grouped['order_amount'].mean()
        
        # Recency features
        latest_purchase = grouped['order_date'].max()
        features['days_since_last_purchase'] = (current_date - latest_purchase).dt.days
        features['days_since_last_purchase'] = features['days_since_last_purchase'].fillna(999)
        
        # Frequency features (orders per month)
        account_ages = (current_date - transactions_df.groupby('customer_id')['order_date'].min()).dt.days
        features['purchase_frequency'] = grouped['customer_id'].count() / (account_ages / 30 + 1)
        
        # Time-based aggregations (7d, 30d, 90d windows)
        end_date = current_date
        for window in [7, 30, 90]:
            start_date = end_date - timedelta(days=window)
            window_data = transactions_df[transactions_df['order_date'] >= start_date]
            
            if len(window_data) > 0:
                features[f'purchase_value_{window}d'] = window_data.groupby('customer_id')['order_amount'].sum()
                features[f'order_count_{window}d'] = window_data.groupby('customer_id').size()
            else:
                features[f'purchase_value_{window}d'] = 0
                features[f'order_count_{window}d'] = 0
        
        # Category diversity
        features['unique_categories'] = grouped['product_category'].nunique()
        
        # Refund rate
        features['refund_rate'] = (
            transactions_df[transactions_df['refund_flag'] == 1].groupby('customer_id').size() /
            grouped['customer_id'].count()
        ).fillna(0)
        
        # Fill NaN values
        features = features.fillna(0)
        
        logger.info(f"Created {len(features.columns)} transaction features")
        
        return features
    
    def create_behavioral_features(self, events_df: pd.DataFrame) -> pd.DataFrame:
        """Create behavioral engagement features"""
        features = pd.DataFrame()
        
        # Aggregate by customer
        grouped = events_df.groupby('customer_id')
        
        # Event-based features
        features['page_views'] = (
            events_df[events_df['event_type'] == 'page_view'].groupby('customer_id').size()
        )
        features['add_to_cart_events'] = (
            events_df[events_df['event_type'] == 'add_to_cart'].groupby('customer_id').size()
        )
        features['purchase_events'] = (
            events_df[events_df['event_type'] == 'purchase'].groupby('customer_id').size()
        )
        
        # Engagement rate
        total_events = grouped.size()
        features['engagement_rate'] = features['page_views'] / total_events
        
        # Conversion rate
        features['cart_to_purchase_ratio'] = (
            features['purchase_events'] / (features['add_to_cart_events'] + 1)
        ).fillna(0)
        
        # Session features
        features['sessions'] = events_df.groupby('customer_id')['session_id'].nunique()
        features['avg_events_per_session'] = total_events / (features['sessions'] + 1)
        
        # Cart abandonment
        features['cart_abandonment_rate'] = 1 - features['cart_to_purchase_ratio']
        
        # Recent activity (last 7 days)
        cutoff_date = datetime.now() - timedelta(days=7)
        recent_events = events_df[pd.to_datetime(events_df['event_timestamp']) >= cutoff_date]
        features['recent_activity_flag'] = (recent_events.groupby('customer_id').size() > 0).astype(int)
        
        # Fill NaN values
        features = features.fillna(0)
        
        logger.info(f"Created {len(features.columns)} behavioral features")
        
        return features
    
    def create_engagement_features(self, support_df: pd.DataFrame, review_df: pd.DataFrame) -> pd.DataFrame:
        """Create support and review engagement features"""
        features = pd.DataFrame()
        
        # Support ticket metrics
        if len(support_df) > 0:
            support_grouped = support_df.groupby('customer_id')
            features['support_tickets_count'] = support_grouped.size()
            features['avg_ticket_resolution_hours'] = support_grouped['resolution_hours'].mean()
            
            # Sentiment analysis (assuming sentiment score exists)
            if 'sentiment_score' in support_df.columns:
                features['avg_support_sentiment'] = support_grouped['sentiment_score'].mean()
            else:
                features['avg_support_sentiment'] = 0.5
        else:
            features['support_tickets_count'] = 0
            features['avg_ticket_resolution_hours'] = 0
            features['avg_support_sentiment'] = 0.5
        
        # Review metrics
        if len(review_df) > 0:
            review_grouped = review_df.groupby('customer_id')
            features['reviews_count'] = review_grouped.size()
            features['avg_review_rating'] = review_grouped['rating'].mean()
            features['review_sentiment_score'] = review_grouped['sentiment_score'].mean()
        else:
            features['reviews_count'] = 0
            features['avg_review_rating'] = 3.0
            features['review_sentiment_score'] = 0.5
        
        # Email engagement (if available)
        features['email_open_rate'] = np.random.uniform(0.2, 0.8, len(features))  # Placeholder
        features['email_click_rate'] = features['email_open_rate'] * 0.3
        
        # Fill NaN values
        features = features.fillna(0)
        
        logger.info(f"Created {len(features.columns)} engagement features")
        
        return features
    
    def create_temporal_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Create temporal patterns and seasonality features"""
        features = pd.DataFrame(index=df.index)
        
        # Assuming df has a 'date' column
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
            features['day_of_week'] = df['date'].dt.dayofweek
            features['month'] = df['date'].dt.month
            features['quarter'] = df['date'].dt.quarter
            features['is_weekend'] = (features['day_of_week'] >= 5).astype(int)
        else:
            features['day_of_week'] = 0
            features['month'] = datetime.now().month
            features['quarter'] = (datetime.now().month - 1) // 3 + 1
            features['is_weekend'] = 0
        
        # Seasonality
        features['seasonal_index'] = np.sin(2 * np.pi * features['month'] / 12)
        
        logger.info(f"Created {len(features.columns)} temporal features")
        
        return features
    
    def create_rfm_features(self, transactions_df: pd.DataFrame) -> pd.DataFrame:
        """Create RFM (Recency, Frequency, Monetary) features"""
        current_date = datetime.now()
        transactions_df = transactions_df.copy()
        transactions_df['order_date'] = pd.to_datetime(transactions_df['order_date'])
        
        rfm = pd.DataFrame()
        
        # Recency: days since last purchase
        rfm['recency'] = (
            current_date - transactions_df.groupby('customer_id')['order_date'].max()
        ).dt.days
        
        # Frequency: number of purchases
        rfm['frequency'] = transactions_df.groupby('customer_id').size()
        
        # Monetary: total purchase amount
        rfm['monetary'] = transactions_df.groupby('customer_id')['order_amount'].sum()
        
        # Create RFM scores (1-5 scale)
        rfm['r_score'] = pd.qcut(rfm['recency'], q=5, labels=[5, 4, 3, 2, 1], duplicates='drop')
        rfm['f_score'] = pd.qcut(rfm['frequency'].rank(method='first'), q=5, labels=[1, 2, 3, 4, 5], duplicates='drop')
        rfm['m_score'] = pd.qcut(rfm['monetary'], q=5, labels=[1, 2, 3, 4, 5], duplicates='drop')
        
        # Convert to numeric
        rfm['r_score'] = pd.to_numeric(rfm['r_score'])
        rfm['f_score'] = pd.to_numeric(rfm['f_score'])
        rfm['m_score'] = pd.to_numeric(rfm['m_score'])
        
        # Combined RFM score
        rfm['rfm_score'] = rfm['r_score'] * 100 + rfm['f_score'] * 10 + rfm['m_score']
        
        logger.info(f"Created RFM features for {len(rfm)} customers")
        
        return rfm
    
    def combine_features(self, *feature_dfs) -> pd.DataFrame:
        """Combine all feature dataframes"""
        combined = feature_dfs[0].copy()
        
        for df in feature_dfs[1:]:
            combined = combined.join(df, how='outer')
        
        combined = combined.fillna(0)
        logger.info(f"Combined features shape: {combined.shape}")
        
        return combined
    
    def scale_features(self, df: pd.DataFrame, fit: bool = True) -> pd.DataFrame:
        """Scale numerical features"""
        df_scaled = df.copy()
        
        # Select numerical columns
        numerical_cols = df_scaled.select_dtypes(include=[np.number]).columns
        
        if fit:
            df_scaled[numerical_cols] = self.scaler.fit_transform(df_scaled[numerical_cols])
        else:
            df_scaled[numerical_cols] = self.scaler.transform(df_scaled[numerical_cols])
        
        logger.info(f"Scaled {len(numerical_cols)} numerical features")
        
        return df_scaled
    
    def detect_outliers(self, df: pd.DataFrame, threshold: float = 3.0) -> pd.DataFrame:
        """Detect and flag outliers using Z-score"""
        numerical_cols = df.select_dtypes(include=[np.number]).columns
        
        z_scores = np.abs(stats.zscore(df[numerical_cols]))
        outlier_flags = (z_scores > threshold).any(axis=1)
        
        df['is_outlier'] = outlier_flags.astype(int)
        
        logger.info(f"Detected {outlier_flags.sum()} outliers")
        
        return df
    
    def get_feature_statistics(self, df: pd.DataFrame) -> dict:
        """Get statistical summary of features"""
        stats_dict = {
            'total_features': len(df.columns),
            'total_samples': len(df),
            'missing_values': df.isnull().sum().to_dict(),
            'feature_types': df.dtypes.to_dict(),
            'numerical_stats': df.describe().to_dict()
        }
        
        logger.info(f"Feature statistics: {stats_dict['total_features']} features, {stats_dict['total_samples']} samples")
        
        return stats_dict


class FeatureStore:
    """Feature store management"""
    
    def __init__(self, s3_path: str):
        self.s3_path = s3_path
        self.features_cache = {}
    
    def store_features(self, df: pd.DataFrame, version: str, s3_client):
        """Store feature set in feature store"""
        key = f"{self.s3_path}/v{version}/features.parquet"
        
        parquet_buffer = df.to_parquet(index=False)
        s3_client.put_object(Body=parquet_buffer, Key=key)
        
        logger.info(f"Stored features version {version}")
    
    def retrieve_features(self, version: str, customer_ids: List[str] = None, s3_client=None) -> pd.DataFrame:
        """Retrieve features from store"""
        # Implementation depends on actual storage backend
        logger.info(f"Retrieved features version {version}")
        return pd.DataFrame()


if __name__ == "__main__":
    # Example usage
    engineer = FeatureEngineer()
    
    # Create sample data
    customers_df = pd.DataFrame({
        'customer_id': [1, 2, 3],
        'signup_date': pd.date_range('2024-01-01', periods=3),
        'customer_segment': ['VIP', 'Regular', 'New'],
        'device_type': ['Web', 'Mobile', 'App'],
        'signup_source': ['Organic', 'Paid', 'Referral'],
        'country': ['US', 'UK', 'DE']
    })
    
    profile_features = engineer.create_customer_profile_features(customers_df)
    print(profile_features)

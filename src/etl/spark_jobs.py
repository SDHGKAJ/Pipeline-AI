"""
ETL Processing Layer - Spark-based data transformation and cleaning
Handles data validation, deduplication, and feature aggregation
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import json

import pandas as pd
import numpy as np
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as F
import boto3

from config.config import get_settings

logger = logging.getLogger(__name__)


class SparkETLProcessor:
    """Processes data using Apache Spark for distributed computing"""
    
    def __init__(self, app_name: str = "ChurnPredictionETL"):
        """Initialize Spark session"""
        self.settings = get_settings()
        self.spark = SparkSession.builder \
            .appName(app_name) \
            .config("spark.sql.adaptive.enabled", "true") \
            .config("spark.sql.adaptive.coalescePartitions.enabled", "true") \
            .getOrCreate()
        
        self.s3_client = boto3.client("s3", region_name=self.settings.aws.region)
        logger.info(f"Spark session created: {app_name}")
    
    def read_from_s3(self, s3_path: str) -> DataFrame:
        """
        Read data from S3 location (Parquet or JSON)
        
        Args:
            s3_path: S3 path (s3://bucket/prefix)
            
        Returns:
            Spark DataFrame
        """
        try:
            if s3_path.endswith(".parquet"):
                df = self.spark.read.parquet(s3_path)
            else:
                df = self.spark.read.json(s3_path)
            
            logger.info(f"Read data from {s3_path}: {df.count()} rows")
            return df
        except Exception as e:
            logger.error(f"Error reading from S3: {e}")
            raise
    
    def validate_schema(self, df: DataFrame, required_columns: list) -> bool:
        """
        Validate DataFrame has required columns
        
        Args:
            df: Spark DataFrame
            required_columns: List of required column names
            
        Returns:
            True if all columns present
        """
        present_columns = set(df.columns)
        required_set = set(required_columns)
        
        if not required_set.issubset(present_columns):
            missing = required_set - present_columns
            logger.warning(f"Missing columns: {missing}")
            return False
        
        logger.info("Schema validation passed")
        return True
    
    def remove_duplicates(
        self,
        df: DataFrame,
        subset: Optional[list] = None
    ) -> DataFrame:
        """
        Remove duplicate rows
        
        Args:
            df: Spark DataFrame
            subset: Columns to consider for deduplication
            
        Returns:
            DataFrame with duplicates removed
        """
        initial_count = df.count()
        
        if subset:
            df_dedup = df.dropDuplicates(subset=subset)
        else:
            df_dedup = df.dropDuplicates()
        
        final_count = df_dedup.count()
        removed = initial_count - final_count
        
        logger.info(f"Removed {removed} duplicate rows ({removed/initial_count*100:.2f}%)")
        return df_dedup
    
    def handle_missing_values(
        self,
        df: DataFrame,
        strategy: Dict[str, Any]
    ) -> DataFrame:
        """
        Handle missing values with various strategies
        
        Args:
            df: Spark DataFrame
            strategy: Dict mapping column names to strategies
                     {'col': 'drop', 'col2': 'mean', 'col3': 'ffill'}
            
        Returns:
            DataFrame with missing values handled
        """
        for col, method in strategy.items():
            if method == "drop":
                df = df.dropna(subset=[col])
            elif method == "mean":
                mean_val = df.agg(F.mean(col)).collect()[0][0]
                df = df.fillna(mean_val, subset=[col])
            elif method == "zero":
                df = df.fillna(0, subset=[col])
            elif method == "forward_fill":
                df = df.withColumn(col, F.last(col, ignorenulls=True) \
                    .over(Window.orderBy(F.monotonically_increasing_id())))
        
        logger.info(f"Missing values handled for {len(strategy)} columns")
        return df
    
    def remove_outliers(
        self,
        df: DataFrame,
        col: str,
        method: str = "iqr",
        threshold: float = 3.0
    ) -> DataFrame:
        """
        Remove outliers using IQR or Z-score
        
        Args:
            df: Spark DataFrame
            col: Column name
            method: 'iqr' or 'zscore'
            threshold: Z-score threshold (default 3.0)
            
        Returns:
            DataFrame with outliers removed
        """
        initial_count = df.count()
        
        if method == "iqr":
            Q1 = df.approxQuantile(col, [0.25], 0.05)[0]
            Q3 = df.approxQuantile(col, [0.75], 0.05)[0]
            IQR = Q3 - Q1
            lower_bound = Q1 - 1.5 * IQR
            upper_bound = Q3 + 1.5 * IQR
            
            df = df.filter((F.col(col) >= lower_bound) & (F.col(col) <= upper_bound))
        
        elif method == "zscore":
            mean = df.agg(F.mean(col)).collect()[0][0]
            std = df.agg(F.stddev(col)).collect()[0][0]
            
            df = df.filter(
                (F.abs(F.col(col) - mean) / std) <= threshold
            )
        
        final_count = df.count()
        removed = initial_count - final_count
        
        logger.info(f"Removed {removed} outliers from {col} using {method}")
        return df
    
    def write_to_s3(
        self,
        df: DataFrame,
        s3_path: str,
        format: str = "parquet",
        mode: str = "overwrite"
    ) -> None:
        """
        Write DataFrame to S3
        
        Args:
            df: Spark DataFrame
            s3_path: S3 output path
            format: 'parquet' or 'csv'
            mode: 'overwrite', 'append', 'ignore', 'error'
        """
        try:
            df.write \
                .format(format) \
                .mode(mode) \
                .save(s3_path)
            
            logger.info(f"Wrote {df.count()} rows to {s3_path}")
        except Exception as e:
            logger.error(f"Error writing to S3: {e}")
            raise
    
    def stop(self) -> None:
        """Stop Spark session"""
        self.spark.stop()
        logger.info("Spark session stopped")


class DataCleaner:
    """Pandas-based data cleaning utilities"""
    
    @staticmethod
    def clean_customer_data(df: pd.DataFrame) -> pd.DataFrame:
        """
        Clean customer data
        
        Args:
            df: Customer DataFrame
            
        Returns:
            Cleaned DataFrame
        """
        df = df.copy()
        
        # Remove duplicates
        df = df.drop_duplicates(subset=['customer_id'])
        
        # Handle missing values
        df['account_age_days'] = df['account_age_days'].fillna(df['account_age_days'].median())
        df['lifetime_value'] = df['lifetime_value'].fillna(0)
        
        # Remove outliers in purchase amount
        Q1 = df['lifetime_value'].quantile(0.25)
        Q3 = df['lifetime_value'].quantile(0.75)
        IQR = Q3 - Q1
        df = df[
            (df['lifetime_value'] >= Q1 - 1.5*IQR) & 
            (df['lifetime_value'] <= Q3 + 1.5*IQR)
        ]
        
        logger.info(f"Cleaned {len(df)} customer records")
        return df
    
    @staticmethod
    def clean_transaction_data(df: pd.DataFrame) -> pd.DataFrame:
        """Clean transaction data"""
        df = df.copy()
        
        # Convert transaction_date to datetime
        df['transaction_date'] = pd.to_datetime(df['transaction_date'])
        
        # Remove negative amounts
        df = df[df['amount'] > 0]
        
        # Remove duplicate transactions (same customer, amount, time within 1 minute)
        df = df.drop_duplicates(
            subset=['customer_id', 'amount', 'transaction_date'],
            keep='first'
        )
        
        logger.info(f"Cleaned {len(df)} transaction records")
        return df
    
    @staticmethod
    def aggregate_by_period(
        df: pd.DataFrame,
        customer_col: str,
        value_col: str,
        date_col: str,
        period: str = "30D"
    ) -> pd.DataFrame:
        """
        Aggregate metrics by customer and time period
        
        Args:
            df: DataFrame with transactions
            customer_col: Customer ID column
            value_col: Value column to aggregate
            date_col: Date column
            period: Period string (e.g., '30D', '90D')
            
        Returns:
            Aggregated DataFrame
        """
        agg_df = df.groupby([
            customer_col,
            pd.Grouper(key=date_col, freq=period)
        ])[value_col].agg(['sum', 'count', 'mean']).reset_index()
        
        agg_df.columns = [customer_col, 'period', f'{value_col}_sum', f'{value_col}_count', f'{value_col}_mean']
        
        return agg_df


class DataValidator:
    """Data quality validation using Great Expectations style checks"""
    
    @staticmethod
    def check_data_integrity(df: pd.DataFrame) -> Dict[str, Any]:
        """
        Perform comprehensive data quality checks
        
        Args:
            df: DataFrame to validate
            
        Returns:
            Validation report
        """
        report = {
            "timestamp": datetime.utcnow().isoformat(),
            "total_rows": len(df),
            "total_columns": len(df.columns),
            "checks": {}
        }
        
        # Check for null values
        null_counts = df.isnull().sum()
        report["checks"]["null_values"] = {
            "columns_with_nulls": null_counts[null_counts > 0].to_dict(),
            "null_percentage": (null_counts / len(df) * 100).to_dict()
        }
        
        # Check for duplicates
        duplicate_rows = df.duplicated().sum()
        report["checks"]["duplicates"] = {
            "duplicate_rows": duplicate_rows,
            "duplicate_percentage": duplicate_rows / len(df) * 100
        }
        
        # Check data types
        report["checks"]["data_types"] = df.dtypes.astype(str).to_dict()
        
        # Check for date fields
        for col in df.select_dtypes(include=['datetime64']).columns:
            report["checks"][f"date_range_{col}"] = {
                "min": df[col].min().isoformat(),
                "max": df[col].max().isoformat()
            }
        
        logger.info(f"Data integrity report: {json.dumps(report, indent=2)}")
        return report
    
    @staticmethod
    def assert_values_in_range(
        df: pd.DataFrame,
        col: str,
        min_val: float,
        max_val: float
    ) -> bool:
        """Assert values are within expected range"""
        out_of_range = ((df[col] < min_val) | (df[col] > max_val)).sum()
        if out_of_range > 0:
            logger.warning(f"{out_of_range} values outside range [{min_val}, {max_val}]")
            return False
        return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Example usage of Spark ETL
    processor = SparkETLProcessor()
    
    # Read data
    # df = processor.read_from_s3("s3://churn-datalake/raw/customer_events/")
    
    # Validate schema
    # required_cols = ["customer_id", "event_type", "timestamp"]
    # processor.validate_schema(df, required_cols)
    
    # Clean data
    # df = processor.remove_duplicates(df, subset=["customer_id", "timestamp"])
    
    processor.stop()

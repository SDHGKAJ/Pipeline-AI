"""
Data ingestion layer
Handles streaming from Kafka and batch ingestion from databases
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, List
import json
from datetime import datetime

import psycopg2
import mysql.connector
from kafka import KafkaConsumer
import pandas as pd
import boto3

from config.config import CONFIG, DataSourceConfig, StorageConfig


logger = logging.getLogger(__name__)


class DataSource(ABC):
    """Abstract base class for data sources"""
    
    @abstractmethod
    def fetch_data(self, query: str = None, **kwargs) -> pd.DataFrame:
        """Fetch data from source"""
        pass


class PostgreSQLSource(DataSource):
    """PostgreSQL data source"""
    
    def __init__(self, config: DataSourceConfig):
        self.config = config
        self.connection = None
    
    def connect(self):
        """Establish database connection"""
        try:
            self.connection = psycopg2.connect(
                host=self.config.postgresql_host,
                port=self.config.postgresql_port,
                user=self.config.postgresql_user,
                password=self.config.postgresql_password,
                database="ecommerce"
            )
            logger.info("PostgreSQL connection established")
        except psycopg2.Error as e:
            logger.error(f"PostgreSQL connection failed: {e}")
            raise
    
    def fetch_data(self, query: str, **kwargs) -> pd.DataFrame:
        """Fetch data using SQL query"""
        if not self.connection:
            self.connect()
        
        try:
            df = pd.read_sql_query(query, self.connection)
            logger.info(f"Fetched {len(df)} rows from PostgreSQL")
            return df
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            raise
    
    def close(self):
        """Close database connection"""
        if self.connection:
            self.connection.close()


class MySQLSource(DataSource):
    """MySQL data source"""
    
    def __init__(self, config: DataSourceConfig):
        self.config = config
        self.connection = None
    
    def connect(self):
        """Establish database connection"""
        try:
            self.connection = mysql.connector.connect(
                host=self.config.mysql_host,
                port=self.config.mysql_port,
                user=self.config.mysql_user,
                password=self.config.mysql_password,
                database="analytics"
            )
            logger.info("MySQL connection established")
        except mysql.connector.Error as e:
            logger.error(f"MySQL connection failed: {e}")
            raise
    
    def fetch_data(self, query: str, **kwargs) -> pd.DataFrame:
        """Fetch data using SQL query"""
        if not self.connection:
            self.connect()
        
        try:
            df = pd.read_sql(query, self.connection)
            logger.info(f"Fetched {len(df)} rows from MySQL")
            return df
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            raise
    
    def close(self):
        """Close database connection"""
        if self.connection:
            self.connection.close()


class KafkaStreamingSource:
    """Kafka streaming data source"""
    
    def __init__(self, config: DataSourceConfig):
        self.config = config
        self.consumer = None
    
    def connect(self, topics: List[str], group_id: str = "churn-pipeline"):
        """Connect to Kafka topics"""
        try:
            self.consumer = KafkaConsumer(
                *topics,
                bootstrap_servers=self.config.kafka_brokers,
                group_id=group_id,
                auto_offset_reset='earliest',
                value_deserializer=lambda x: json.loads(x.decode('utf-8')),
                batch_size=1000,
                session_timeout_ms=30000
            )
            logger.info(f"Connected to Kafka topics: {topics}")
        except Exception as e:
            logger.error(f"Kafka connection failed: {e}")
            raise
    
    def stream_messages(self, max_messages: int = None):
        """Stream messages from Kafka"""
        try:
            message_count = 0
            for message in self.consumer:
                yield message.value
                message_count += 1
                
                if max_messages and message_count >= max_messages:
                    break
        except Exception as e:
            logger.error(f"Error streaming messages: {e}")
            raise
    
    def batch_fetch(self, duration_seconds: int = 60) -> pd.DataFrame:
        """Fetch messages for specified duration and return as DataFrame"""
        messages = []
        start_time = datetime.now()
        
        try:
            for message in self.consumer:
                messages.append(message.value)
                
                elapsed = (datetime.now() - start_time).total_seconds()
                if elapsed > duration_seconds:
                    break
            
            if messages:
                df = pd.json_normalize(messages)
                logger.info(f"Fetched {len(df)} messages from Kafka")
                return df
            else:
                logger.warning("No messages received from Kafka")
                return pd.DataFrame()
        
        except Exception as e:
            logger.error(f"Kafka batch fetch failed: {e}")
            raise


class S3DataSource:
    """AWS S3 data source"""
    
    def __init__(self, config: StorageConfig):
        self.config = config
        self.s3_client = boto3.client(
            's3',
            region_name=config.aws_region,
            aws_access_key_id=config.aws_access_key,
            aws_secret_access_key=config.aws_secret_key
        )
    
    def read_csv(self, bucket: str, key: str) -> pd.DataFrame:
        """Read CSV file from S3"""
        try:
            obj = self.s3_client.get_object(Bucket=bucket, Key=key)
            df = pd.read_csv(obj['Body'])
            logger.info(f"Read {len(df)} rows from s3://{bucket}/{key}")
            return df
        except Exception as e:
            logger.error(f"Failed to read from S3: {e}")
            raise
    
    def read_parquet(self, bucket: str, key: str) -> pd.DataFrame:
        """Read Parquet file from S3"""
        try:
            obj = self.s3_client.get_object(Bucket=bucket, Key=key)
            df = pd.read_parquet(obj['Body'])
            logger.info(f"Read {len(df)} rows from s3://{bucket}/{key}")
            return df
        except Exception as e:
            logger.error(f"Failed to read Parquet from S3: {e}")
            raise
    
    def write_parquet(self, df: pd.DataFrame, bucket: str, key: str):
        """Write Parquet file to S3"""
        try:
            parquet_buffer = df.to_parquet(index=False)
            self.s3_client.put_object(
                Bucket=bucket,
                Key=key,
                Body=parquet_buffer
            )
            logger.info(f"Wrote {len(df)} rows to s3://{bucket}/{key}")
        except Exception as e:
            logger.error(f"Failed to write to S3: {e}")
            raise
    
    def list_files(self, bucket: str, prefix: str) -> List[str]:
        """List files in S3 with prefix"""
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=bucket,
                Prefix=prefix
            )
            
            if 'Contents' not in response:
                return []
            
            return [obj['Key'] for obj in response['Contents']]
        except Exception as e:
            logger.error(f"Failed to list S3 objects: {e}")
            raise


class DataIngestionPipeline:
    """Main data ingestion orchestrator"""
    
    def __init__(self):
        self.pg_source = PostgreSQLSource(CONFIG.data_source)
        self.mysql_source = MySQLSource(CONFIG.data_source)
        self.kafka_source = KafkaStreamingSource(CONFIG.data_source)
        self.s3_source = S3DataSource(CONFIG.storage)
    
    def ingest_customer_data(self) -> pd.DataFrame:
        """Ingest customer master data"""
        query = """
        SELECT 
            customer_id,
            email,
            country,
            region,
            signup_date,
            account_status,
            customer_segment,
            device_type,
            signup_source
        FROM customers
        WHERE deleted_at IS NULL
        ORDER BY customer_id DESC
        LIMIT 10000
        """
        
        return self.pg_source.fetch_data(query)
    
    def ingest_transaction_data(self, days: int = 90) -> pd.DataFrame:
        """Ingest transaction data for recent period"""
        query = f"""
        SELECT 
            transaction_id,
            customer_id,
            order_date,
            order_amount,
            product_category,
            payment_method,
            shipping_status,
            refund_flag
        FROM transactions
        WHERE order_date >= DATE_SUB(NOW(), INTERVAL {days} DAY)
        ORDER BY order_date DESC
        """
        
        return self.mysql_source.fetch_data(query)
    
    def ingest_streaming_events(self, max_messages: int = 100000) -> pd.DataFrame:
        """Ingest streaming events from Kafka"""
        topics = list(CONFIG.data_source.kafka_topics.values())
        self.kafka_source.connect(topics)
        
        return self.kafka_source.batch_fetch(duration_seconds=60)
    
    def save_to_datalake(self, df: pd.DataFrame, data_type: str, date: str):
        """Save ingested data to S3 data lake"""
        key = f"raw/{data_type}/date={date}/data.parquet"
        self.s3_source.write_parquet(
            df,
            CONFIG.storage.s3_bucket_raw,
            key
        )
    
    def cleanup(self):
        """Close all connections"""
        self.pg_source.close()
        self.mysql_source.close()


if __name__ == "__main__":
    # Example usage
    pipeline = DataIngestionPipeline()
    
    # Ingest customer data
    customers = pipeline.ingest_customer_data()
    pipeline.save_to_datalake(customers, "customers", "2025-02-21")
    
    # Ingest transactions
    transactions = pipeline.ingest_transaction_data()
    pipeline.save_to_datalake(transactions, "transactions", "2025-02-21")
    
    pipeline.cleanup()

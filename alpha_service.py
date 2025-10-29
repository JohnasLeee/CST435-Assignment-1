"""
Alpha Service - Calculates negative rank returns and communicates with Normalizer Service
"""

import os
import sys
import json
import logging
import pandas as pd
import numpy as np
import threading
from typing import Dict, Any, Optional
import grpc
from concurrent import futures

# Ensure project root is importable for utils
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import utils

import pipeline_pb2 as pb2  # type: ignore
import pipeline_pb2_grpc as pb2_grpc  # type: ignore

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

execution_started = False


class AlphaService:
    """Alpha Service for calculating negative rank returns"""
    
    def __init__(self):
        self.normalizer_host = os.getenv('NORMALIZER_HOST', 'normalizer')
        self.normalizer_port = int(os.getenv('NORMALIZER_PORT', '50051'))
        self.backtester_host = os.getenv('BACKTESTER_HOST', 'backtester')
        self.backtester_port = int(os.getenv('BACKTESTER_PORT', '50052'))
        
        # Store computed data for retrieval
        self.alpha_data: Optional[pd.DataFrame] = None
        self.returns_data: Optional[pd.DataFrame] = None
        
        logger.info(f"[AlphaService] Normalizer endpoint: {self.normalizer_host}:{self.normalizer_port}")
        logger.info(f"[AlphaService] Backtester endpoint: {self.backtester_host}:{self.backtester_port}")
    
    def _normalize_via_grpc(self, matrix_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            max_msg_mb = int(os.getenv('GRPC_MAX_MESSAGE_MB', '64'))
            chan = grpc.insecure_channel(
                f"{self.normalizer_host}:{self.normalizer_port}",
                options=[
                    ('grpc.max_send_message_length', max_msg_mb * 1024 * 1024),
                    ('grpc.max_receive_message_length', max_msg_mb * 1024 * 1024),
                ],
            )
            stub = pb2_grpc.NormalizerServiceStub(chan)
            rows = [pb2.Row(values=[float(x) if x is not None else 0.0 for x in row]) for row in matrix_data["data"]]
            dates = list(matrix_data.get("dates", []))
            stocks = list(matrix_data.get("stocks", []))
            req = pb2.NormalizeRequest(matrix=pb2.Matrix(rows=rows), dates=dates, stocks=stocks)
            _ = stub.Normalize(req, timeout=300)
            return {}
        except Exception as e:
            logger.error(f"[AlphaService] gRPC normalize error: {e}")
            return None
    
    def calculate_returns_data(self, raw_data: pd.DataFrame) -> pd.DataFrame:
        """Calculate actual returns from raw stock data"""
        logger.info("[AlphaService] Calculating returns data...")
        
        try:
            returns_columns = []
            
            if isinstance(raw_data.columns, pd.MultiIndex):
                tickers = raw_data.columns.get_level_values(0).unique()
                
                for ticker in tickers:
                    close_col = (ticker, 'Close')
                    if close_col in raw_data.columns:
                        close_prices = raw_data[close_col]
                        returns = close_prices.pct_change(fill_method=None)
                        returns_columns.append(pd.DataFrame({ticker: returns}))
            
            if returns_columns:
                returns_df = pd.concat(returns_columns, axis=1)
                logger.info(f"[AlphaService] Returns data shape: {returns_df.shape}")
                return returns_df
            else:
                return None
                
        except Exception as e:
            logger.error(f"[AlphaService] Error calculating returns: {e}")
            return None
    
    def calculate_alpha_data(self) -> pd.DataFrame:
        """Calculate negative rank returns using utils"""
        logger.info("[AlphaService] Calculating alpha data...")
        
        try:
            # Get S&P 500 data
            logger.info("[AlphaService] Fetching S&P 500 data...")
            data = utils.get_SP500()
            
            if data is None:
                logger.error("[AlphaService] Failed to get S&P 500 data")
                return None
            
            # Store raw data and calculate returns
            logger.info("[AlphaService] Calculating returns...")
            self.returns_data = self.calculate_returns_data(data)
            
            # Calculate negative rank returns
            logger.info("[AlphaService] Calculating negative rank returns...")
            alpha_data = utils.get_negative_rank_returns_only(data)
            
            if alpha_data is None:
                logger.error("[AlphaService] Failed to calculate negative rank returns")
                return None
            
            logger.info(f"[AlphaService] Alpha data calculated: {alpha_data.shape}")
            return alpha_data
            
        except Exception as e:
            logger.error(f"[AlphaService] Error calculating alpha data: {e}")
            return None
    
    def prepare_matrix_data(self, alpha_data: pd.DataFrame) -> Dict[str, Any]:
        """Convert DataFrame to JSON format for Normalizer Service"""
        logger.info("[AlphaService] Preparing matrix data for normalization...")
        
        try:
            # Extract dates and stock symbols
            dates = alpha_data.index.strftime('%Y-%m-%d').tolist()
            stocks = alpha_data.columns.tolist()
            
            # Convert DataFrame to list of lists, handling NaN values
            data_matrix = []
            for date in alpha_data.index:
                row = []
                for stock in alpha_data.columns:
                    value = alpha_data.loc[date, stock]
                    if pd.isna(value):
                        row.append(None)
                    else:
                        row.append(float(value))
                data_matrix.append(row)
            
            # Create JSON structure
            matrix_data = {
                "dates": dates,
                "stocks": stocks,
                "data": data_matrix
            }
            
            logger.info(f"[AlphaService] Matrix prepared: {len(dates)} dates, {len(stocks)} stocks")
            return matrix_data
            
        except Exception as e:
            logger.error(f"[AlphaService] Error preparing matrix data: {e}")
            return None
    
    def send_to_normalizer(self, matrix_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        logger.info("[AlphaService] Sending data to Normalizer Service via gRPC...")
        return self._normalize_via_grpc(matrix_data)
    
    def process_alpha_pipeline(self) -> Optional[Dict[str, Any]]:
        """Complete alpha processing pipeline"""
        logger.info("[AlphaService] Starting alpha processing pipeline...")
        
        try:
            # Step 1: Calculate alpha data
            alpha_data = self.calculate_alpha_data()
            if alpha_data is None:
                return None
            
            # Store alpha_data for retrieval
            self.alpha_data = alpha_data
            
            # Step 2: Prepare matrix data
            matrix_data = self.prepare_matrix_data(alpha_data)
            if matrix_data is None:
                return None
            
            # Step 3: Send to Normalizer Service
            result = self.send_to_normalizer(matrix_data)
            
            if result is not None:
                logger.info("[AlphaService] Sending returns to Backtester via gRPC...")
                try:
                    # Prepare returns matrix from stored returns_data
                    if self.returns_data is None:
                        logger.error("[AlphaService] Returns data not available for Backtester")
                        return result
                    
                    returns_dates = self.returns_data.index.strftime('%Y-%m-%d').tolist()
                    returns_stocks = self.returns_data.columns.tolist()
                    returns_matrix_data = []
                    for date in self.returns_data.index:
                        row = []
                        for stock in self.returns_data.columns:
                            value = self.returns_data.loc[date, stock]
                            if pd.isna(value):
                                row.append(0.0)
                            else:
                                row.append(float(value))
                        returns_matrix_data.append(row)
                    returns_rows = [pb2.Row(values=row) for row in returns_matrix_data]
                    returns_matrix = pb2.Matrix(rows=returns_rows)
                    
                    max_msg_mb = int(os.getenv('GRPC_MAX_MESSAGE_MB', '64'))
                    chan = grpc.insecure_channel(
                        f"{self.backtester_host}:{self.backtester_port}",
                        options=[
                            ('grpc.max_send_message_length', max_msg_mb * 1024 * 1024),
                            ('grpc.max_receive_message_length', max_msg_mb * 1024 * 1024),
                        ],
                    )
                    stub = pb2_grpc.BacktesterServiceStub(chan)
                    # Send returns with dates/stocks for alignment
                    req = pb2.SubmitReturnsRequest(
                        returns=returns_matrix,
                        dates=returns_dates,
                        stocks=returns_stocks
                    )
                    _ = stub.SubmitReturns(req, timeout=60)
                    logger.info("[AlphaService] Backtester acknowledged returns")
                except Exception as e:
                    logger.error(f"[AlphaService] Error calling Backtester: {e}")
                return result
            else:
                logger.error("[AlphaService] Alpha processing pipeline failed")
                return None
                
        except Exception as e:
            logger.error(f"[AlphaService] Pipeline error: {e}")
            return None
        finally:
            pass
    
class AlphaGrpcService(pb2_grpc.AlphaServiceServicer):
    def __init__(self, alpha: 'AlphaService'):
        self.alpha = alpha

    def StartProcessing(self, request: pb2.StartProcessingRequest, context):
        global execution_started
        if execution_started:
            return pb2.StartProcessingResponse(ack=pb2.Ack(ok=True, message="Already started"))
        execution_started = True
        t = threading.Thread(target=self.alpha.process_alpha_pipeline, daemon=True)
        t.start()
        return pb2.StartProcessingResponse(ack=pb2.Ack(ok=True, message="Started"))

def run_grpc_server(alpha: 'AlphaService') -> None:
    port = int(os.getenv('ALPHA_PORT', '50050'))
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    pb2_grpc.add_AlphaServiceServicer_to_server(AlphaGrpcService(alpha), server)
    server.add_insecure_port(f'[::]:{port}')
    logger.info(f"Alpha gRPC server listening on {port}")
    server.start()
    server.wait_for_termination()


def main():
    service = AlphaService()
    run_grpc_server(service)


if __name__ == "__main__":
    main()

"""
Alpha Service - Calculates negative rank returns and communicates with Normalizer Service
"""

import os
import sys
import json
import logging
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional

# Add parent directory to path to import utils
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import utils
from communication_interface import create_client, ICommClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AlphaService:
    """Alpha Service for calculating negative rank returns"""
    
    def __init__(self):
        self.client: Optional[ICommClient] = None
        self.normalizer_host = os.getenv('NORMALIZER_HOST', 'localhost')
        self.normalizer_port = int(os.getenv('NORMALIZER_PORT', '8080'))
        self.protocol = os.getenv('COMM_TYPE', 'REST').upper()
        
        logger.info(f"[AlphaService] Initialized with protocol: {self.protocol}")
        logger.info(f"[AlphaService] Normalizer endpoint: {self.normalizer_host}:{self.normalizer_port}")
    
    def connect_to_normalizer(self) -> bool:
        """Connect to Normalizer Service"""
        try:
            self.client = create_client(self.protocol)
            
            if self.client.connect(self.normalizer_host, self.normalizer_port):
                logger.info("[AlphaService] Connected to Normalizer Service")
                return True
            else:
                logger.error("[AlphaService] Failed to connect to Normalizer Service")
                return False
                
        except Exception as e:
            logger.error(f"[AlphaService] Connection error: {e}")
            return False
    
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
        """Send matrix data to Normalizer Service"""
        if not self.client or not self.client.is_connected():
            logger.error("[AlphaService] Not connected to Normalizer Service")
            return None
        
        try:
            logger.info("[AlphaService] Sending data to Normalizer Service...")
            
            # Send data and get response
            response = self.client.send_data(matrix_data)
            
            if response:
                logger.info("[AlphaService] Received response from Normalizer Service")
                return response
            else:
                logger.error("[AlphaService] No response from Normalizer Service")
                return None
                
        except Exception as e:
            logger.error(f"[AlphaService] Error sending to Normalizer: {e}")
            return None
    
    def process_alpha_pipeline(self) -> Optional[Dict[str, Any]]:
        """Complete alpha processing pipeline"""
        logger.info("[AlphaService] Starting alpha processing pipeline...")
        
        try:
            # Step 1: Calculate alpha data
            alpha_data = self.calculate_alpha_data()
            if alpha_data is None:
                return None
            
            # Step 2: Prepare matrix data
            matrix_data = self.prepare_matrix_data(alpha_data)
            if matrix_data is None:
                return None
            
            # Step 3: Connect to Normalizer Service
            if not self.connect_to_normalizer():
                return None
            
            # Step 4: Send to Normalizer Service
            result = self.send_to_normalizer(matrix_data)
            
            if result:
                logger.info("[AlphaService] Alpha processing pipeline completed successfully")
                return result
            else:
                logger.error("[AlphaService] Alpha processing pipeline failed")
                return None
                
        except Exception as e:
            logger.error(f"[AlphaService] Pipeline error: {e}")
            return None
        finally:
            # Cleanup connection
            if self.client:
                self.client.disconnect()
    
    def run_service(self):
        """Run the Alpha Service"""
        logger.info("=== Alpha Service Started ===")
        logger.info(f"Protocol: {self.protocol}")
        logger.info(f"Normalizer: {self.normalizer_host}:{self.normalizer_port}")
        
        try:
            # Process the alpha pipeline
            result = self.process_alpha_pipeline()
            
            if result:
                logger.info("=== Alpha Service Completed Successfully ===")
                print("\n=== NORMALIZED WEIGHTS ===")
                print(json.dumps(result, indent=2))
            else:
                logger.error("=== Alpha Service Failed ===")
                return False
                
        except KeyboardInterrupt:
            logger.info("=== Alpha Service Interrupted ===")
        except Exception as e:
            logger.error(f"=== Alpha Service Error: {e} ===")
            return False
        
        return True


def main():
    """Main entry point"""
    # Create and run Alpha Service
    service = AlphaService()
    success = service.run_service()
    
    if success:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()

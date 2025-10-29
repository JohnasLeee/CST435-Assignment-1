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
from flask import Flask, request, jsonify

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

# Flask app for receiving execution commands from master
app = Flask(__name__)
execution_started = False
alpha_service_instance = None


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "alpha", "execution_started": execution_started}), 200


@app.route('/execute', methods=['POST'])
def execute_command():
    """Receive execution command from master and acknowledge receipt"""
    global execution_started, alpha_service_instance
    
    try:
        data = request.get_json()
        command = data.get('command', '')
        
        logger.info(f"[AlphaService] Received execution command from master: {command}")
        
        if command == "start_processing" and not execution_started:
            execution_started = True
            
            # Acknowledge receipt to master
            response = {
                "status": "received",
                "message": "Execution code received and acknowledged"
            }
            
            # Start processing in a separate thread to avoid blocking the response
            if alpha_service_instance:
                thread = threading.Thread(target=alpha_service_instance.process_alpha_pipeline)
                thread.daemon = True
                thread.start()
            
            logger.info("[AlphaService] Acknowledging receipt to master and starting processing")
            return jsonify(response), 200
        else:
            if execution_started:
                return jsonify({"status": "already_started", "message": "Processing already in progress"}), 200
            else:
                return jsonify({"status": "error", "message": "Unknown command"}), 400
                
    except Exception as e:
        logger.error(f"[AlphaService] Error handling execution command: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/get_returns', methods=['GET'])
def get_returns():
    """Get returns data for backtesting"""
    global alpha_service_instance
    
    try:
        if not alpha_service_instance or alpha_service_instance.returns_data is None:
            return jsonify({"error": "Returns data not available"}), 404
        
        returns_df = alpha_service_instance.returns_data
        
        # Convert to JSON format
        dates = returns_df.index.strftime('%Y-%m-%d').tolist()
        stocks = returns_df.columns.tolist()
        
        data_matrix = []
        for date in returns_df.index:
            row = []
            for stock in returns_df.columns:
                value = returns_df.loc[date, stock]
                if pd.isna(value):
                    row.append(None)
                else:
                    row.append(float(value))
            data_matrix.append(row)
        
        result = {
            "dates": dates,
            "stocks": stocks,
            "data": data_matrix
        }
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"[AlphaService] Error getting returns: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/get_alpha', methods=['GET'])
def get_alpha():
    """Get alpha (negative rank returns) data"""
    global alpha_service_instance
    
    try:
        if not alpha_service_instance or alpha_service_instance.alpha_data is None:
            return jsonify({"error": "Alpha data not available"}), 404
        
        alpha_df = alpha_service_instance.alpha_data
        
        # Convert to JSON format
        dates = alpha_df.index.strftime('%Y-%m-%d').tolist()
        stocks = alpha_df.columns.tolist()
        
        data_matrix = []
        for date in alpha_df.index:
            row = []
            for stock in alpha_df.columns:
                value = alpha_df.loc[date, stock]
                if pd.isna(value):
                    row.append(None)
                else:
                    row.append(float(value))
            data_matrix.append(row)
        
        result = {
            "dates": dates,
            "stocks": stocks,
            "data": data_matrix
        }
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"[AlphaService] Error getting alpha data: {e}")
        return jsonify({"error": str(e)}), 500


class AlphaService:
    """Alpha Service for calculating negative rank returns"""
    
    def __init__(self):
        self.client: Optional[ICommClient] = None
        self.normalizer_host = os.getenv('NORMALIZER_HOST', 'localhost')
        self.normalizer_port = int(os.getenv('NORMALIZER_PORT', '8080'))
        self.protocol = os.getenv('COMM_TYPE', 'REST').upper()
        
        # Store computed data for retrieval
        self.alpha_data: Optional[pd.DataFrame] = None
        self.returns_data: Optional[pd.DataFrame] = None
        
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
        """Send matrix data to Normalizer Service"""
        if not self.client or not self.client.is_connected():
            logger.error("[AlphaService] Not connected to Normalizer Service")
            return None
        
        try:
            logger.info("[AlphaService] Sending data to Normalizer Service...")
            
            # Send data and get response (normalized weights)
            response = self.client.send_data(matrix_data)
            
            if response and isinstance(response, dict):
                logger.info("[AlphaService] Received normalized weights from Normalizer Service")
                logger.info("[AlphaService] Normalizer will send weights to backtester directly")
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
            
            # Store alpha_data for retrieval
            self.alpha_data = alpha_data
            
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
        """Run the Alpha Service with HTTP server for master communication"""
        global alpha_service_instance
        
        logger.info("=== Alpha Service Started ===")
        logger.info(f"Protocol: {self.protocol}")
        logger.info(f"Normalizer: {self.normalizer_host}:{self.normalizer_port}")
        
        # Set instance for HTTP handler
        alpha_service_instance = self
        
        # Start Flask server in a separate thread
        alpha_port = int(os.getenv('ALPHA_PORT', '8081'))
        logger.info(f"[AlphaService] Starting HTTP server on port {alpha_port} to receive commands from master")
        
        # Run Flask server in a separate thread (non-daemon so it stays alive)
        server_thread = threading.Thread(target=lambda: app.run(host='0.0.0.0', port=alpha_port, debug=False, use_reloader=False))
        server_thread.daemon = False  # Keep thread alive even when main exits
        server_thread.start()
        
        logger.info("[AlphaService] Waiting for execution command from master...")
        
        # Keep the main thread alive to maintain the server indefinitely
        try:
            # Wait for execution to be triggered
            while not execution_started:
                import time
                time.sleep(1)
            
            logger.info("[AlphaService] Processing started, keeping server alive indefinitely...")
            
            # Keep the server running indefinitely to serve requests
            # This allows the backtester and other services to query data
            while True:
                import time
                time.sleep(60)  # Keep alive
                
        except KeyboardInterrupt:
            logger.info("=== Alpha Service Interrupted ===")
            return False
        except Exception as e:
            logger.error(f"=== Alpha Service Error: {e} ===")
            return False


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

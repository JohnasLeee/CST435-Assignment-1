import os
import subprocess
import sys
import requests
import time
import logging
import json
from flask import Flask, request, jsonify

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
results_received = False
backtest_results = None


@app.route('/results', methods=['POST'])
def receive_results():
    """Receive backtest results from Backtester"""
    global results_received, backtest_results
    
    try:
        results = request.get_json()
        results_received = True
        backtest_results = results
        
        logger.info("[Master] Received backtest results from Backtester")
        logger.info(f"[Master] Sharpe Ratio: {results.get('sharpe')}")
        logger.info(f"[Master] Fitness Score: {results.get('fitness')}")
        logger.info(f"[Master] Max Drawdown: {results.get('max_drawdown')}")
        logger.info(f"[Master] Turnover: {results.get('turnover')}")
        
        return jsonify({"status": "received"}), 200
        
    except Exception as e:
        logger.error(f"[Master] Error receiving results: {e}")
        return jsonify({"error": str(e)}), 500


def send_execution_command_to_alpha():
    """Send execution command to Alpha Service and wait for acknowledgment"""
    alpha_host = os.getenv('ALPHA_HOST', 'alpha')
    alpha_port = int(os.getenv('ALPHA_PORT', '8081'))
    max_retries = 10
    retry_delay = 2
    
    logger.info(f"[Master] Sending execution command to Alpha Service at {alpha_host}:{alpha_port}")
    
    for attempt in range(max_retries):
        try:
            url = f"http://{alpha_host}:{alpha_port}/execute"
            response = requests.post(url, json={"command": "start_processing"}, timeout=5)
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"[Master] Alpha Service acknowledged receipt of execution code: {result}")
                print(f"[Master] Alpha Service confirmed: {result.get('message', 'Execution started')}")
                return True
            else:
                logger.warning(f"[Master] Alpha Service returned status {response.status_code}")
                
        except requests.exceptions.ConnectionError:
            logger.info(f"[Master] Attempt {attempt + 1}/{max_retries}: Alpha Service not ready yet, retrying in {retry_delay}s...")
            time.sleep(retry_delay)
        except Exception as e:
            logger.error(f"[Master] Error communicating with Alpha Service: {e}")
            time.sleep(retry_delay)
    
    logger.error("[Master] Failed to get acknowledgment from Alpha Service after all retries")
    return False


def main():
    # Master node sends execution command to alpha service and receives results
    import threading
    
    logger.info("=== Master Service Started ===")
    
    # Start Flask server in background to receive results
    master_port = int(os.getenv('MASTER_PORT', '8083'))
    server_thread = threading.Thread(target=lambda: app.run(host='0.0.0.0', port=master_port, debug=False, use_reloader=False))
    server_thread.daemon = True
    server_thread.start()
    logger.info(f"[Master] Listening for results on port {master_port}")
    
    try:
        # Send execution command to alpha and wait for acknowledgment
        success = send_execution_command_to_alpha()
        
        if success:
            logger.info("[Master] Waiting for backtest results...")
            
            # Wait for results
            max_wait_time = 300  # 5 minutes
            wait_interval = 5
            elapsed = 0
            
            while not results_received and elapsed < max_wait_time:
                time.sleep(wait_interval)
                elapsed += wait_interval
                logger.info(f"[Master] Waiting for results... ({elapsed}s)")
            
            if results_received and backtest_results:
                logger.info("=== Master Service Completed Successfully ===")
                logger.info("=== BACKTEST RESULTS ===")
                logger.info(json.dumps(backtest_results, indent=2))
                print("\n=== BACKTEST RESULTS ===")
                print(json.dumps(backtest_results, indent=2))
                sys.exit(0)
            else:
                logger.error("=== Master Service Timed Out - No results received ===")
                sys.exit(1)
        else:
            logger.error("=== Master Service Failed - Alpha did not acknowledge ===")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"[Master] Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()



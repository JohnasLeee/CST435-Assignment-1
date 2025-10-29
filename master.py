import os
import subprocess
import sys
import grpc
import time
import logging
import json
import pipeline_pb2 as pb2  # type: ignore
import pipeline_pb2_grpc as pb2_grpc  # type: ignore

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

results_received = False
backtest_results = None


def poll_backtester_until_done(timeout_sec: int = 300, interval_sec: int = 5) -> bool:
    global results_received, backtest_results
    backtester_host = os.getenv('BACKTESTER_HOST', 'backtester')
    backtester_port = int(os.getenv('BACKTESTER_PORT', '50052'))
    stub = pb2_grpc.BacktesterServiceStub(grpc.insecure_channel(f"{backtester_host}:{backtester_port}"))
    elapsed = 0
    while elapsed < timeout_sec:
        try:
            resp = stub.GetStatus(pb2.BacktestStatusRequest(), timeout=10)
            if resp.done:
                results_received = True
                backtest_results = json.loads(resp.summary_json) if resp.summary_json else None
                return True
        except Exception as e:
            logger.info(f"[Master] Backtester not ready: {e}")
        time.sleep(interval_sec)
        elapsed += interval_sec
        logger.info(f"[Master] Waiting for results... ({elapsed}s)")
    return False


def send_execution_command_to_alpha():
    alpha_host = os.getenv('ALPHA_HOST', 'alpha')
    alpha_port = int(os.getenv('ALPHA_PORT', '50050'))
    max_retries = 10
    retry_delay = 2
    logger.info(f"[Master] Sending StartProcessing to Alpha at {alpha_host}:{alpha_port}")
    for attempt in range(max_retries):
        try:
            stub = pb2_grpc.AlphaServiceStub(grpc.insecure_channel(f"{alpha_host}:{alpha_port}"))
            resp = stub.StartProcessing(pb2.StartProcessingRequest(), timeout=5)
            if resp.ack.ok:
                logger.info(f"[Master] Alpha acknowledged: {resp.ack.message}")
                print(f"[Master] Alpha: {resp.ack.message}")
                return True
        except Exception as e:
            logger.info(f"[Master] Attempt {attempt + 1}/{max_retries}: Alpha not ready: {e}")
            time.sleep(retry_delay)
    logger.error("[Master] Failed to reach Alpha after retries")
    return False


def main():
    # Master node sends execution command to alpha service and receives results
    logger.info("=== Master Service Started ===")
    try:
        # Send execution command to alpha and wait for acknowledgment
        success = send_execution_command_to_alpha()
        
        if success:
            logger.info("[Master] Waiting for backtest results...")
            if poll_backtester_until_done(timeout_sec=300, interval_sec=5) and backtest_results:
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



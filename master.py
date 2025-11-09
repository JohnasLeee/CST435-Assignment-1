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

# Create persistent gRPC channels and stubs at module level
max_msg_mb = int(os.getenv('GRPC_MAX_MESSAGE_MB', '64'))
grpc_channel_options = [
    ('grpc.max_send_message_length', max_msg_mb * 1024 * 1024),
    ('grpc.max_receive_message_length', max_msg_mb * 1024 * 1024),
    ('grpc.use_local_subchannel_pool', 1),  # Disable Nagle's algorithm
]

alpha_host = os.getenv('ALPHA_HOST', 'alpha')
alpha_port = int(os.getenv('ALPHA_PORT', '50050'))
backtester_host = os.getenv('BACKTESTER_HOST', 'backtester')
backtester_port = int(os.getenv('BACKTESTER_PORT', '50052'))

persistent_alpha_channel = grpc.insecure_channel(f"{alpha_host}:{alpha_port}", options=grpc_channel_options)
persistent_alpha_stub = pb2_grpc.AlphaServiceStub(persistent_alpha_channel)
persistent_backtester_channel = grpc.insecure_channel(f"{backtester_host}:{backtester_port}", options=grpc_channel_options)
persistent_backtester_stub = pb2_grpc.BacktesterServiceStub(persistent_backtester_channel)


def poll_backtester_until_done(timeout_sec: int = 300, interval_sec: int = 5) -> bool:
    global results_received, backtest_results
    elapsed = 0
    poll_start = time.perf_counter()
    while elapsed < timeout_sec:
        try:
            # Time the pure gRPC call to get status
            call_start = time.perf_counter()
            resp = persistent_backtester_stub.GetStatus(pb2.BacktestStatusRequest(), timeout=10)
            call_elapsed = time.perf_counter() - call_start
            
            if resp.done:
                total_wait = time.perf_counter() - poll_start
                logger.info(f"[TIMING] Backtester -> Master (pure gRPC call, no retries): {call_elapsed:.3f} seconds")
                logger.info(f"[TIMING] Backtester -> Master (with polling wait): {total_wait:.3f} seconds")
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
    max_retries = 10
    retry_delay = 2
    overall_start = time.perf_counter()
    logger.info(f"[Master] Sending StartProcessing to Alpha at {alpha_host}:{alpha_port}")
    for attempt in range(max_retries):
        try:
            # Time the pure gRPC call
            call_start = time.perf_counter()
            resp = persistent_alpha_stub.StartProcessing(pb2.StartProcessingRequest(), timeout=5)
            call_elapsed = time.perf_counter() - call_start
            
            if resp.ack.ok:
                overall_elapsed = time.perf_counter() - overall_start
                logger.info(f"[TIMING] Master -> Alpha (pure gRPC call, no retries): {call_elapsed:.3f} seconds")
                logger.info(f"[TIMING] Master -> Alpha (with retries/setup): {overall_elapsed:.3f} seconds")
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



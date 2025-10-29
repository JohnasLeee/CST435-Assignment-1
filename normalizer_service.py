import os
import json
import time
import grpc
import logging
import subprocess
from concurrent import futures

import pipeline_pb2 as pb2  # type: ignore
import pipeline_pb2_grpc as pb2_grpc  # type: ignore


logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger("normalizer_service")


def matrix_to_json(matrix_msg: pb2.Matrix) -> str:
    data = [[float(v) for v in row.values] for row in matrix_msg.rows]
    num_rows = len(data)
    num_cols = len(data[0]) if num_rows > 0 else 0
    # Provide placeholder dates/stocks to satisfy CLI schema expectations
    dates = [f"d{i}" for i in range(num_rows)]
    stocks = [f"s{j}" for j in range(num_cols)]
    payload = {
        "dates": dates,
        "index": dates,
        "stocks": stocks,
        "columns": stocks,
        "data": data,
    }
    return json.dumps(payload, separators=(",", ":"))


def json_to_matrix(json_str: str) -> pb2.Matrix:
    obj = json.loads(json_str)
    data = obj.get("data", [])
    rows = [pb2.Row(values=[float(x) for x in row]) for row in data]
    return pb2.Matrix(rows=rows)


class NormalizerService(pb2_grpc.NormalizerServiceServicer):
    def __init__(self):
        self.binary = os.getenv('NORMALIZER_BIN', '/app/bin/normalizer_cli')

    def Normalize(self, request: pb2.NormalizeRequest, context: grpc.ServicerContext) -> pb2.NormalizeResponse:
        start = time.time()
        try:
            payload = matrix_to_json(request.matrix)
            proc = subprocess.Popen(
                [self.binary],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            out, err = proc.communicate(input=payload, timeout=int(os.getenv('NORMALIZER_TIMEOUT', '300')))
            if proc.returncode != 0:
                snippet = (err or "").strip().replace("\n", " ")[:300]
                logger.error(f"Normalizer binary failed: rc={proc.returncode} stderr={snippet}")
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details(f'Normalizer binary failed: {snippet}')
                return pb2.NormalizeResponse()
            normalized = json_to_matrix(out)
            elapsed = (time.time() - start) * 1000.0
            logger.info(f"Normalized matrix via CLI in {elapsed:.1f} ms")

            # Send weights to Backtester
            backtester_host = os.getenv('BACKTESTER_HOST', 'backtester')
            backtester_port = int(os.getenv('BACKTESTER_PORT', '50052'))
            max_msg_mb = int(os.getenv('GRPC_MAX_MESSAGE_MB', '64'))
            channel = grpc.insecure_channel(
                f"{backtester_host}:{backtester_port}",
                options=[
                    ('grpc.max_send_message_length', max_msg_mb * 1024 * 1024),
                    ('grpc.max_receive_message_length', max_msg_mb * 1024 * 1024),
                ],
            )
            stub = pb2_grpc.BacktesterServiceStub(channel)
            req = pb2.SubmitWeightsRequest(
                weights=normalized,
                dates=list(request.dates),
                stocks=list(request.stocks),
            )
            _ = stub.SubmitWeights(req, timeout=60)
            return pb2.NormalizeResponse(ack=pb2.Ack(ok=True, message="Weights sent to Backtester"))
        except subprocess.TimeoutExpired:
            context.set_code(grpc.StatusCode.DEADLINE_EXCEEDED)
            context.set_details('Normalization timed out')
            return pb2.NormalizeResponse()
        except Exception as e:
            logger.exception("Normalization error")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return pb2.NormalizeResponse()


def serve() -> None:
    port = int(os.getenv('NORMALIZER_PORT', '50051'))
    max_msg_mb = int(os.getenv('GRPC_MAX_MESSAGE_MB', '64'))
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=8),
        options=[
            ('grpc.max_send_message_length', max_msg_mb * 1024 * 1024),
            ('grpc.max_receive_message_length', max_msg_mb * 1024 * 1024),
        ],
    )
    pb2_grpc.add_NormalizerServiceServicer_to_server(NormalizerService(), server)
    server.add_insecure_port(f'[::]:{port}')
    logger.info(f"Normalizer gRPC server listening on {port}")
    server.start()
    server.wait_for_termination()


if __name__ == '__main__':
    serve()



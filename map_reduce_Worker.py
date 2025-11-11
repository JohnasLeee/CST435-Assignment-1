import grpc
from concurrent import futures
import time
import sys
from collections import defaultdict

# Import generated gRPC definitions
import gRPC_service_defination_pb2 as mapreduce_pb2
import gRPC_service_defination_pb2_grpc as mapreduce_pb2_grpc


class MapReduceServicer(mapreduce_pb2_grpc.MapReduceServicer):
    """
    Worker that performs map + local reduce for each text chunk.
    """

    def FullProcessTask(self, request, context):
        try:
            recv_time = time.time()
            print(f"Received FullProcessTask {request.task_id} (content length: {len(request.input_content)}) at {recv_time:.6f}")

            # --- MAP: tokenize words ---
            words = request.input_content.lower().split()

            # --- LOCAL SHUFFLE + REDUCE ---
            word_counts = defaultdict(int)
            for w in words:
                clean = ''.join(c for c in w if c.isalnum())
                if clean:
                    word_counts[clean] += 1

            # --- Prepare response ---
            results = [
                mapreduce_pb2.KeyValue(key=word, value=str(count))
                for word, count in word_counts.items()
            ]
            send_time = time.time()
            print(f"Task {request.task_id} complete: {len(results)} unique words, sending response at {send_time:.6f}")
            print(f"Worker communication times for task {request.task_id}: received at {recv_time:.6f}, sent at {send_time:.6f}")
            return mapreduce_pb2.MapResponse(task_id=request.task_id, intermediate_results=results)

        except Exception as e:
            print(f"Error in FullProcessTask {request.task_id}: {e}")
            return mapreduce_pb2.MapResponse(task_id=request.task_id, intermediate_results=[])


def serve():
    if len(sys.argv) < 2:
        print("Usage: python worker.py <port>")
        sys.exit(1)
    port = sys.argv[1]

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    mapreduce_pb2_grpc.add_MapReduceServicer_to_server(MapReduceServicer(), server)
    server.add_insecure_port(f'[::]:{port}')
    server.start()
    print(f"Worker started on port {port}. Ready for tasks.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Worker shutting down.")
        server.stop(0)


if __name__ == "__main__":
    serve()

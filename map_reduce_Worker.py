import grpc
from concurrent import futures
import time
import sys

# Import the generated classes
import gRPC_service_defination_pb2 as mapreduce_pb2
import gRPC_service_defination_pb2_grpc as mapreduce_pb2_grpc

# Worker implementation
class MapReduceServicer(mapreduce_pb2_grpc.MapReduceServicer):
    """
    This class implements the gRPC service methods for the worker.
    It handles Map and Reduce tasks sent by the Master.
    """

    def MapTask(self, request, context):
        """
        Processes a Map task. For word count, it tokenizes the input
        and emits a (word, "1") pair for each word.
        """
        try:
            print(f"Received Map task {request.task_id} (content length: {len(request.input_content)})")
            
            # Simple word splitting and cleaning
            words = request.input_content.lower().split()
            print(f"Processing {len(words)} words...")
            
            intermediate_results = []
            for word in words:
                # Clean word (remove punctuation)
                clean_word = ''.join(c for c in word if c.isalnum())
                if clean_word:  # Only add non-empty words
                    kv_pair = mapreduce_pb2.KeyValue(key=clean_word, value="1")
                    intermediate_results.append(kv_pair)

            print(f"Map task {request.task_id} completed: {len(intermediate_results)} results")
            
            # Return the list of key-value pairs
            return mapreduce_pb2.MapResponse(
                task_id=request.task_id,
                intermediate_results=intermediate_results
            )
        except Exception as e:
            print(f"Error in MapTask {request.task_id}: {e}")
            # Return empty results on error
            return mapreduce_pb2.MapResponse(
                task_id=request.task_id,
                intermediate_results=[]
            )

    def ReduceTask(self, request, context):
        """
        Processes a Reduce task. For word count, it sums up the values ("1"s)
        to get the total count for a given word.
        """
        try:
            print(f"Received Reduce task for key: {request.reduce_key} ({len(request.values)} values)")
            
            # The values are a list of strings "1". Sum them up.
            count = sum(int(v) for v in request.values)
            
            print(f"Reduce task completed for '{request.reduce_key}': {count}")
            
            return mapreduce_pb2.ReduceResponse(
                reduce_key=request.reduce_key,
                result_value=str(count)
            )
        except Exception as e:
            print(f"Error in ReduceTask for key '{request.reduce_key}': {e}")
            # Return 0 count on error
            return mapreduce_pb2.ReduceResponse(
                reduce_key=request.reduce_key,
                result_value="0"
            )

def serve():
    """
    Starts the gRPC server for the worker.
    """
    if len(sys.argv) < 2:
        print("Usage: python worker.py <port>")
        sys.exit(1)
        
    port = sys.argv[1]
    
    # Configure server options for larger messages
    options = [
        ('grpc.max_send_message_length', 50 * 1024 * 1024),  # 50MB
        ('grpc.max_receive_message_length', 50 * 1024 * 1024),  # 50MB
    ]
    
    # Create a gRPC server with options
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10), options=options)
    
    # Add the servicer to the server
    mapreduce_pb2_grpc.add_MapReduceServicer_to_server(MapReduceServicer(), server)
    
    # Start the server on the specified port
    server.add_insecure_port(f'[::]:{port}')
    server.start()
    print(f"Worker started. Listening on port {port}...")
    
    try:
        # Keep the server running
        print("Worker ready and waiting for tasks...")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Worker shutting down.")
        server.stop(0)

if __name__ == '__main__':
    serve()

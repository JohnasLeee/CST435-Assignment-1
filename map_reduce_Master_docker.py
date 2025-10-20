import grpc
import os
from collections import defaultdict
import time
import concurrent.futures

# Import the generated classes
import gRPC_service_defination_pb2 as mapreduce_pb2
import gRPC_service_defination_pb2_grpc as mapreduce_pb2_grpc

# --- CONFIGURATION FOR DOCKER ---
WORKER_ADDRESSES = [
    'worker1:50051',
    'worker2:50052',
]
INPUT_DIR = 'input_data'
MAX_CHUNK_SIZE = 200000

def split_text_into_chunks(text, max_size):
    """Splits text into manageable chunks."""
    if len(text) <= max_size:
        return [text]
    chunks, start = [], 0
    while start < len(text):
        end = start + max_size
        if end < len(text):
            split_point = text.rfind(' ', start, end)
            if split_point > start:
                end = split_point
        chunks.append(text[start:end].strip())
        start = end
    return chunks

def run_mapreduce():
    """Orchestrates the entire MapReduce job with Docker networking."""
    start_time = time.time()

    # 1. Read input data from files
    input_splits = []
    try:
        filenames = [f for f in os.listdir(INPUT_DIR) if f.endswith(".txt")]
        if not filenames:
            print(f"Error: No .txt files found in '{INPUT_DIR}' directory.")
            return
        for filename in filenames:
            with open(os.path.join(INPUT_DIR, filename), 'r', encoding='utf-8') as f:
                file_content = f.read()
            input_splits.extend(split_text_into_chunks(file_content, MAX_CHUNK_SIZE))
    except (FileNotFoundError, UnicodeDecodeError) as e:
        print(f"Error reading input files: {e}")
        return

    channels, stubs = {}, {}
    print("--- Initializing connections to workers ---")
    try:
        for address in WORKER_ADDRESSES:
            options = [
                ('grpc.max_send_message_length', 50 * 1024 * 1024),
                ('grpc.max_receive_message_length', 50 * 1024 * 1024),
            ]
            channel = grpc.insecure_channel(address, options=options)
            channels[address] = channel
            stubs[address] = mapreduce_pb2_grpc.MapReduceStub(channel)
            print(f"Channel created for {address}")
    except Exception as e:
        print(f"Failed to create gRPC channels: {e}")
        return

    try:
        # --- MAP PHASE (NOW PARALLELIZED) ---
        print("\n--- Starting PARALLEL MAP Phase ---")
        intermediate_data = []
        
        def send_map_task(task_data):
            """Helper function to send a single map task."""
            task_id, content_split = task_data
            worker_address = WORKER_ADDRESSES[task_id % len(WORKER_ADDRESSES)]
            try:
                stub = stubs[worker_address]
                request = mapreduce_pb2.MapRequest(task_id=str(task_id), input_content=content_split)
                print(f"Assigning Map task {task_id} to {worker_address}...")
                response = stub.MapTask(request, timeout=120) # Increased timeout for heavy loads
                return response.intermediate_results
            except grpc.RpcError as e:
                print(f"  ERROR on map task {task_id} at {worker_address}. Details: {e.details()}")
                return []

        # Create a list of tasks to submit
        map_tasks = list(enumerate(input_splits))
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(WORKER_ADDRESSES) * 2) as executor:
            future_to_results = {executor.submit(send_map_task, task): task for task in map_tasks}
            for future in concurrent.futures.as_completed(future_to_results):
                try:
                    results = future.result()
                    intermediate_data.extend(results)
                except Exception as e:
                    task_id, _ = future_to_results[future]
                    print(f"  ERROR processing map task {task_id}: {e}")

        if not intermediate_data:
            print("Map phase produced no results. Aborting.")
            return

        print("--- MAP Phase Complete ---")

        # --- SHUFFLE PHASE ---
        print("\n--- Starting SHUFFLE Phase ---")
        shuffled_data = defaultdict(list)
        for kv_pair in intermediate_data:
            shuffled_data[kv_pair.key].append(kv_pair.value)
        print("--- SHUFFLE Phase Complete ---")

        # --- REDUCE PHASE (ALREADY PARALLEL) ---
        print("\n--- Starting PARALLEL REDUCE Phase ---")
        final_results = {}
        reduce_tasks = list(shuffled_data.items())
        
        def send_reduce_task(task_data):
            """Helper function to send a single reduce task."""
            key, values = task_data
            worker_index = hash(key) % len(WORKER_ADDRESSES)
            worker_address = WORKER_ADDRESSES[worker_index]
            try:
                stub = stubs[worker_address]
                request = mapreduce_pb2.ReduceRequest(reduce_key=key, values=values)
                response = stub.ReduceTask(request, timeout=120)
                return (response.reduce_key, int(response.result_value))
            except grpc.RpcError as e:
                print(f"  ERROR on reduce task for key '{key}' at {worker_address}. Details: {e.details()}")
                return (key, 0)
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(WORKER_ADDRESSES) * 4) as executor:
            future_to_task = {executor.submit(send_reduce_task, task): task for task in reduce_tasks}
            for future in concurrent.futures.as_completed(future_to_task):
                try:
                    key, count = future.result()
                    final_results[key] = count
                except Exception as e:
                    task = future_to_task[future]
                    print(f"  ERROR processing reduce task {task}: {e}")

        print("--- REDUCE Phase Complete ---\n")

    finally:
        print("--- Closing all worker connections ---")
        for address, channel in channels.items():
            channel.close()
        print("--- All connections closed ---")

    end_time = time.time()
    
    print("\n----------- MAPREDUCE RESULTS -----------")
    for key, value in sorted(final_results.items()):
        print(f"{key}: {value}")
    print("-----------------------------------------")
    print(f"Total execution time: {end_time - start_time:.4f} seconds")

if __name__ == '__main__':
    run_mapreduce()

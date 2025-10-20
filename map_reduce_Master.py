import grpc
import os
from collections import defaultdict
import time

# Import the generated classes
import gRPC_service_defination_pb2 as mapreduce_pb2
import gRPC_service_defination_pb2_grpc as mapreduce_pb2_grpc

# --- CONFIGURATION ---
WORKER_ADDRESSES = [
    'localhost:50051',
    'localhost:50052',
]
INPUT_DIR = 'input_data'
MAX_CHUNK_SIZE = 200000

def split_text_into_chunks(text, max_size):
    """Splits text into manageable chunks."""
    if len(text) <= max_size:
        return [text]
    
    chunks = []
    start = 0
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
    """Orchestrates the entire MapReduce job with reused gRPC channels."""
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

    channels = {}
    stubs = {}
    
    # *** NEW: Create reusable channels and stubs outside the loops ***
    print("--- Initializing connections to workers ---")
    try:
        for address in WORKER_ADDRESSES:
            # Configure gRPC options for larger messages
            options = [
                ('grpc.max_send_message_length', 50 * 1024 * 1024),  # 50MB
                ('grpc.max_receive_message_length', 50 * 1024 * 1024),  # 50MB
            ]
            channel = grpc.insecure_channel(address, options=options)
            channels[address] = channel
            stubs[address] = mapreduce_pb2_grpc.MapReduceStub(channel)
            print(f"Channel created for {address}")
    except Exception as e:
        print(f"Failed to create gRPC channels: {e}")
        return

    try:
        # --- MAP PHASE ---
        print("\n--- Starting MAP Phase ---")
        intermediate_data = []
        map_task_id = 0
        for i, content_split in enumerate(input_splits):
            worker_address = WORKER_ADDRESSES[i % len(WORKER_ADDRESSES)]
            print(f"Assigning Map task {map_task_id} to worker at {worker_address}...")
            
            try:
                # *** MODIFIED: Use the existing stub ***
                stub = stubs[worker_address]
                request = mapreduce_pb2.MapRequest(task_id=str(map_task_id), input_content=content_split)
                response = stub.MapTask(request, timeout=60)
                intermediate_data.extend(response.intermediate_results)
                map_task_id += 1
            except grpc.RpcError as e:
                print(f"  ERROR communicating with worker at {worker_address}. Skipping task. Details: {e.details()}")
                
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

        # --- REDUCE PHASE ---
        print("\n--- Starting REDUCE Phase ---")
        final_results = {}
        reduce_tasks = list(shuffled_data.items())
        for i, (key, values) in enumerate(reduce_tasks):
            worker_index = hash(key) % len(WORKER_ADDRESSES)
            worker_address = WORKER_ADDRESSES[worker_index]
            
            try:
                # *** MODIFIED: Use the existing stub ***
                stub = stubs[worker_address]
                request = mapreduce_pb2.ReduceRequest(reduce_key=key, values=values)
                response = stub.ReduceTask(request, timeout=60)
                final_results[response.reduce_key] = int(response.result_value)
            except grpc.RpcError as e:
                print(f"  ERROR on reduce task for key '{key}' at {worker_address}. Skipping. Details: {e.details()}")

        print("--- REDUCE Phase Complete ---\n")

    finally:
        # *** NEW: Close the channels at the very end ***
        print("--- Closing all worker connections ---")
        for address, channel in channels.items():
            channel.close()
            print(f"Channel to {address} closed.")

    # --- FINAL AGGREGATION & DISPLAY ---
    end_time = time.time()
    
    print("\n----------- MAPREDUCE RESULTS -----------")
    for key, value in sorted(final_results.items()):
        print(f"{key}: {value}")
    print("-----------------------------------------")
    print(f"Total execution time: {end_time - start_time:.4f} seconds")

if __name__ == '__main__':
    run_mapreduce()

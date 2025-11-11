import grpc
import os
import time
import concurrent.futures
from collections import defaultdict

# Import generated gRPC code
import gRPC_service_defination_pb2 as mapreduce_pb2
import gRPC_service_defination_pb2_grpc as mapreduce_pb2_grpc

WORKER_ADDRESSES = [
  'worker1:50051',
  'worker2:50052',
  '10.213.7.252:50053'
]

INPUT_DIR = 'input_data'
MAX_CHUNK_SIZE = 200000


def split_text_into_chunks(text, max_size):
    """Splits large text into chunks by spaces."""
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
    start_time = time.time()

    # 1. Load input files and split into chunks
    input_splits = []
    filenames = [f for f in os.listdir(INPUT_DIR) if f.endswith(".txt")]
    if not filenames:
        print(f"No .txt files found in '{INPUT_DIR}'")
        return
    for filename in filenames:
        with open(os.path.join(INPUT_DIR, filename), 'r', encoding='utf-8') as f:
            text = f.read()
        input_splits.extend(split_text_into_chunks(text, MAX_CHUNK_SIZE))

    # 2. Initialize worker channels
    print("--- Initializing connections to workers ---")
    stubs = {}
    for addr in WORKER_ADDRESSES:
        options = [
            ('grpc.max_send_message_length', 50 * 1024 * 1024),
            ('grpc.max_receive_message_length', 50 * 1024 * 1024),
        ]
        channel = grpc.insecure_channel(addr, options=options)
        stubs[addr] = mapreduce_pb2_grpc.MapReduceStub(channel)
        print(f"Connected to {addr}")

    # 3. Send text chunks directly to workers for processing
    print("\n--- Distributing chunks to workers ---")
    def send_task(task_data):
        task_id, text = task_data
        worker_addr = WORKER_ADDRESSES[task_id % len(WORKER_ADDRESSES)]
        stub = stubs[worker_addr]
        request = mapreduce_pb2.MapRequest(task_id=str(task_id), input_content=text)
        try:
            master_send_time = time.time()
            response = stub.FullProcessTask(request, timeout=120)
            master_recv_time = time.time()
            grpc_duration = master_recv_time - master_send_time
            partial_result = {kv.key: int(kv.value) for kv in response.intermediate_results}
            print(f"Task {task_id} done by {worker_addr} ({len(partial_result)} unique words)")
            print(f"Master send time: {master_send_time:.6f}, receive time: {master_recv_time:.6f}")
            print(f"Total gRPC round-trip time for task {task_id}: {grpc_duration:.4f} seconds")
            # Note: Worker logs its own receive/send times. Check worker logs for detailed communication breakdown.
            return partial_result
        except grpc.RpcError as e:
            print(f"Task {task_id} failed on {worker_addr}: {e.details()}")
            return {}

    map_tasks = list(enumerate(input_splits))
    all_results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(WORKER_ADDRESSES)) as executor:
        futures = [executor.submit(send_task, t) for t in map_tasks]
        for f in concurrent.futures.as_completed(futures):
            all_results.append(f.result())

    # 4. Merge all dictionaries into final result
    print("\n--- Merging worker results ---")
    final_counts = defaultdict(int)
    for partial in all_results:
        for word, count in partial.items():
            final_counts[word] += count

    end_time = time.time()
    print("\n----------- FINAL WORD COUNTS -----------")
    for word, count in sorted(final_counts.items()):
        print(f"{word}: {count}")
    print("-----------------------------------------")
    
    # Calculate and print statistics
    total_words = sum(final_counts.values())
    total_unique_words = len(final_counts)
    print(f"Total txt file processed: {len(filenames)}")
    print(f"Total words: {total_words}")
    print(f"Total unique words: {total_unique_words}")
    print(f"Total execution time: {end_time - start_time:.2f} s")


if __name__ == "__main__":
    run_mapreduce()

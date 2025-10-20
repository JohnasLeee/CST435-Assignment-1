# MapReduce with gRPC - CST435 Assignment

This project implements a distributed MapReduce system using gRPC for word counting on the Bible text.

## Project Structure

- `map_reduce_Master.py` - Master node that coordinates the MapReduce job
- `map_reduce_Worker.py` - Worker node that processes Map and Reduce tasks
- `gRPC_service_defination.proto` - Protocol buffer definition for gRPC communication
- `gRPC_code_gen.py` - Script to generate Python gRPC code from proto file
- `input_data/` - Directory containing input text files (Bible_KJV.txt)
- `venv/` - Python virtual environment with gRPC dependencies

## Prerequisites

1. Python 3.7+ installed
2. Virtual environment activated (venv folder is already set up)
3. gRPC and protobuf libraries (already installed in venv)

## How to Run the Program

### Step 1: Generate gRPC Code (if not already done)
```bash
# Activate virtual environment
venv\Scripts\activate

# Generate gRPC Python code
python gRPC_code_gen.py
```

### Step 2: Run Workers (Terminal 1 & 2)
Open two separate terminal windows and run:

**Terminal 1:**
```bash
cd "C:\Users\ASUS\Documents\CST435\Assignment 1"
venv\Scripts\python.exe map_reduce_Worker.py 50051
```

**Terminal 2:**
```bash
cd "C:\Users\ASUS\Documents\CST435\Assignment 1"
venv\Scripts\python.exe map_reduce_Worker.py 50052
```

### Step 3: Run Master (Terminal 3)
Open a third terminal window and run:

```bash
cd "C:\Users\ASUS\Documents\CST435\Assignment 1"
venv\Scripts\python.exe map_reduce_Master.py
```

## Expected Output

The program will:
1. Read the Bible text from `input_data/Bible_KJV.txt`
2. Split the text into chunks for Map tasks
3. Distribute Map tasks to workers
4. Collect intermediate results (word, "1" pairs)
5. Shuffle and group by word
6. Distribute Reduce tasks to workers
7. Collect final word counts
8. Display results sorted by word

## Performance Comparison

### Single Machine Testing
- Run with 1 worker: `WORKER_ADDRESSES = ['localhost:50051']`
- Run with 2 workers: `WORKER_ADDRESSES = ['localhost:50051', 'localhost:50052']`

### Distributed Testing (Docker)
Use the provided Docker setup for testing across multiple containers.

## Troubleshooting

1. **Port already in use**: Change ports in `WORKER_ADDRESSES` in `map_reduce_Master.py`
2. **Module not found**: Ensure virtual environment is activated
3. **Connection refused**: Make sure workers are running before starting master
4. **No input files**: Ensure `Bible_KJV.txt` is in the `input_data/` directory

## Performance Metrics

The program measures and displays:
- Total execution time
- Number of words processed
- Distribution of work across workers
- Network communication overhead

## Files Generated

After running `gRPC_code_gen.py`, you should see:
- `gRPC_service_defination_pb2.py`
- `gRPC_service_defination_pb2_grpc.py`

These contain the generated gRPC client and server code.

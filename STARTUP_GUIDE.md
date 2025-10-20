# 🚀 MapReduce Startup Guide

## ❌ The Problem
You're getting connection errors because **workers must be started BEFORE the master**.

## ✅ Correct Startup Sequence

### Step 1: Start Worker 1
Open **Terminal 1** and run:
```bash
cd "C:\Users\ASUS\Documents\CST435\Assignment 1"
venv\Scripts\python.exe map_reduce_Worker.py 50051
```

**Expected output:**
```
Worker started. Listening on port 50051...
```

### Step 2: Start Worker 2  
Open **Terminal 2** and run:
```bash
cd "C:\Users\ASUS\Documents\CST435\Assignment 1"
venv\Scripts\python.exe map_reduce_Worker.py 50052
```

**Expected output:**
```
Worker started. Listening on port 50052...
```

### Step 3: Test Workers (Optional)
Open **Terminal 3** and test:
```bash
cd "C:\Users\ASUS\Documents\CST435\Assignment 1"
venv\Scripts\python.exe test_worker.py
```

### Step 4: Run Master
In **Terminal 3** (or new terminal):
```bash
cd "C:\Users\ASUS\Documents\CST435\Assignment 1"
venv\Scripts\python.exe map_reduce_Master.py
```

## 🔧 Troubleshooting

### If you get "port already in use":
1. **Kill existing processes:**
   ```bash
   taskkill /f /im python.exe
   ```
2. **Wait 5 seconds**
3. **Start workers again**

### If workers won't start:
1. **Check virtual environment:**
   ```bash
   venv\Scripts\python.exe --version
   ```
2. **Regenerate gRPC code:**
   ```bash
   venv\Scripts\python.exe gRPC_code_gen.py
   ```

### If master can't connect:
1. **Test workers first:**
   ```bash
   venv\Scripts\python.exe test_worker.py
   ```
2. **Check ports are free:**
   ```bash
   netstat -an | findstr "50051\|50052"
   ```

## 📊 Expected Results

When everything works, you'll see:
```
Reading Bible_KJV.txt...
Split Bible_KJV.txt into 5 chunks
--- Starting MAP Phase ---
Assigning Map task 0 to worker at localhost:50051...
Assigning Map task 1 to worker at localhost:50052...
...
--- MAP Phase Complete ---
--- Starting SHUFFLE Phase ---
--- SHUFFLE Phase Complete ---
--- Starting REDUCE Phase ---
...
----------- MAPREDUCE RESULTS -----------
the: 12345
and: 9876
...
Total execution time: 2.3456 seconds
```

## 🎯 Quick Commands

**Kill all Python processes:**
```bash
taskkill /f /im python.exe
```

**Test everything:**
```bash
venv\Scripts\python.exe test_worker.py
```

**Run automated:**
```bash
run_local.bat
```

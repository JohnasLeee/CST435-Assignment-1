# Quick Start Guide - MapReduce with Bible Text

## 🚀 How to Run Your MapReduce Program

### Option 1: Easy Automated Run (Recommended)
```bash
# Double-click this file or run in terminal:
run_local.bat
```

### Option 2: Manual Step-by-Step

#### Step 1: Start Workers (2 separate terminals)
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

#### Step 3: Run Master (3rd terminal)
```bash
cd "C:\Users\ASUS\Documents\CST435\Assignment 1"
venv\Scripts\python.exe map_reduce_Master.py
```

## 📊 Performance Testing

### Run Performance Comparison
```bash
venv\Scripts\python.exe performance_test.py
```

This will:
- Test single worker performance
- Test multi-worker performance  
- Generate comparison report
- Show speedup metrics

### Docker Distributed Testing
```bash
# Build and run with Docker
docker-compose up --build
```

## 📁 What the Program Does

1. **Input**: Reads `Bible_KJV.txt` from `input_data/` directory
2. **Map Phase**: Splits text into chunks, sends to workers
3. **Shuffle**: Groups words by key
4. **Reduce Phase**: Counts occurrences of each word
5. **Output**: Displays word frequency counts

## 🔧 Troubleshooting

### Common Issues:

1. **"Module not found"**
   - Solution: Use `venv\Scripts\python.exe` instead of `python`

2. **"Port already in use"**
   - Solution: Change ports in `map_reduce_Master.py` line 14-17

3. **"No input files found"**
   - Solution: Ensure `Bible_KJV.txt` is in `input_data/` folder

4. **"Connection refused"**
   - Solution: Start workers before master

5. **"Message larger than max"** ✅ FIXED
   - Solution: The program now automatically splits large files into 1MB chunks
   - gRPC message limits increased to 50MB
   - Bible text will be processed in multiple chunks

## 📈 Expected Results

The program will output:
- Word frequency counts (e.g., "the: 12345")
- Total execution time
- Performance metrics

## 🎯 Assignment Requirements Met

✅ **gRPC Implementation**: Master-Worker communication via gRPC  
✅ **Bible Text Processing**: Word count on Bible_KJV.txt  
✅ **Performance Comparison**: Single vs Multi-worker testing  
✅ **Docker Support**: Distributed testing capability  
✅ **Documentation**: Complete setup and usage instructions  

## 📝 For Your Report

Use the performance test results to compare:
- Single worker vs Multi-worker execution time
- Network overhead vs processing speedup
- Scalability analysis

## 🎥 Video Recording Tips

1. Show the terminal outputs clearly
2. Demonstrate both single and multi-worker runs
3. Highlight the performance differences
4. Show the final word count results
5. Keep it under 15 minutes as required

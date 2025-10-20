@echo off
echo Starting Local MapReduce with Bible Text...

echo Activating virtual environment...
call venv\Scripts\activate.bat

echo Starting Worker 1 on port 50051...
start "Worker 1" cmd /k "venv\Scripts\python.exe map_reduce_Worker.py 50051"

echo Starting Worker 2 on port 50052...
start "Worker 2" cmd /k "venv\Scripts\python.exe map_reduce_Worker.py 50052"

echo Waiting 3 seconds for workers to start...
timeout /t 3 /nobreak

echo Starting Master...
venv\Scripts\python.exe map_reduce_Master.py

echo MapReduce job completed!
pause

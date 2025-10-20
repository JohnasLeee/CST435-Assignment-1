@echo off
echo Starting Distributed MapReduce with Docker...

echo Building Docker images...
docker-compose build

echo Starting workers and master...
docker-compose up

echo MapReduce job completed!
pause

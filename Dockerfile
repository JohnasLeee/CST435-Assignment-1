# Dockerfile for MapReduce gRPC Workers
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Set Python to run in unbuffered mode
ENV PYTHONUNBUFFERED=1

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Generate gRPC code
RUN python gRPC_code_gen.py

# Expose port
EXPOSE 50051

# Default command (can be overridden)
CMD ["python", "map_reduce_Worker.py", "50051"]

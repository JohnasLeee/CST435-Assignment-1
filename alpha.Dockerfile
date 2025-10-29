FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN apt-get update && apt-get install -y --no-install-recommends \
    libfreetype6 \
    libpng16-16 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

# Generate gRPC Python stubs
RUN python -m grpc_tools.protoc -I /app/protos \
    --python_out=/app \
    --grpc_python_out=/app \
    /app/protos/pipeline.proto

CMD ["python", "alpha_service.py"]



FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    libeigen3-dev \
    nlohmann-json3-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

# Generate gRPC Python stubs
RUN python -m grpc_tools.protoc -I /app/protos \
    --python_out=/app \
    --grpc_python_out=/app \
    /app/protos/pipeline.proto

# Build C++ normalizer CLI
RUN cmake -S . -B build -DCMAKE_BUILD_TYPE=Release \
 && cmake --build build -j

ENV NORMALIZER_BIN=/app/build/normalizer_cli

CMD ["python", "normalizer_service.py"]

 
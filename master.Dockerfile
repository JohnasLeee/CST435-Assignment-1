FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

# Generate gRPC Python stubs
RUN python -m grpc_tools.protoc -I /app/protos \
    --python_out=/app \
    --grpc_python_out=/app \
    /app/protos/pipeline.proto

CMD ["python", "master.py"]



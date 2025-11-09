FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    libeigen3-dev \
    nlohmann-json3-dev \
    libgrpc++-dev \
    libprotobuf-dev \
    protobuf-compiler-grpc \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY CMakeLists.txt /app/
COPY main.cpp /app/
COPY src/ /app/src/
COPY protos/ /app/protos/

# Build C++ normalizer gRPC server
RUN cmake -S . -B build -DCMAKE_BUILD_TYPE=Release \
    && cmake --build build -j \
    && cmake --install build

ENV NORMALIZER_PORT=50051
ENV BACKTESTER_HOST=backtester
ENV BACKTESTER_PORT=50052
ENV GRPC_MAX_MESSAGE_MB=64

CMD ["/app/build/normalizer_server"]


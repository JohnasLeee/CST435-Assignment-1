# This script compiles the .proto file into Python code.
# Running this is a prerequisite for running the master and worker.

from grpc_tools import protoc

# The command to generate the gRPC code.
# -I.: Specifies the directory in which to search for .proto files (current directory).
# --python_out=.: Specifies the directory for the generated _pb2.py file.
# --grpc_python_out=.: Specifies the directory for the generated _pb2_grpc.py file.
# mapreduce.proto: The input .proto file.
protoc.main((
    '',
    '-I.',
    '--python_out=.',
    '--grpc_python_out=.',
    'gRPC_service_defination.proto',
))

print("gRPC code generated successfully from gRPC_service_defination.proto!")

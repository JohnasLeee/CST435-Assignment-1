#include "ICommServer.h"

#include <iostream>

// Stub GRPC server implementation.
// TODO: Integrate gRPC server, define protobuf schema, and wire bidirectional calls.
class GrpcServer : public ICommServer {
public:
    void start() override {
        std::cout << "[GrpcServer] Starting (stub). TODO: initialize gRPC server..." << std::endl;
    }

    void setHandler(RequestHandler handler) override {
        handler_ = std::move(handler);
    }

    std::string receiveData(const std::string &payloadJson) override {
        std::cout << "[GrpcServer] Received payload (stub)." << std::endl;
        if (!handler_) {
            std::cerr << "[GrpcServer] No handler set." << std::endl;
            return "{}";
        }
        return handler_(payloadJson);
    }

    void sendResponse(const std::string &responseJson) override {
        std::cout << "[GrpcServer] Sending response (stub): " << responseJson.substr(0, 120) << (responseJson.size()>120?"...":"") << std::endl;
    }

private:
    RequestHandler handler_;
};

// Factory function to create servers without exposing class in header
ICommServer* createGrpcServer() {
    return new GrpcServer();
}



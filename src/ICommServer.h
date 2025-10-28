#pragma once

#include <string>
#include <functional>

// Simple communication interface abstraction to allow plug-in of GRPC/REST implementations
class ICommServer {
public:
    using RequestHandler = std::function<std::string(const std::string&)>; // input JSON -> output JSON

    virtual ~ICommServer() = default;

    // Starts the server (blocking or non-blocking based on implementation)
    virtual void start() = 0;

    // Set the handler used to process incoming request payloads
    virtual void setHandler(RequestHandler handler) = 0;

    // For simple single-shot demo: receive a data payload and return the response
    virtual std::string receiveData(const std::string &payloadJson) = 0;

    // For simple single-shot demo: send response (could be a no-op in stubs)
    virtual void sendResponse(const std::string &responseJson) = 0;
};



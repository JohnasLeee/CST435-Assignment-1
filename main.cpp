#include <cstdlib>
#include <iostream>
#include <memory>
#include <string>

#include "src/Normalizer.h"
#include "src/ICommServer.h"
#include <nlohmann/json.hpp>

// Factory declarations from implementation files
ICommServer* createGrpcServer();
ICommServer* createRestServer();

static std::unique_ptr<ICommServer> makeServer(const std::string &commType) {
    if (commType == "GRPC") {
        std::cout << "[Main] Using GRPC protocol" << std::endl;
        return std::unique_ptr<ICommServer>(createGrpcServer());
    }
    if (commType == "REST") {
        std::cout << "[Main] Using REST protocol" << std::endl;
        return std::unique_ptr<ICommServer>(createRestServer());
    }
    std::cout << "[Main] Unknown COMM_TYPE='" << commType << "', defaulting to REST" << std::endl;
    return std::unique_ptr<ICommServer>(createRestServer());
}

int main() {
    const char* commTypeEnv = std::getenv("COMM_TYPE");
    const std::string commType = commTypeEnv ? std::string(commTypeEnv) : std::string("REST");
    const char* runTestsEnv = std::getenv("RUN_TESTS");

    Normalizer normalizer;

    if (runTestsEnv && std::string(runTestsEnv) == "1") {
        bool ok = normalizer.runUnitTest();
        std::cout << (ok ? "[Test] PASS" : "[Test] FAIL") << std::endl;
        return ok ? 0 : 1;
    }

    auto server = makeServer(commType);

    // Wire the request handler: JSON-in -> JSON-out
    server->setHandler([&normalizer](const std::string &payloadJson) {
        try {
            return normalizer.processJsonMatrix(payloadJson);
        } catch (const std::exception &ex) {
            std::cerr << "[Handler] Error: " << ex.what() << std::endl;
            return std::string("{}");
        }
    });

    // If REST, run server loop and let Alpha call POST /normalize
    if (commType == "REST") {
        server->setHandler([&normalizer](const std::string &payloadJson) {
            try {
                std::string out = normalizer.processJsonMatrix(payloadJson);
                // Log first 10 rows only
                nlohmann::json j = nlohmann::json::parse(out);
                const auto &data = j.at("data");
                std::size_t rowsToShow = std::min<std::size_t>(10, data.size());
                std::cout << "[Main] First " << rowsToShow << " rows:" << std::endl;
                for (std::size_t r = 0; r < rowsToShow; ++r) {
                    const auto &row = data.at(r);
                    std::cout << "Row " << r << ": [";
                    for (std::size_t c = 0; c < row.size(); ++c) {
                        std::cout << row.at(c).get<double>();
                        if (c + 1 < row.size()) std::cout << ", ";
                    }
                    std::cout << "]" << std::endl;
                }
            } catch (const std::exception &ex) {
                std::cerr << "[Handler] Error: " << ex.what() << std::endl;
            }
            return std::string("{}");
        });
        server->start();
        return 0; // never reached in simple loop
    }

    // For GRPC stub (not implemented), keep stdin single-shot path as fallback
    std::cout << "[Main] Waiting for payload on stdin (GRPC fallback)..." << std::endl;
    std::string inputJson;
    {
        std::ostringstream oss;
        oss << std::cin.rdbuf();
        inputJson = oss.str();
    }
    if (inputJson.empty()) {
        std::cerr << "[Main] No input received on stdin. Exiting." << std::endl;
        return 1;
    }
    std::string out = server->receiveData(inputJson);

    // Debug: log first 10 rows of the normalized matrix instead of returning to a client
    try {
        nlohmann::json j = nlohmann::json::parse(out);
        const auto &data = j.at("data");
        std::size_t rowsToShow = std::min<std::size_t>(10, data.size());
        std::cout << "[Main] First " << rowsToShow << " rows:" << std::endl;
        for (std::size_t r = 0; r < rowsToShow; ++r) {
            const auto &row = data.at(r);
            std::cout << "Row " << r << ": [";
            for (std::size_t c = 0; c < row.size(); ++c) {
                std::cout << row.at(c).get<double>();
                if (c + 1 < row.size()) std::cout << ", ";
            }
            std::cout << "]" << std::endl;
        }
    } catch (const std::exception &ex) {
        std::cerr << "[Main] Failed to log first 10 rows: " << ex.what() << std::endl;
    }

    // Keep stub response logging for visibility (no real client yet)
    server->sendResponse(out);

    return 0;
}



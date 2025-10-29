#include <cstdlib>
#include <iostream>
#include <memory>
#include <string>
#include <cstring>
#include <thread>
#include <chrono>

#include "src/Normalizer.h"
#include "src/ICommServer.h"
#include <nlohmann/json.hpp>

// Factory declarations from implementation files
ICommServer* createRestServer();

// Simple HTTP POST function (robust for large payloads)
std::string post_to_backtester(const std::string& json_data) {
    const char* backtester_host = std::getenv("BACKTESTER_HOST");
    const char* backtester_port = std::getenv("BACKTESTER_PORT");
    
    if (!backtester_host) backtester_host = "backtester";
    if (!backtester_port) backtester_port = "8082";
    
    std::string url = "http://" + std::string(backtester_host) + ":" + std::string(backtester_port) + "/backtest";
    
    // Write payload to a temp file to avoid shell-arg length/quoting limits
    const char* tmpPath = "/tmp/normalized_weights.json";
    {
        FILE* f = fopen(tmpPath, "wb");
        if (!f) return std::string("");
        size_t wrote = fwrite(json_data.data(), 1, json_data.size(), f);
        (void)wrote;
        fclose(f);
    }

    // Post using --data-binary @file and capture response
    std::string cmd = std::string("curl -s -f -H 'Content-Type: application/json' --data-binary @") + tmpPath + " " + url + " 2>/dev/null";

    // Retry a few times in case backtester isn't quite ready
    std::string result;
    for (int attempt = 1; attempt <= 5; ++attempt) {
        FILE* pipe = popen(cmd.c_str(), "r");
        if (!pipe) {
            continue;
        }
        char buffer[256];
        result.clear();
        while (fgets(buffer, sizeof buffer, pipe) != nullptr) {
            result += buffer;
        }
        int status = pclose(pipe);
        if (status == 0 && !result.empty()) {
            break;
        }
        // brief backoff
        std::this_thread::sleep_for(std::chrono::seconds(2));
    }
    return result;
}

static std::unique_ptr<ICommServer> makeServer() {
    std::cout << "[Main] Using REST protocol" << std::endl;
    return std::unique_ptr<ICommServer>(createRestServer());
}

int main() {
    const char* runTestsEnv = std::getenv("RUN_TESTS");

    Normalizer normalizer;

    if (runTestsEnv && std::string(runTestsEnv) == "1") {
        bool ok = normalizer.runUnitTest();
        std::cout << (ok ? "[Test] PASS" : "[Test] FAIL") << std::endl;
        return ok ? 0 : 1;
    }

    auto server = makeServer();

    // Wire the request handler: JSON-in -> JSON-out
    auto logAndProcess = [&normalizer](const std::string &payloadJson) -> std::string {
        try {
            std::string out = normalizer.processJsonMatrix(payloadJson);
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
            
            // Send normalized weights to backtester
            std::cout << "[Main] Sending normalized weights to backtester..." << std::endl;
            std::string backtester_response = post_to_backtester(out);
            if (!backtester_response.empty() && backtester_response.find("received") != std::string::npos) {
                std::cout << "[Main] Backtester acknowledged receipt: " << backtester_response << std::endl;
            } else {
                std::cerr << "[Main] Failed to get acknowledgment from backtester" << std::endl;
            }
            
            // Return the normalized weights JSON
            return out;
        } catch (const std::exception &ex) {
            std::cerr << "[Handler] Error: " << ex.what() << std::endl;
            return std::string("{}");
        }
    };
    server->setHandler(logAndProcess);
    server->start();
    return 0;
}



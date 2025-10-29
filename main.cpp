#include <cstdlib>
#include <iostream>
#include <memory>
#include <string>

#include "src/Normalizer.h"
#include "src/ICommServer.h"
#include <nlohmann/json.hpp>

// Factory declarations from implementation files
ICommServer* createRestServer();

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
            return std::string("{}");
        } catch (const std::exception &ex) {
            std::cerr << "[Handler] Error: " << ex.what() << std::endl;
            return std::string("{}");
        }
    };
    server->setHandler(logAndProcess);
    server->start();
    return 0;
}



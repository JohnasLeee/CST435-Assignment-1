#include <cstdlib>
#include <iostream>
#include <memory>
#include <string>
#include <sstream>

#include "src/Normalizer.h"
int main() {
    const char* runTestsEnv = std::getenv("RUN_TESTS");

    Normalizer normalizer;

    if (runTestsEnv && std::string(runTestsEnv) == "1") {
        bool ok = normalizer.runUnitTest();
        std::cout << (ok ? "[Test] PASS" : "[Test] FAIL") << std::endl;
        return ok ? 0 : 1;
    }

    // Read entire stdin as JSON payload
    std::ostringstream oss;
    oss << std::cin.rdbuf();
    std::string inputJson = oss.str();
    if (inputJson.empty()) {
        std::cerr << "[Main] No input received on stdin. Exiting." << std::endl;
        return 1;
    }

    try {
        std::string out = normalizer.processJsonMatrix(inputJson);
        // Write normalized JSON to stdout (no extra logs)
        std::cout << out;
        return 0;
    } catch (const std::exception &ex) {
        std::cerr << "[Main] Error: " << ex.what() << std::endl;
        return 1;
    }
}



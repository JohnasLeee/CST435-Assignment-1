#include <cstdlib>
#include <iostream>
#include <memory>
#include <string>
#include <cstring>
#include <thread>
#include <chrono>
#include <sstream>
#include <sys/socket.h>
#include <netinet/in.h>
#include <netdb.h>
#include <unistd.h>

#include "src/Normalizer.h"
#include "src/ICommServer.h"
#include <nlohmann/json.hpp>

// Factory declarations from implementation files
ICommServer *createRestServer();

// Native HTTP POST (no subprocess overhead)
std::string post_to_backtester(const std::string &json_data)
{
    const char *backtester_host = std::getenv("BACKTESTER_HOST");
    const char *backtester_port = std::getenv("BACKTESTER_PORT");

    if (!backtester_host)
        backtester_host = "backtester";
    if (!backtester_port)
        backtester_port = "8082";

    std::cout << "[DEBUG] Posting to " << backtester_host << ":" << backtester_port << " (native socket)" << std::endl;

    for (int attempt = 1; attempt <= 5; ++attempt)
    {
        struct hostent *server = gethostbyname(backtester_host);
        if (!server)
        {
            std::cerr << "[DEBUG] DNS lookup failed, attempt " << attempt << "/5" << std::endl;
            std::this_thread::sleep_for(std::chrono::seconds(2));
            continue;
        }

        int sockfd = socket(AF_INET, SOCK_STREAM, 0);
        if (sockfd < 0)
            continue;

        struct sockaddr_in serv_addr;
        memset(&serv_addr, 0, sizeof(serv_addr));
        serv_addr.sin_family = AF_INET;
        memcpy(&serv_addr.sin_addr.s_addr, server->h_addr, server->h_length);
        serv_addr.sin_port = htons(std::stoi(backtester_port));

        if (connect(sockfd, (struct sockaddr *)&serv_addr, sizeof(serv_addr)) < 0)
        {
            close(sockfd);
            std::cerr << "[DEBUG] Connection failed, attempt " << attempt << "/5" << std::endl;
            std::this_thread::sleep_for(std::chrono::seconds(2));
            continue;
        }

        std::ostringstream request;
        request << "POST /backtest HTTP/1.1\r\n";
        request << "Host: " << backtester_host << "\r\n";
        request << "Content-Type: application/json\r\n";
        request << "Content-Length: " << json_data.length() << "\r\n";
        request << "Connection: close\r\n\r\n";
        request << json_data;

        std::string req_str = request.str();
        send(sockfd, req_str.c_str(), req_str.length(), 0);

        std::string response;
        char buffer[4096];
        ssize_t received;
        while ((received = recv(sockfd, buffer, sizeof(buffer) - 1, 0)) > 0)
        {
            buffer[received] = '\0';
            response.append(buffer, received);
        }
        close(sockfd);

        size_t header_end = response.find("\r\n\r\n");
        if (header_end != std::string::npos && response.find("200") != std::string::npos)
        {
            std::cout << "[DEBUG] HTTP POST successful, attempt " << attempt << "/5" << std::endl;
            return response.substr(header_end + 4);
        }
        std::this_thread::sleep_for(std::chrono::seconds(2));
    }
    return "";
}

static std::unique_ptr<ICommServer> makeServer()
{
    std::cout << "[Main] Using REST protocol" << std::endl;
    return std::unique_ptr<ICommServer>(createRestServer());
}

int main()
{
    const char *runTestsEnv = std::getenv("RUN_TESTS");

    Normalizer normalizer;

    if (runTestsEnv && std::string(runTestsEnv) == "1")
    {
        bool ok = normalizer.runUnitTest();
        std::cout << (ok ? "[Test] PASS" : "[Test] FAIL") << std::endl;
        return ok ? 0 : 1;
    }

    auto server = makeServer();

    // Wire the request handler: JSON-in -> JSON-out
    auto logAndProcess = [&normalizer](const std::string &payloadJson) -> std::string
    {
        try
        {
            std::string out = normalizer.processJsonMatrix(payloadJson);
            nlohmann::json j = nlohmann::json::parse(out);
            const auto &data = j.at("data");
            std::size_t rowsToShow = std::min<std::size_t>(10, data.size());
            std::cout << "[Main] First " << rowsToShow << " rows:" << std::endl;
            for (std::size_t r = 0; r < rowsToShow; ++r)
            {
                const auto &row = data.at(r);
                std::cout << "Row " << r << ": [";
                for (std::size_t c = 0; c < row.size(); ++c)
                {
                    std::cout << row.at(c).get<double>();
                    if (c + 1 < row.size())
                        std::cout << ", ";
                }
                std::cout << "]" << std::endl;
            }

            // Send normalized weights to backtester
            double payload_size_mb = static_cast<double>(out.size()) / (1024.0 * 1024.0);
            std::cout << "[Main] Sending normalized weights to backtester..." << std::endl;
            std::cout << "[DEBUG] Payload size: " << payload_size_mb << " MB" << std::endl;

            auto overall_start = std::chrono::high_resolution_clock::now();
            auto call_start = std::chrono::high_resolution_clock::now();
            std::string backtester_response = post_to_backtester(out);
            auto call_end = std::chrono::high_resolution_clock::now();
            auto overall_end = std::chrono::high_resolution_clock::now();

            std::chrono::duration<double> call_elapsed = call_end - call_start;
            std::chrono::duration<double> overall_elapsed = overall_end - overall_start;

            double transfer_speed = (call_elapsed.count() > 0) ? (payload_size_mb / call_elapsed.count()) : 0.0;

            std::cout << "[TIMING] Normalizer -> Backtester (pure HTTP call, no retries): "
                      << call_elapsed.count() << " seconds" << std::endl;
            std::cout << "[TIMING] Normalizer -> Backtester (with setup, no retries): "
                      << overall_elapsed.count() << " seconds" << std::endl;
            std::cout << "[DEBUG] Transfer speed: " << transfer_speed << " MB/s" << std::endl;

            if (!backtester_response.empty() && backtester_response.find("received") != std::string::npos)
            {
                std::cout << "[Main] Backtester acknowledged receipt: " << backtester_response << std::endl;
            }
            else
            {
                std::cerr << "[Main] Failed to get acknowledgment from backtester" << std::endl;
            }

            // Return the normalized weights JSON
            return out;
        }
        catch (const std::exception &ex)
        {
            std::cerr << "[Handler] Error: " << ex.what() << std::endl;
            return std::string("{}");
        }
    };
    server->setHandler(logAndProcess);
    server->start();
    return 0;
}

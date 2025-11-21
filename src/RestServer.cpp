#include "ICommServer.h"

#include <iostream>
#include <string>
#include <cstdlib>

#include <sys/types.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <unistd.h>

namespace
{
    int create_listen_socket(int port)
    {
        int server_fd = ::socket(AF_INET, SOCK_STREAM, 0);
        if (server_fd < 0)
            return -1;

        int opt = 1;
        setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

        sockaddr_in addr{};
        addr.sin_family = AF_INET;
        addr.sin_addr.s_addr = htonl(INADDR_ANY);
        addr.sin_port = htons(static_cast<uint16_t>(port));

        if (bind(server_fd, reinterpret_cast<sockaddr *>(&addr), sizeof(addr)) < 0)
        {
            ::close(server_fd);
            return -1;
        }
        if (listen(server_fd, 16) < 0)
        {
            ::close(server_fd);
            return -1;
        }
        return server_fd;
    }

    bool read_http_request(int client_fd, std::string &method, std::string &path, std::string &body)
    {
        char buf[8192];
        ssize_t n = recv(client_fd, buf, sizeof(buf), 0);
        if (n <= 0)
            return false;
        std::string req(buf, static_cast<size_t>(n));

        // Find header/body split
        auto pos = req.find("\r\n\r\n");
        if (pos == std::string::npos)
            return false;
        std::string headers = req.substr(0, pos + 4);
        body = req.substr(pos + 4);

        // Parse request line
        auto endLine = headers.find("\r\n");
        if (endLine == std::string::npos)
            return false;
        std::string requestLine = headers.substr(0, endLine);
        {
            size_t sp1 = requestLine.find(' ');
            size_t sp2 = requestLine.find(' ', sp1 + 1);
            if (sp1 == std::string::npos || sp2 == std::string::npos)
                return false;
            method = requestLine.substr(0, sp1);
            path = requestLine.substr(sp1 + 1, sp2 - sp1 - 1);
        }

        // Find content-length
        size_t clPos = headers.find("Content-Length:");
        size_t contentLength = 0;
        if (clPos != std::string::npos)
        {
            size_t lineEnd = headers.find("\r\n", clPos);
            std::string clLine = headers.substr(clPos, lineEnd - clPos);
            size_t colon = clLine.find(':');
            if (colon != std::string::npos)
            {
                std::string val = clLine.substr(colon + 1);
                // trim spaces
                size_t start = val.find_first_not_of(' ');
                if (start != std::string::npos)
                    val = val.substr(start);
                contentLength = static_cast<size_t>(std::stoul(val));
            }
        }

        // If body incomplete, read remaining
        while (body.size() < contentLength)
        {
            char tmp[4096];
            ssize_t m = recv(client_fd, tmp, sizeof(tmp), 0);
            if (m <= 0)
                break;
            body.append(tmp, tmp + m);
        }
        return true;
    }

    void write_http_response(int client_fd, int status, const std::string &text)
    {
        std::string statusText = (status == 200 ? "OK" : "ERROR");
        std::string body = text;
        std::string resp = "HTTP/1.1 " + std::to_string(status) + " " + statusText + "\r\n";
        // Use JSON content type if the body looks like JSON
        if (status == 200 && !body.empty() && body[0] == '{')
        {
            resp += "Content-Type: application/json\r\n";
        }
        else
        {
            resp += "Content-Type: text/plain\r\n";
        }
        resp += "Content-Length: " + std::to_string(body.size()) + "\r\n";
        resp += "Connection: close\r\n\r\n";
        resp += body;
        send(client_fd, resp.data(), resp.size(), 0);
    }
}

// Minimal REST server implementation serving POST /normalize
class RestServer : public ICommServer
{
public:
    void start() override
    {
        int port = 8080;
        if (const char *p = std::getenv("NORMALIZER_PORT"))
        {
            try
            {
                port = std::stoi(p);
            }
            catch (...)
            {
            }
        }
        std::cout << "[RestServer] Listening on 0.0.0.0:" << port << std::endl;
        int server_fd = create_listen_socket(port);
        if (server_fd < 0)
        {
            std::cerr << "[RestServer] Failed to bind port " << port << std::endl;
            return;
        }

        while (true)
        {
            sockaddr_in client{};
            socklen_t clen = sizeof(client);
            int cfd = accept(server_fd, reinterpret_cast<sockaddr *>(&client), &clen);
            if (cfd < 0)
                continue;

            std::string method, path, body;
            if (!read_http_request(cfd, method, path, body))
            {
                write_http_response(cfd, 400, "Bad Request");
                ::close(cfd);
                continue;
            }

            if (method == "POST" && path == "/normalize")
            {
                if (!handler_)
                {
                    std::cerr << "[RestServer] No handler set." << std::endl;
                    write_http_response(cfd, 500, "No handler");
                }
                else
                {
                    try
                    {
                        // Process and return the normalized weights JSON
                        std::string normalized_weights = handler_(body);
                        write_http_response(cfd, 200, normalized_weights);
                    }
                    catch (const std::exception &ex)
                    {
                        std::cerr << "[RestServer] Handler error: " << ex.what() << std::endl;
                        write_http_response(cfd, 500, "Handler error");
                    }
                }
            }
            else if (method == "GET" && path == "/health")
            {
                write_http_response(cfd, 200, "{\"status\":\"healthy\",\"service\":\"normalizer\"}");
            }
            else
            {
                write_http_response(cfd, 404, "Not Found");
            }
            ::close(cfd);
        }
        ::close(server_fd);
    }

    void setHandler(RequestHandler handler) override
    {
        handler_ = std::move(handler);
    }

    std::string receiveData(const std::string &payloadJson) override
    {
        if (!handler_)
            return "{}";
        return handler_(payloadJson);
    }

    void sendResponse(const std::string &responseJson) override
    {
        // No-op for server-driven HTTP
        (void)responseJson;
    }

private:
    RequestHandler handler_;
};

// Factory function to create servers without exposing class in header
ICommServer *createRestServer()
{
    return new RestServer();
}

#include <iostream>
#include <memory>
#include <string>
#include <thread>
#include <chrono>
#include <cstdlib>

#include <grpcpp/grpcpp.h>
#include <nlohmann/json.hpp>

#include "pipeline.grpc.pb.h"
#include "Normalizer.h"

using grpc::Channel;
using grpc::ClientContext;
using grpc::Server;
using grpc::ServerBuilder;
using grpc::ServerContext;
using grpc::Status;

using pipeline::Ack;
using pipeline::BacktesterService;
using pipeline::Matrix;
using pipeline::NormalizeRequest;
using pipeline::NormalizeResponse;
using pipeline::NormalizerService;
using pipeline::Row;
using pipeline::SubmitWeightsRequest;
using pipeline::SubmitWeightsResponse;

class NormalizerServiceImpl final : public NormalizerService::Service
{
private:
    Normalizer normalizer_;
    std::string backtester_host_;
    int backtester_port_;
    int max_msg_mb_;

    // Helper: Convert protobuf Matrix to JSON format expected by Normalizer
    std::string matrixToJson(const Matrix &matrix,
                             const google::protobuf::RepeatedPtrField<std::string> &dates,
                             const google::protobuf::RepeatedPtrField<std::string> &stocks)
    {
        nlohmann::json j;
        j["dates"] = std::vector<std::string>(dates.begin(), dates.end());
        j["stocks"] = std::vector<std::string>(stocks.begin(), stocks.end());
        j["index"] = j["dates"];
        j["columns"] = j["stocks"];

        nlohmann::json data = nlohmann::json::array();
        for (const auto &row : matrix.rows())
        {
            nlohmann::json row_array = nlohmann::json::array();
            for (double val : row.values())
            {
                row_array.push_back(val);
            }
            data.push_back(row_array);
        }
        j["data"] = data;
        return j.dump();
    }

    // Helper: Convert JSON back to protobuf Matrix
    Matrix jsonToMatrix(const std::string &json_str)
    {
        auto j = nlohmann::json::parse(json_str);
        Matrix matrix;

        const auto &data = j.at("data");
        for (const auto &row_array : data)
        {
            Row *row = matrix.add_rows();
            for (const auto &val : row_array)
            {
                row->add_values(val.is_null() ? 0.0 : val.get<double>());
            }
        }
        return matrix;
    }

    // Async processing function
    void processAsync(const NormalizeRequest &request, std::chrono::steady_clock::time_point receive_time)
    {
        try
        {
            auto compute_start = std::chrono::steady_clock::now();

            // Convert to JSON
            std::string json_input = matrixToJson(request.matrix(), request.dates(), request.stocks());

            // Process through Normalizer
            std::string json_output = normalizer_.processJsonMatrix(json_input);

            // Convert back to Matrix
            Matrix normalized = jsonToMatrix(json_output);

            auto compute_end = std::chrono::steady_clock::now();
            double compute_ms = std::chrono::duration<double, std::milli>(compute_end - compute_start).count();
            std::cout << "[TIMING] Normalization Computation: " << compute_ms << " ms" << std::endl;

            // Send to Backtester with timing
            auto backtester_overall_start = std::chrono::steady_clock::now();

            std::string target = backtester_host_ + ":" + std::to_string(backtester_port_);
            grpc::ChannelArguments args;
            args.SetMaxSendMessageSize(max_msg_mb_ * 1024 * 1024);
            args.SetMaxReceiveMessageSize(max_msg_mb_ * 1024 * 1024);

            auto channel = grpc::CreateCustomChannel(target, grpc::InsecureChannelCredentials(), args);
            auto stub = BacktesterService::NewStub(channel);

            SubmitWeightsRequest backtester_req;
            *backtester_req.mutable_weights() = normalized;
            for (const auto &date : request.dates())
            {
                backtester_req.add_dates(date);
            }
            for (const auto &stock : request.stocks())
            {
                backtester_req.add_stocks(stock);
            }

            // Time the actual gRPC call (pure delivery time)
            SubmitWeightsResponse backtester_resp;
            ClientContext context;
            auto grpc_call_start = std::chrono::steady_clock::now();
            Status status = stub->SubmitWeights(&context, backtester_req, &backtester_resp);
            auto grpc_call_end = std::chrono::steady_clock::now();

            auto backtester_overall_end = std::chrono::steady_clock::now();

            double grpc_call_ms = std::chrono::duration<double, std::milli>(grpc_call_end - grpc_call_start).count();
            double backtester_total_ms = std::chrono::duration<double, std::milli>(backtester_overall_end - backtester_overall_start).count();

            std::cout << "[TIMING] Normalizer -> Backtester (pure gRPC call only, no retries): " << grpc_call_ms << " ms" << std::endl;
            std::cout << "[TIMING] Normalizer -> Backtester (total with setup, no retries): " << backtester_total_ms << " ms" << std::endl;

            auto total_end = std::chrono::steady_clock::now();
            double total_ms = std::chrono::duration<double, std::milli>(total_end - receive_time).count();
            std::cout << "[TIMING] Total Normalizer Processing (after ACK): " << total_ms << " ms" << std::endl;

            if (!status.ok())
            {
                std::cerr << "Failed to send to Backtester: " << status.error_message() << std::endl;
            }
        }
        catch (const std::exception &e)
        {
            std::cerr << "Async processing error: " << e.what() << std::endl;
        }
    }

public:
    NormalizerServiceImpl()
    {
        backtester_host_ = getenv("BACKTESTER_HOST") ? getenv("BACKTESTER_HOST") : "backtester";
        backtester_port_ = getenv("BACKTESTER_PORT") ? std::atoi(getenv("BACKTESTER_PORT")) : 50052;
        max_msg_mb_ = getenv("GRPC_MAX_MESSAGE_MB") ? std::atoi(getenv("GRPC_MAX_MESSAGE_MB")) : 64;
    }

    Status Normalize(ServerContext *context, const NormalizeRequest *request,
                     NormalizeResponse *response) override
    {
        auto receive_time = std::chrono::steady_clock::now();

        // Calculate message receive time (from request arrival to ACK send)
        auto ack_send_time = std::chrono::steady_clock::now();
        double receive_process_ms = std::chrono::duration<double, std::milli>(ack_send_time - receive_time).count();
        std::cout << "[TIMING] Alpha -> Normalizer (receive + ACK, no retries): " << receive_process_ms << " ms" << std::endl;

        // Start async processing
        std::thread(&NormalizerServiceImpl::processAsync, this, *request, receive_time).detach();

        // Return ACK immediately
        response->mutable_ack()->set_ok(true);
        response->mutable_ack()->set_message("Request received, processing async");

        return Status::OK;
    }
};

void RunServer()
{
    int port = getenv("NORMALIZER_PORT") ? std::atoi(getenv("NORMALIZER_PORT")) : 50051;
    int max_msg_mb = getenv("GRPC_MAX_MESSAGE_MB") ? std::atoi(getenv("GRPC_MAX_MESSAGE_MB")) : 64;

    std::string server_address = "0.0.0.0:" + std::to_string(port);
    NormalizerServiceImpl service;

    ServerBuilder builder;
    builder.AddListeningPort(server_address, grpc::InsecureServerCredentials());
    builder.RegisterService(&service);
    builder.SetMaxSendMessageSize(max_msg_mb * 1024 * 1024);
    builder.SetMaxReceiveMessageSize(max_msg_mb * 1024 * 1024);

    std::unique_ptr<Server> server(builder.BuildAndStart());
    std::cout << "Normalizer C++ gRPC server listening on " << server_address << std::endl;

    server->Wait();
}

int main(int argc, char **argv)
{
    RunServer();
    return 0;
}

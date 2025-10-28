#include "Normalizer.h"

#include <limits>
#include <stdexcept>
#include <iostream>

#include <nlohmann/json.hpp>

using json = nlohmann::json;

bool Normalizer::isNaN(double v) {
    return std::isnan(v);
}

Eigen::MatrixXd Normalizer::parseJsonToMatrix(
    const std::string &jsonString,
    std::vector<std::string> &outIndex,
    std::vector<std::string> &outColumns
) const {
    json j = json::parse(jsonString);

    // Accept either (index, columns) or (dates, stocks)
    const char* kIndex = j.contains("index") ? "index" : (j.contains("dates") ? "dates" : nullptr);
    const char* kCols  = j.contains("columns") ? "columns" : (j.contains("stocks") ? "stocks" : nullptr);
    if (kIndex == nullptr || kCols == nullptr || !j.contains("data")) {
        throw std::runtime_error("Invalid JSON: expected keys (index|dates), (columns|stocks), data");
    }
    outIndex = j.at(kIndex).get<std::vector<std::string>>();
    outColumns = j.at(kCols).get<std::vector<std::string>>();
    const auto rows = outIndex.size();
    const auto cols = outColumns.size();

    const auto &data = j.at("data");
    if (!data.is_array() || data.size() != rows) {
        throw std::runtime_error("Invalid JSON: data row count mismatch");
    }


    Eigen::MatrixXd mat(rows, cols);
    for (size_t r = 0; r < rows; ++r) {
        const auto &rowArr = data.at(r);
        if (!rowArr.is_array() || rowArr.size() != cols) {
            throw std::runtime_error("Invalid JSON: data col count mismatch");
        }
        for (size_t c = 0; c < cols; ++c) {
            const auto &cell = rowArr.at(c);
            if (cell.is_null()) {
                mat(static_cast<Eigen::Index>(r), static_cast<Eigen::Index>(c)) = std::numeric_limits<double>::quiet_NaN();
            } else if (cell.is_number()) {
                mat(static_cast<Eigen::Index>(r), static_cast<Eigen::Index>(c)) = cell.get<double>();
            } else {
                // try parse string numbers; anything else becomes NaN
                try {
                    mat(static_cast<Eigen::Index>(r), static_cast<Eigen::Index>(c)) = std::stod(cell.get<std::string>());
                } catch (...) {
                    mat(static_cast<Eigen::Index>(r), static_cast<Eigen::Index>(c)) = std::numeric_limits<double>::quiet_NaN();
                }
            }
        }
    }
    return mat;
}

std::string Normalizer::matrixToJson(
    const Eigen::MatrixXd &matrix,
    const std::vector<std::string> &index,
    const std::vector<std::string> &columns
) const {
    json j;
    j["index"] = index;
    j["columns"] = columns;

    json data = json::array();
    for (Eigen::Index r = 0; r < matrix.rows(); ++r) {
        json row = json::array();
        for (Eigen::Index c = 0; c < matrix.cols(); ++c) {
            double v = matrix(r, c);
            if (isNaN(v)) {
                row.push_back(0.0); // serialize NaN as 0.0 as requested
            } else {
                row.push_back(v);
            }
        }
        data.push_back(row);
    }
    j["data"] = data;
    return j.dump();
}

void Normalizer::neutralizeRow(Eigen::VectorXd &row) const {
    double sum = 0.0;
    int count = 0;
    for (Eigen::Index i = 0; i < row.size(); ++i) {
        if (!isNaN(row(i))) {
            sum += row(i);
            ++count;
        }
    }
    if (count == 0) {
        return; // nothing to do
    }
    double mean = sum / static_cast<double>(count);
    for (Eigen::Index i = 0; i < row.size(); ++i) {
        if (!isNaN(row(i))) {
            row(i) = row(i) - mean;
        }
    }
}

void Normalizer::normalizeRowL1(Eigen::VectorXd &row) const {
    double l1sum = 0.0;
    for (Eigen::Index i = 0; i < row.size(); ++i) {
        if (!isNaN(row(i))) {
            l1sum += std::abs(row(i));
        }
    }
    if (l1sum <= 0.0) {
        return; // all zeros or no valid values
    }
    for (Eigen::Index i = 0; i < row.size(); ++i) {
        if (!isNaN(row(i))) {
            row(i) = row(i) / l1sum;
        }
    }
}

Eigen::MatrixXd Normalizer::processMatrix(const Eigen::MatrixXd &inputWithNaNs) const {
    Eigen::MatrixXd result = inputWithNaNs;
    for (Eigen::Index r = 0; r < result.rows(); ++r) {
        Eigen::VectorXd row = result.row(r).transpose();
        neutralizeRow(row);
        normalizeRowL1(row);
        // Set NaN positions to 0 as requested for output
        for (Eigen::Index i = 0; i < row.size(); ++i) {
            if (isNaN(inputWithNaNs(r, i))) {
                row(i) = 0.0;
            }
        }
        result.row(r) = row.transpose();
    }
    return result;
}

std::string Normalizer::processJsonMatrix(const std::string &jsonString) const {
    std::vector<std::string> index;
    std::vector<std::string> columns;
    Eigen::MatrixXd mat = parseJsonToMatrix(jsonString, index, columns);
    Eigen::MatrixXd out = processMatrix(mat);
    return matrixToJson(out, index, columns);
}

bool Normalizer::runUnitTest() const {
    Eigen::VectorXd v(3);
    v << 2.0, 4.0, 6.0;
    Eigen::MatrixXd m(1,3);
    m.row(0) = v.transpose();
    Eigen::MatrixXd res = processMatrix(m);
    // Expected after neutralize: [-2, 0, 2] (mean=4)
    // L1 sum = 4, normalized => [-0.5, 0, 0.5]
    const double eps = 1e-9;
    return std::abs(res(0,0) + 0.5) < eps && std::abs(res(0,1) - 0.0) < eps && std::abs(res(0,2) - 0.5) < eps;
}



#pragma once

#include <string>
#include <vector>
#include <map>

#include <Eigen/Dense>

class Normalizer {
public:
    // Parse a JSON string with schema {"index":[], "columns":[], "data":[[...] , ...]}
    // Numbers may be null; we treat them as NaN during processing and output zeros in those positions.
    // Returns a matrix with NaNs where inputs were missing, and fills out index/columns labels.
    Eigen::MatrixXd parseJsonToMatrix(
        const std::string &jsonString,
        std::vector<std::string> &outIndex,
        std::vector<std::string> &outColumns
    ) const;

    // Convert matrix back to JSON string using the same schema. Any NaN values will be serialized as 0.0.
    std::string matrixToJson(
        const Eigen::MatrixXd &matrix,
        const std::vector<std::string> &index,
        const std::vector<std::string> &columns
    ) const;

    // Process the matrix row-wise: neutralize then L1 normalize each row using only valid entries.
    // Invalid entries (NaN in input) are set to 0 in the output.
    Eigen::MatrixXd processMatrix(const Eigen::MatrixXd &inputWithNaNs) const;

    // Convenience end-to-end from JSON to JSON
    std::string processJsonMatrix(const std::string &jsonString) const;

    // Bonus: small unit test convenience to verify vector behavior.
    // Returns true if the test passes.
    bool runUnitTest() const;

private:
    // Subtract mean of valid entries in the row; invalid entries are ignored in mean and left as is (NaN) here.
    void neutralizeRow(Eigen::VectorXd &row) const;

    // Scale so that sum of absolute values across valid entries is 1. If all-zero or no valid entries, leave as is.
    void normalizeRowL1(Eigen::VectorXd &row) const;

    // Helpers for NaN handling
    static bool isNaN(double v);
};



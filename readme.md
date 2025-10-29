# Normalizer Service

Microservice that neutralizes and normalizes alpha matrices using REST.

## Quick Start

```powershell
# Build and run
docker compose up --build
```

## Architecture

- **Master**: Triggers pipeline
- **Alpha**: Calculates -rank(returns) and sends to Normalizer
- **Normalizer**: Neutralizes and L1-normalizes matrices (outputs first 10 rows to logs)
- **Backtester (Coming Soon)**: Calculates PnL and relevant metrics



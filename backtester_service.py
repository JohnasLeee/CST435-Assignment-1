"""
Backtester Service - Performs backtesting on normalized weights from Normalizer Service
"""

import os
import sys
import json
import logging
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
from typing import Dict, Any, Optional
import grpc
from concurrent import futures
import threading
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import utils

import pipeline_pb2 as pb2  # type: ignore
import pipeline_pb2_grpc as pb2_grpc  # type: ignore

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

_STATUS_LOCK = threading.Lock()
_LATEST_STATUS: Dict[str, Any] = {"done": False, "summary_json": ""}
_LATEST_RETURNS: Dict[str, Any] = {}
_LATEST_WEIGHTS: Dict[str, Any] = {}


class BacktesterCore:
    """Core backtesting computation logic"""
    
    def __init__(self, alpha_host='alpha', alpha_port=50050):
        self.alpha_host = alpha_host
        self.alpha_port = alpha_port
    
    def fetch_returns_matrix(self, max_retries=3, returns_data=None) -> Optional[pd.DataFrame]:
        """Use returns provided in payload or fetch locally as fallback."""
        if returns_data is not None:
            # Returns provided from Alpha via gRPC
            logger.info("[Backtester] Using returns data provided by Alpha")
            dates = returns_data.get("dates", [])
            stocks = returns_data.get("stocks", [])
            data = returns_data.get("data", [])
            if dates and stocks and data:
                try:
                    idx = pd.to_datetime(dates)
                    df = pd.DataFrame(data, index=idx, columns=stocks)
                    logger.info(f"[Backtester] Returns matrix shape: {df.shape}")
                    return df
                except Exception as e:
                    logger.error(f"[Backtester] Error parsing provided returns: {e}")
        
        # Fallback to local fetch if not provided
        try:
            data = utils.get_SP500()
            if data is None:
                return None
            # Compute returns from Close columns
            returns_columns = []
            if isinstance(data.columns, pd.MultiIndex):
                tickers = data.columns.get_level_values(0).unique()
                for ticker in tickers:
                    close_col = (ticker, 'Close')
                    if close_col in data.columns:
                        close_prices = data[close_col]
                        returns = close_prices.pct_change(fill_method=None)
                        returns_columns.append(pd.DataFrame({ticker: returns}))
            if returns_columns:
                returns_df = pd.concat(returns_columns, axis=1)
                logger.info(f"[Backtester] Returns matrix shape (fallback): {returns_df.shape}")
                return returns_df
            return None
        except Exception as e:
            logger.error(f"[Backtester] Error computing returns locally: {e}")
            return None
    
    def align_data(self, weights_df: pd.DataFrame, returns_df: pd.DataFrame) -> tuple:
        """Align weights and returns DataFrames by dates and stocks"""
        logger.info("[Backtester] Aligning weights and returns...")
        
        # Get common dates
        common_dates = weights_df.index.intersection(returns_df.index)
        logger.info(f"[Backtester] Common dates: {len(common_dates)}")
        
        # Get common stocks
        common_stocks = weights_df.columns.intersection(returns_df.columns)
        logger.info(f"[Backtester] Common stocks: {len(common_stocks)}")
        
        # Align by common dates and stocks
        weights_aligned = weights_df.loc[common_dates, common_stocks]
        returns_aligned = returns_df.loc[common_dates, common_stocks]

        # IMPORTANT: Use previous day's weights for today's returns (weights_{t-1} * returns_{t})
        # Shift weights forward by one day so row t contains weights from t-1
        weights_aligned = weights_aligned.shift(-1)

        # Drop the first day (no previous weights available) and keep returns as-is for those dates
        if len(weights_aligned) > 0:
            weights_aligned = weights_aligned.iloc[1:]
            returns_aligned = returns_aligned.iloc[1:]

        # Safety: fill any residual NaNs in returns with zeros; weights should be clean after trim
        returns_aligned = returns_aligned.fillna(0)
        
        logger.info(f"[Backtester] Aligned (weights_{'{t-1}'} to returns_{'{t}'}) shape: {weights_aligned.shape}")
        return weights_aligned, returns_aligned
    
    def compute_daily_pnl(self, weights_df: pd.DataFrame, returns_df: pd.DataFrame) -> pd.Series:
        """Compute daily portfolio PnL in dollars using $book_size and L1-normalized weights.
        Uses weights from previous day and returns of today (already aligned by align_data).
        """
        logger.info("[Backtester] Computing daily portfolio PnL (dollar PnL with L1-normalized weights)...")

        # Total gross book size in dollars (default $20,000,000)
        book_size = 20000000.0

        # L1-normalize weights row-wise so sum(abs(weights)) == 1
        l1 = weights_df.abs().sum(axis=1)
        # Avoid div-by-zero: rows with zero exposure become zeros
        weights_norm = weights_df.div(l1.replace(0, np.nan), axis=0).fillna(0.0)

        # Dollar positions for each stock per day
        positions = weights_norm * book_size

        # Daily dollar PnL: Σ position_{t-1,i} * return_{t,i}
        daily_pnl = (positions * returns_df).sum(axis=1)

        logger.info(f"[Backtester] Daily PnL computed for {len(daily_pnl)} days (book size ${book_size:,.0f})")
        return daily_pnl
    
    def compute_cumulative_pnl(self, daily_pnl: pd.Series) -> pd.Series:
        """Compute cumulative PnL in dollars"""
        cumulative_pnl = daily_pnl.cumsum()
        return cumulative_pnl
    
    def compute_sharpe_ratio(self, daily_pnl: pd.Series) -> float:
        """Compute annualized Sharpe ratio using portfolio daily returns (PnL / book_size)"""
        if len(daily_pnl) == 0 or daily_pnl.std() == 0:
            return 0.0

        # Convert dollar PnL to returns using same book size used to size positions
        try:
            book_size = float(os.getenv('BOOK_SIZE', '20000000'))
        except Exception:
            book_size = 20000000.0
        portfolio_returns = daily_pnl / book_size

        if portfolio_returns.std() == 0:
            return 0.0

        mean_return = portfolio_returns.mean()
        std_return = portfolio_returns.std()
        
        if std_return == 0:
            return 0.0
        
        # Annualize: multiply by sqrt(252) for daily returns
        sharpe = (mean_return / std_return) * np.sqrt(252)
        return sharpe
    
    def compute_turnover(self, weights_df: pd.DataFrame) -> float:
        """Compute average absolute day-to-day change in L1-normalized weights.
        This aligns with DollarTradingValue / Booksize since positions are sized
        by book size using L1-normalized weights.
        """
        logger.info("[Backtester] Computing turnover (based on L1-normalized weights)...")

        if len(weights_df) < 2:
            return 0.0

        # L1-normalize each day
        l1 = weights_df.abs().sum(axis=1)
        weights_norm = weights_df.div(l1.replace(0, np.nan), axis=0).fillna(0.0)

        # Absolute day-to-day weight change
        diffs = weights_norm.diff().abs()
        daily_turnover = diffs.sum(axis=1)

        turnover = daily_turnover.iloc[1:].mean() if len(daily_turnover) > 1 else 0.0
        logger.info(f"[Backtester] Turnover: {turnover:.4f}")
        return turnover
    
    def compute_max_drawdown(self, cumulative_pnl: pd.Series) -> float:
        """Compute maximum drawdown as a fraction of 0.5 * book size (percentage basis)."""
        if len(cumulative_pnl) == 0:
            return 0.0

        running_max = cumulative_pnl.cummax()
        drawdown = running_max - cumulative_pnl  # positive dollars
        max_dd_dollars = drawdown.max()

        try:
            book_size = float(os.getenv('BOOK_SIZE', '20000000'))
        except Exception:
            book_size = 20000000.0

        denom = 0.5 * book_size if book_size > 0 else 1.0
        max_dd_frac = float(max_dd_dollars) / denom

        logger.info(f"[Backtester] Maximum drawdown: {max_dd_frac:.4f} (fraction of 0.5*Book)")
        return max_dd_frac
    
    def compute_annual_return(self, daily_pnl: pd.Series) -> float:
        """Annual return as defined: AnnualizedPnL / (0.5 * BookSize)."""
        try:
            book_size = float(os.getenv('BOOK_SIZE', '20000000'))
        except Exception:
            book_size = 20000000.0
        if len(daily_pnl) == 0:
            return 0.0
        annualized_pnl = daily_pnl.mean() * 252.0
        denom = 0.5 * book_size if book_size > 0 else 1.0
        return float(annualized_pnl) / denom

    def compute_fitness_score(self, sharpe: float, annual_return: float, turnover: float) -> float:
        """Fitness = Sharpe * sqrt( abs(Returns) / max(Turnover, 0.125) )."""
        denom = max(turnover, 0.125)
        if denom <= 0:
            return 0.0
        fitness = sharpe * np.sqrt(abs(annual_return) / denom)
        logger.info(f"[Backtester] Fitness score: {fitness:.4f}")
        return fitness
    
    def plot_pnl_chart(self, cumulative_pnl: pd.Series, output_path: Optional[str] = None):
        """Plot cumulative PnL chart. If PNL_OUTPUT_DIR is set, save there."""
        out_dir = os.getenv('PNL_OUTPUT_DIR', '').strip()
        if not output_path:
            output_path = "pnl_chart.png"
        if out_dir:
            try:
                os.makedirs(out_dir, exist_ok=True)
                output_path = os.path.join(out_dir, output_path)
            except Exception as e:
                logger.warning(f"[Backtester] Could not create output dir '{out_dir}': {e}. Falling back to container path.")
        logger.info(f"[Backtester] Plotting PnL chart to {output_path}...")

        # Display in thousands of dollars (K$)
        pnl_k = cumulative_pnl / 1_000.0

        plt.figure(figsize=(12, 6))
        plt.plot(pnl_k.index, pnl_k.values, linewidth=2)
        plt.title('Cumulative Portfolio PnL', fontsize=16, fontweight='bold')
        plt.xlabel('Date', fontsize=12)
        plt.ylabel('Cumulative PnL (K$)', fontsize=12)
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        logger.info(f"[Backtester] Chart saved to {output_path}")
    
    def backtest(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Main backtesting method"""
        if not payload:
            logger.error("[Backtester] No payload provided")
            return None
            
        try:
            logger.info("[Backtester] ===== STARTING BACKTEST PROCESSING =====")
            
            # Step 1: Parse weights data
            logger.info("[Backtester] Step 1/8: Parsing weights data...")
            weights_data = payload.get("weights", payload)  # Support old format too
            weights_df = self._parse_weights_data(weights_data)
            if weights_df is None:
                logger.error("[Backtester] Failed to parse weights data")
                return None
            logger.info(f"[Backtester] ✓ Parsed {weights_df.shape[0]} days, {weights_df.shape[1]} stocks")
            
            # Step 2: Get returns (from payload if provided, else fetch)
            logger.info("[Backtester] Step 2/8: Getting returns data...")
            returns_data = payload.get("returns")
            returns_df = self.fetch_returns_matrix(returns_data=returns_data)
            if returns_df is None:
                logger.error("[Backtester] Failed to get returns")
                return None
            logger.info(f"[Backtester] ✓ Retrieved {returns_df.shape[0]} days, {returns_df.shape[1]} stocks")
            
            # Step 3: Align data
            logger.info("[Backtester] Step 3/8: Aligning weights and returns...")
            weights_aligned, returns_aligned = self.align_data(weights_df, returns_df)
            logger.info(f"[Backtester] ✓ Aligned data: {weights_aligned.shape[0]} days, {weights_aligned.shape[1]} stocks")
            
            # Step 4: Compute daily PnL
            logger.info("[Backtester] Step 4/8: Computing daily portfolio PnL...")
            daily_pnl = self.compute_daily_pnl(weights_aligned, returns_aligned)
            logger.info(f"[Backtester] ✓ Computed {len(daily_pnl)} daily PnL values")
            
            # Step 5: Compute cumulative PnL
            logger.info("[Backtester] Step 5/8: Computing cumulative PnL...")
            cumulative_pnl = self.compute_cumulative_pnl(daily_pnl)
            logger.info("[Backtester] ✓ Cumulative PnL computed")
            
            # Step 6: Compute metrics
            logger.info("[Backtester] Step 6/8: Computing performance metrics...")
            sharpe = self.compute_sharpe_ratio(daily_pnl)
            logger.info(f"[Backtester]   Sharpe Ratio: {sharpe:.4f}")

            turnover = self.compute_turnover(weights_aligned)
            logger.info(f"[Backtester]   Turnover: {turnover:.4f}")

            max_drawdown = self.compute_max_drawdown(cumulative_pnl)
            logger.info(f"[Backtester]   Max Drawdown (fraction of 0.5*Book): {max_drawdown:.4f}")

            annual_return = self.compute_annual_return(daily_pnl)
            logger.info(f"[Backtester]   Annual Return (fraction of 0.5*Book): {annual_return:.4f}")

            fitness = self.compute_fitness_score(sharpe, annual_return, turnover)
            logger.info(f"[Backtester]   Fitness Score: {fitness:.4f}")
            
            # Step 7: Plot chart
            logger.info("[Backtester] Step 7/8: Generating PnL chart...")
            chart_path = "pnl_chart.png"
            self.plot_pnl_chart(cumulative_pnl, chart_path)
            logger.info("[Backtester] ✓ Chart saved")
            
            # Step 8: Format output (ensure JSON-serializable keys/values)
            daily_pnl_dict = {(
                idx.strftime('%Y-%m-%d') if hasattr(idx, 'strftime') else str(idx)
            ): (float(val) if hasattr(val, 'item') else float(val)) for idx, val in daily_pnl.items()}

            result = {
                "daily_pnl": daily_pnl_dict,
                "cumulative_pnl": cumulative_pnl.tolist(),
                "sharpe": round(float(sharpe), 4),
                "turnover": round(float(turnover), 4),
                "max_drawdown": round(float(max_drawdown), 4),
                "annual_return": round(float(annual_return), 4),
                "fitness": round(float(fitness), 4),
                "pnl_chart_path": chart_path
            }
            
            logger.info("[Backtester] Step 8/8: Store results for polling...")
            with _STATUS_LOCK:
                _LATEST_STATUS["done"] = True
                _LATEST_STATUS["summary_json"] = json.dumps(result)
            
            logger.info("[Backtester] ===== BACKTEST COMPLETED SUCCESSFULLY =====")
            
            return result
            
        except Exception as e:
            logger.error(f"[Backtester] Backtest error: {e}")
            return None
    
    def _send_results_to_master(self, results: Dict[str, Any]):
        pass
    
    def _parse_weights_data(self, weights_data: Dict[str, Any]) -> Optional[pd.DataFrame]:
        """Parse weights JSON into DataFrame"""
        try:
            # Handle both 'index'/'dates' and 'columns'/'stocks' keys
            dates_key = "dates" if "dates" in weights_data else "index"
            stocks_key = "stocks" if "stocks" in weights_data else "columns"
            
            dates = weights_data.get(dates_key, [])
            stocks = weights_data.get(stocks_key, [])
            data = weights_data.get('data', [])
            
            if not dates or not stocks or not data:
                logger.error("[Backtester] Invalid weights data structure")
                return None
            
            # Create DataFrame with robust date handling
            try:
                idx = pd.to_datetime(dates, errors='raise')
            except Exception:
                logger.warning("[Backtester] Dates not parseable; using integer index instead")
                idx = pd.RangeIndex(start=0, stop=len(dates), step=1)

            df = pd.DataFrame(data, index=idx, columns=stocks)
            
            logger.info(f"[Backtester] Weights DataFrame shape: {df.shape}")
            return df
            
        except Exception as e:
            logger.error(f"[Backtester] Error parsing weights: {e}")
            return None


class BacktesterService(pb2_grpc.BacktesterServiceServicer):
    def __init__(self):
        self.alpha_host = os.getenv('ALPHA_HOST', 'alpha')
        self.alpha_port = int(os.getenv('ALPHA_PORT', '50050'))

    def SubmitWeights(self, request: pb2.SubmitWeightsRequest, context):
        logger.info("[Backtester] Received SubmitWeights request")
        weights = [[float(v) for v in row.values] for row in request.weights.rows]
        dates = list(request.dates) if request.dates else []
        stocks = list(request.stocks) if request.stocks else []
        with _STATUS_LOCK:
            _LATEST_WEIGHTS.clear()
            _LATEST_WEIGHTS.update({"dates": dates, "stocks": stocks, "data": weights})
            payload = None
            if _LATEST_RETURNS:
                payload = {"weights": _LATEST_WEIGHTS.copy(), "returns": _LATEST_RETURNS.copy()}
        if payload:
            backtester = BacktesterCore(self.alpha_host, self.alpha_port)
            def run_backtest():
                backtester.backtest(payload)
                logger.info("[Backtester] Backtest processing completed")
            threading.Thread(target=run_backtest, daemon=True).start()
        return pb2.SubmitWeightsResponse(ack=pb2.Ack(ok=True, message="Weights received"))

    def SubmitReturns(self, request: pb2.SubmitReturnsRequest, context):
        logger.info("[Backtester] Received SubmitReturns request")
        returns = [[float(v) for v in row.values] for row in request.returns.rows]
        dates = list(request.dates) if request.dates else []
        stocks = list(request.stocks) if request.stocks else []
        with _STATUS_LOCK:
            _LATEST_RETURNS.clear()
            _LATEST_RETURNS.update({"dates": dates, "stocks": stocks, "data": returns})
            payload = None
            if _LATEST_WEIGHTS:
                payload = {"weights": _LATEST_WEIGHTS.copy(), "returns": _LATEST_RETURNS.copy()}
        if payload:
            backtester = BacktesterCore(self.alpha_host, self.alpha_port)
            def run_backtest():
                backtester.backtest(payload)
                logger.info("[Backtester] Backtest processing completed")
            threading.Thread(target=run_backtest, daemon=True).start()
        return pb2.SubmitReturnsResponse(ack=pb2.Ack(ok=True, message="Returns received"))

    def GetStatus(self, request: pb2.BacktestStatusRequest, context):
        with _STATUS_LOCK:
            done = bool(_LATEST_STATUS.get("done", False))
            summary_json = str(_LATEST_STATUS.get("summary_json", ""))
        return pb2.BacktestStatusResponse(done=done, summary_json=summary_json)


def serve() -> None:
    port = int(os.getenv('BACKTESTER_PORT', '50052'))
    max_msg_mb = int(os.getenv('GRPC_MAX_MESSAGE_MB', '64'))
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=8),
        options=[
            ('grpc.max_send_message_length', max_msg_mb * 1024 * 1024),
            ('grpc.max_receive_message_length', max_msg_mb * 1024 * 1024),
        ],
    )
    pb2_grpc.add_BacktesterServiceServicer_to_server(BacktesterService(), server)
    server.add_insecure_port(f'[::]:{port}')
    logger.info(f"Backtester gRPC server listening on {port}")
    server.start()
    server.wait_for_termination()


def main():
    serve()


if __name__ == "__main__":
    main()


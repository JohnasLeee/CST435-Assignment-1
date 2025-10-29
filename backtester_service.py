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
import requests
from typing import Dict, Any, Optional
from flask import Flask, request, jsonify

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)


class BacktesterCore:
    """Core backtesting computation logic"""
    
    def __init__(self, alpha_host='alpha', alpha_port=8081):
        self.alpha_host = alpha_host
        self.alpha_port = alpha_port
    
    def fetch_returns_matrix(self, max_retries=3) -> Optional[pd.DataFrame]:
        """Fetch returns matrix from Alpha Service"""
        for attempt in range(max_retries):
            try:
                url = f"http://{self.alpha_host}:{self.alpha_port}/get_returns"
                logger.info(f"[Backtester] Fetching returns from Alpha Service (attempt {attempt+1}/{max_retries})...")
                response = requests.get(url, timeout=120)
                response.raise_for_status()
                
                data = response.json()
                logger.info(f"[Backtester] Retrieved returns data with {len(data.get('dates', []))} dates and {len(data.get('stocks', []))} stocks")
                
                # Convert to DataFrame
                df = pd.DataFrame(
                    data['data'],
                    index=pd.to_datetime(data['dates']),
                    columns=data['stocks']
                )
                
                logger.info(f"[Backtester] Returns matrix shape: {df.shape}")
                return df
                
            except Exception as e:
                logger.warning(f"[Backtester] Error fetching returns (attempt {attempt+1}): {e}")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(2)
                else:
                    logger.error(f"[Backtester] Failed to fetch returns after {max_retries} attempts")
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
        weights_aligned = weights_aligned.shift(1)

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
    
    def plot_pnl_chart(self, cumulative_pnl: pd.Series, output_path: str = "pnl_chart.png"):
        """Plot cumulative PnL chart"""
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
    
    def backtest(self, weights_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Main backtesting method"""
        if not weights_data:
            logger.error("[Backtester] No weights data provided")
            return None
            
        try:
            logger.info("[Backtester] ===== STARTING BACKTEST PROCESSING =====")
            
            # Step 1: Parse weights data
            logger.info("[Backtester] Step 1/8: Parsing weights data...")
            weights_df = self._parse_weights_data(weights_data)
            if weights_df is None:
                logger.error("[Backtester] Failed to parse weights data")
                return None
            logger.info(f"[Backtester] ✓ Parsed {weights_df.shape[0]} days, {weights_df.shape[1]} stocks")
            
            # Step 2: Fetch returns
            logger.info("[Backtester] Step 2/8: Fetching returns from Alpha Service...")
            returns_df = self.fetch_returns_matrix()
            if returns_df is None:
                logger.error("[Backtester] Failed to fetch returns")
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
            
            logger.info("[Backtester] Step 8/8: Sending results to Master...")
            # Step 9: Send results to master
            self._send_results_to_master(result)
            
            logger.info("[Backtester] ===== BACKTEST COMPLETED SUCCESSFULLY =====")
            
            return result
            
        except Exception as e:
            logger.error(f"[Backtester] Backtest error: {e}")
            return None
    
    def _send_results_to_master(self, results: Dict[str, Any]):
        """Send backtest results to Master"""
        try:
            master_host = os.getenv('MASTER_HOST', 'master')
            master_port = int(os.getenv('MASTER_PORT', '8083'))
            
            url = f"http://{master_host}:{master_port}/results"
            logger.info(f"[Backtester] Sending results to Master at {master_host}:{master_port}")
            
            import requests
            response = requests.post(url, json=results, timeout=30)
            response.raise_for_status()
            
            logger.info("[Backtester] Results successfully sent to Master")
            
        except Exception as e:
            logger.error(f"[Backtester] Error sending results to Master: {e}")
    
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
            
            # Create DataFrame
            df = pd.DataFrame(
                data,
                index=pd.to_datetime(dates),
                columns=stocks
            )
            
            logger.info(f"[Backtester] Weights DataFrame shape: {df.shape}")
            return df
            
        except Exception as e:
            logger.error(f"[Backtester] Error parsing weights: {e}")
            return None


@app.route('/backtest', methods=['POST'])
def backtest():
    """Receive normalized weights from Normalizer and perform backtest"""
    import threading
    
    try:
        # Get weights from request body (sent by Normalizer)
        weights_data = request.get_json()
        
        if not weights_data:
            return jsonify({"error": "No weights data provided"}), 400
        
        logger.info("[Backtester] Received backtest request with weights data")
        
        # Acknowledge receipt to Normalizer immediately
        acknowledgment = {"status": "received", "message": "Backtest started"}
        response_data = jsonify(acknowledgment)
        
        # Process backtest in background thread
        alpha_host = os.getenv('ALPHA_HOST', 'alpha')
        alpha_port = int(os.getenv('ALPHA_PORT', '8081'))
        backtester = BacktesterCore(alpha_host, alpha_port)
        
        # Start backtest in a separate thread to avoid blocking
        def run_backtest():
            result = backtester.backtest(weights_data)
            logger.info("[Backtester] Backtest processing completed")
        
        thread = threading.Thread(target=run_backtest)
        thread.daemon = True
        thread.start()
        
        # Return acknowledgment immediately
        return response_data, 200
            
    except Exception as e:
        logger.error(f"[Backtester] Error in backtest endpoint: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "backtester"}), 200


def main():
    """Main entry point"""
    port = int(os.getenv('BACKTESTER_PORT', '8082'))
    host = os.getenv('BACKTESTER_HOST', '0.0.0.0')
    
    logger.info("=== Backtester Service Started ===")
    logger.info(f"Listening on {host}:{port}")
    
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()


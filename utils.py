import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import yfinance as yf
import requests
from io import StringIO
import os
import pickle
from pathlib import Path

# Cache configuration
CACHE_DIR = Path("./data_cache")
CACHE_FILE = CACHE_DIR / "sp500_data.pkl"

# Get the list of S&P 500 tickers from Wikipedia
def get_SP500(use_cache: bool = True) -> pd.DataFrame:
    # Try loading from cache first
    if use_cache and CACHE_FILE.exists():
        try:
            print(f"[DEBUG] Loading cached S&P 500 data from {CACHE_FILE}")
            with open(CACHE_FILE, 'rb') as f:
                data = pickle.load(f)
            print(f"[DEBUG] Cache loaded! Shape: {data.shape}, Range: {data.index[0]} to {data.index[-1]}")
            return data
        except Exception as e:
            print(f"[DEBUG] Cache load failed: {e}. Fetching fresh data...")
    else:
        print("[DEBUG] Cache disabled or not found. Fetching fresh data...")
    # Add headers to avoid 403 Forbidden error
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    # Use requests to get the page content first (more reliable)
    print("Fetching S&P 500 company list from Wikipedia...")
    response = requests.get('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies', 
                        headers=headers)
    
    response.raise_for_status()
    tables = pd.read_html(StringIO(response.text))
    
    # Find table with "Symbol" column
    sp500 = None
    for tbl in tables:
        if 'Symbol' in tbl.columns:
            sp500 = tbl
            break
    
    if sp500 is None:
        raise RuntimeError("Could not locate S&P 500 table on Wikipedia")
    
    tickers = sp500['Symbol'].astype(str).tolist()
    print(f"Number of tickers: {len(tickers)}")

    # Convert dot notation (e.g., BRK.B) to hyphen for yfinance compatibility
    tickers = [t.replace('.', '-') for t in tickers]

    # Download data with error handling
    print("Downloading stock data...")
    print(f"Date range: 2013-01-01 to 2023-12-31")
    print(f"Total tickers to download: {len(tickers)}")

    try:
        data = yf.download(
            tickers=tickers,
            start="2013-01-01",
            end="2023-12-31",
            interval="1d",
            group_by='ticker',  # separate each symbol in columns
            threads=True,       # multi-threaded for speed
            progress=True,      # show progress bar
            auto_adjust=True    # explicitly set to avoid warning
        )
        
        # Check which tickers were successfully downloaded
        if isinstance(data.columns, pd.MultiIndex):
            successful_tickers = data.columns.get_level_values(0).unique().tolist()
        else:
            # If single ticker, data.columns might be different
            successful_tickers = [tickers[0]] if len(tickers) == 1 else []
        
        print(f"\nSuccessfully downloaded data for {len(successful_tickers)} tickers")
        print(f"Data shape: {data.shape}")
        
        # Show basic info about the data
        print(f"\nData columns (first 10): {list(data.columns)[:10]}")
        print(f"Date range: {data.index[0]} to {data.index[-1]}")
        
        # Save to cache
        if use_cache:
            try:
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                with open(CACHE_FILE, 'wb') as f:
                    pickle.dump(data, f)
                print(f"[DEBUG] Data cached to {CACHE_FILE}")
            except Exception as e:
                print(f"[DEBUG] Cache save failed: {e}")
        
        return data
        
    except Exception as e:
        print(f"Error during download: {e}")
        print("Some tickers may not have data for the specified date range.")
        print("This is normal for newer companies that weren't public during 2013-2023.")
        return None

def get_negative_rank_returns_only(data: pd.DataFrame) -> pd.DataFrame:
    """
    Compute and return a new DataFrame containing only the -rank(returns) columns with datetime index.
    
    Parameters:
    data: Raw DataFrame with MultiIndex columns (ticker, metric)
    
    Returns:
    DataFrame with only -rank(returns) columns and datetime index
    """
    if data is None:
        print("No data provided")
        return None
    
    # Get all unique tickers
    if isinstance(data.columns, pd.MultiIndex):
        tickers = data.columns.get_level_values(0).unique()
    else:
        print("Data does not have MultiIndex columns")
        return None
    
    print(f"Computing -rank(returns) for {len(tickers)} tickers...")
    
    # Collect all computed -rank(returns) columns
    rank_columns = []
    
    for ticker in tickers:
        try:
            # Get close prices for this ticker
            close_col = (ticker, 'Close')
            if close_col in data.columns:
                close_prices = data[close_col]
                
                # Calculate daily returns
                returns = close_prices.pct_change(fill_method=None)
                
                # Calculate rank of returns (ascending: lowest return gets rank 1)
                # Using method='min' to handle ties consistently
                rank_returns = returns.rank(method='min', ascending=True)
                
                # Normalize rank to be between 0 and 1
                # (rank - 1) / (n - 1) where n is the number of non-null values
                n_valid = returns.notna().sum()
                if n_valid > 1:
                    normalized_rank = (rank_returns - 1) / (n_valid - 1)
                else:
                    normalized_rank = rank_returns
                
                # Create negative rank (so highest returns get most negative values)
                negative_rank = -normalized_rank
                
                # Store the computed column
                rank_columns.append(pd.DataFrame({ticker: negative_rank}))
            else:
                print(f"Close prices not found for {ticker}")
                
        except Exception as e:
            print(f"Error processing {ticker}: {e}")
    
    # Create new DataFrame with only -rank(returns) columns
    if rank_columns:
        result_df = pd.concat(rank_columns, axis=1)
        print(f"Created DataFrame with {result_df.shape[1]} -rank(returns) columns")
        print(f"Date range: {result_df.index[0]} to {result_df.index[-1]}")
        return result_df
    else:
        print("No -rank(returns) columns computed")
        return None
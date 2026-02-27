"""
Charles Schwab API Client for real portfolio synchronization.

This module provides the interface to Schwab's API for fetching
real account positions and balances. Requires API credentials.

Note: Schwab's API requires OAuth2 authentication. You'll need to:
1. Register an app at developer.schwab.com
2. Complete the OAuth flow to get access/refresh tokens
3. Store tokens in config/schwab_token.json
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

import pandas as pd
import requests
from loguru import logger

from src.utils import load_credentials, get_config_dir, save_parquet, load_parquet


class SchwabClient:
    """
    Client for Charles Schwab API integration.

    Handles OAuth2 token management and portfolio data retrieval.
    Falls back gracefully when credentials are not configured.
    """

    BASE_URL = "https://api.schwabapi.com"
    AUTH_URL = "https://api.schwabapi.com/v1/oauth/authorize"
    TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"

    def __init__(self):
        self._credentials = None
        self._token = None
        self._session = requests.Session()
        self._initialized = False

        try:
            creds = load_credentials()
            self._credentials = creds.get("schwab", {})
            if self._credentials.get("app_key"):
                self._load_token()
                self._initialized = True
                logger.info("Schwab client initialized with credentials")
            else:
                logger.info("Schwab credentials not configured - using paper trading only")
        except Exception as e:
            logger.info(f"Schwab client not configured: {e}")

    @property
    def is_configured(self) -> bool:
        return self._initialized and self._token is not None

    # ------------------------------------------------------------------
    # Token Management
    # ------------------------------------------------------------------
    def _load_token(self):
        """Load OAuth token from file."""
        token_file = self._credentials.get("token_file", "config/schwab_token.json")
        token_path = get_config_dir().parent / token_file
        if token_path.exists():
            with open(token_path) as f:
                self._token = json.load(f)
            logger.debug("Loaded Schwab token from file")
        else:
            logger.warning(f"Token file not found: {token_path}")

    def _save_token(self):
        """Save OAuth token to file."""
        if self._token:
            token_file = self._credentials.get("token_file", "config/schwab_token.json")
            token_path = get_config_dir().parent / token_file
            with open(token_path, "w") as f:
                json.dump(self._token, f, indent=2)

    def _refresh_token(self) -> bool:
        """Refresh the OAuth access token."""
        if not self._token or not self._token.get("refresh_token"):
            logger.error("No refresh token available")
            return False

        try:
            resp = self._session.post(
                self.TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self._token["refresh_token"],
                    "client_id": self._credentials["app_key"],
                    "client_secret": self._credentials["app_secret"],
                },
            )
            resp.raise_for_status()
            self._token.update(resp.json())
            self._save_token()
            logger.info("Schwab token refreshed successfully")
            return True
        except Exception as e:
            logger.error(f"Token refresh failed: {e}")
            return False

    def _get_headers(self) -> Dict[str, str]:
        """Get authorization headers."""
        if self._token:
            return {
                "Authorization": f"Bearer {self._token.get('access_token', '')}",
                "Accept": "application/json",
            }
        return {}

    def _api_request(self, endpoint: str, method: str = "GET", **kwargs) -> Optional[Dict]:
        """Make an authenticated API request with auto token refresh."""
        if not self.is_configured:
            return None

        url = f"{self.BASE_URL}{endpoint}"

        for attempt in range(2):
            try:
                resp = self._session.request(
                    method, url, headers=self._get_headers(), **kwargs
                )
                if resp.status_code == 401 and attempt == 0:
                    if self._refresh_token():
                        continue
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                logger.error(f"API request failed ({endpoint}): {e}")
                if attempt == 0:
                    self._refresh_token()

        return None

    # ------------------------------------------------------------------
    # Portfolio Data
    # ------------------------------------------------------------------
    def get_account_positions(self) -> Optional[pd.DataFrame]:
        """
        Fetch current account positions from Schwab.
        Returns DataFrame with: ticker, quantity, avg_cost, market_value,
        unrealized_pnl, unrealized_pnl_pct.
        """
        if not self.is_configured:
            logger.info("Schwab not configured, skipping position fetch")
            return None

        account = self._credentials.get("account_number", "")
        data = self._api_request(f"/trader/v1/accounts/{account}/positions")

        if not data:
            return None

        positions = []
        for pos in data.get("securitiesAccount", {}).get("positions", []):
            instrument = pos.get("instrument", {})
            positions.append({
                "ticker": instrument.get("symbol", ""),
                "asset_type": instrument.get("assetType", ""),
                "quantity": pos.get("longQuantity", 0) - pos.get("shortQuantity", 0),
                "avg_cost": pos.get("averagePrice", 0),
                "market_value": pos.get("marketValue", 0),
                "current_price": pos.get("currentDayProfitLoss", 0),
                "unrealized_pnl": pos.get("longOpenProfitLoss", 0),
            })

        df = pd.DataFrame(positions)
        if not df.empty:
            df["unrealized_pnl_pct"] = df["unrealized_pnl"] / (
                df["avg_cost"] * df["quantity"]
            ).replace(0, float("nan"))
            logger.info(f"Fetched {len(df)} positions from Schwab")

        return df

    def get_account_balance(self) -> Optional[Dict[str, float]]:
        """Fetch account balance information."""
        if not self.is_configured:
            return None

        account = self._credentials.get("account_number", "")
        data = self._api_request(f"/trader/v1/accounts/{account}")

        if not data:
            return None

        balances = data.get("securitiesAccount", {}).get("currentBalances", {})
        return {
            "total_value": balances.get("liquidationValue", 0),
            "cash": balances.get("cashBalance", 0),
            "buying_power": balances.get("buyingPower", 0),
            "equity": balances.get("equity", 0),
        }

    def sync_real_portfolio(self):
        """
        Sync real portfolio from Schwab and store in Parquet.
        """
        positions = self.get_account_positions()
        if positions is not None and not positions.empty:
            positions["sync_date"] = datetime.now().isoformat()
            positions["source"] = "schwab"
            save_parquet(positions, "portfolios", "real_portfolio")
            logger.info("Real portfolio synced from Schwab")

        balance = self.get_account_balance()
        if balance:
            bal_df = pd.DataFrame([{
                "sync_date": datetime.now().isoformat(),
                "source": "schwab",
                **balance,
            }])
            save_parquet(bal_df, "portfolios", "real_balance")
            logger.info("Account balance synced from Schwab")

    def load_real_portfolio(self) -> Optional[pd.DataFrame]:
        """Load the last synced real portfolio."""
        return load_parquet("portfolios", "real_portfolio")

"""Minimal Tradovate REST API client: auth, accounts, contracts, orders, positions.

Defaults to the demo (paper trading) environment - TRADOVATE_ENV must be explicitly
set to "live" in trading/.env to touch real money. See docs/CONNECT_TRADOVATE.md.
"""
import time

import requests

from config.settings import (
    TRADOVATE_APP_ID,
    TRADOVATE_APP_VERSION,
    TRADOVATE_CID,
    TRADOVATE_DEVICE_ID,
    TRADOVATE_ENV,
    TRADOVATE_PASSWORD,
    TRADOVATE_SEC,
    TRADOVATE_USERNAME,
    require_credentials,
    rest_base_url,
)


class TradovateError(RuntimeError):
    pass


class TradovateClient:
    def __init__(self):
        require_credentials()
        self.base_url = rest_base_url()
        self.access_token = None
        self.md_access_token = None
        self.expiration_time = 0
        self._session = requests.Session()

    def authenticate(self):
        body = {
            "name": TRADOVATE_USERNAME,
            "password": TRADOVATE_PASSWORD,
            "appId": TRADOVATE_APP_ID,
            "appVersion": TRADOVATE_APP_VERSION,
            "cid": TRADOVATE_CID,
            "sec": TRADOVATE_SEC,
            "deviceId": TRADOVATE_DEVICE_ID,
        }
        resp = self._session.post(f"{self.base_url}/auth/accessTokenRequest", json=body, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if "errorText" in data:
            raise TradovateError(f"Tradovate auth failed: {data['errorText']}")
        self.access_token = data["accessToken"]
        self.md_access_token = data.get("mdAccessToken")
        # expirationTime is an ISO string; keep it simple and just re-auth every ~55 min
        self.expiration_time = time.time() + 55 * 60
        return data

    def _headers(self):
        if not self.access_token or time.time() >= self.expiration_time:
            self.authenticate()
        return {"Authorization": f"Bearer {self.access_token}"}

    def _get(self, path: str, params: dict | None = None):
        resp = self._session.get(f"{self.base_url}{path}", headers=self._headers(), params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, body: dict):
        resp = self._session.post(f"{self.base_url}{path}", headers=self._headers(), json=body, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and data.get("failureReason"):
            raise TradovateError(f"Tradovate request failed: {data['failureReason']} - {data.get('failureText')}")
        return data

    # -- accounts --------------------------------------------------------
    def list_accounts(self):
        return self._get("/account/list")

    # -- contracts ---------------------------------------------------------
    def find_contract(self, symbol: str):
        """symbol e.g. 'MESU6' (micro E-mini S&P, Sept 2026). Use /contract/suggest
        with a root like 'MES' if you need to discover the current front-month symbol."""
        return self._get("/contract/find", params={"name": symbol})

    def suggest_contracts(self, text: str, limit: int = 10):
        return self._get("/contract/suggest", params={"t": text, "l": limit})

    # -- orders ------------------------------------------------------------
    def place_order(self, account_id: int, account_spec: str, symbol: str, action: str,
                     order_qty: int, order_type: str = "Market", price: float | None = None,
                     is_automated: bool = True):
        """action: 'Buy' or 'Sell'. order_type: Market, Limit, Stop, StopLimit, etc."""
        body = {
            "accountSpec": account_spec,
            "accountId": account_id,
            "action": action,
            "symbol": symbol,
            "orderQty": order_qty,
            "orderType": order_type,
            "isAutomated": is_automated,
        }
        if price is not None:
            body["price"] = price
        return self._post("/order/placeOrder", body)

    def cancel_order(self, order_id: int):
        return self._post("/order/cancelOrder", {"orderId": order_id})

    def list_orders(self):
        return self._get("/order/list")

    # -- positions -----------------------------------------------------------
    def list_positions(self):
        return self._get("/position/list")

    def cash_balance(self, account_id: int):
        return self._get("/cashBalance/getCashBalanceSnapshot", params={"accountId": account_id})

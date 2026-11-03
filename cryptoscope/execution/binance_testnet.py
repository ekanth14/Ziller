"""Binance Spot Testnet Client.

Implements official REST API interactions against Binance Spot Testnet (https://testnet.binance.vision).
Adheres strictly to zero-leakage credential policies and fail-closed safety semantics.
"""

import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger("cryptoscope.execution.binance_testnet")


class BinanceClientError(Exception):
    """Base exception for Binance Testnet errors."""
    def __init__(self, message: str, code: Optional[int] = None, http_status: Optional[int] = None):
        super().__init__(message)
        self.code = code
        self.http_status = http_status


class BinanceAuthError(BinanceClientError):
    """Raised on authentication failure (-2014 invalid format, -2015 invalid key/permission)."""
    pass


class BinanceOrderFilterError(BinanceClientError):
    """Raised when an order violates LOT_SIZE, PRICE_FILTER, or MIN_NOTIONAL (-1013)."""
    pass


class BinanceInsufficientBalanceError(BinanceClientError):
    """Raised when account balance is insufficient for trade (-2010)."""
    pass


class BinanceTestnetClient:
    """Official Binance Spot Testnet REST client for order execution and safety controls."""

    DEFAULT_BASE_URL = "https://testnet.binance.vision"

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 5.0,
    ):
        self.api_key = (api_key or os.getenv("BINANCE_TESTNET_API_KEY", "")).strip().strip("<>\"' \t\r\n")
        self.api_secret = (api_secret or os.getenv("BINANCE_TESTNET_API_SECRET", "")).strip().strip("<>\"' \t\r\n")
        self.base_url = (base_url or os.getenv("BINANCE_TESTNET_BASE_URL", self.DEFAULT_BASE_URL)).rstrip("/")
        self.timeout = timeout

    @property
    def masked_api_key(self) -> str:
        if not self.api_key:
            return "<UNSET>"
        if len(self.api_key) <= 8:
            return "***"
        return f"{self.api_key[:4]}...{self.api_key[-4:]}"

    def __repr__(self) -> str:
        return f"BinanceTestnetClient(base_url={self.base_url!r}, api_key={self.masked_api_key})"

    def _sign_query(self, params: Dict[str, Any]) -> str:
        """Create HMAC-SHA256 signature for parameters."""
        query_string = urllib.parse.urlencode(params)
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"{query_string}&signature={signature}"

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        signed: bool = False,
    ) -> Dict[str, Any]:
        """Execute HTTP request against Binance Testnet."""
        params = params.copy() if params else {}

        if signed:
            if not self.api_key or not self.api_secret:
                raise BinanceAuthError("Binance API key and secret must be configured for signed endpoints.")
            # Automatically add timestamp and recvWindow
            server_time = self.get_server_time()
            params.setdefault("timestamp", server_time)
            params.setdefault("recvWindow", 5000)
            encoded_query = self._sign_query(params)
        else:
            encoded_query = urllib.parse.urlencode(params)

        url = f"{self.base_url}{path}"
        data = None
        headers = {
            "User-Agent": "ZILLERS-Orchestrator/1.0",
            "Accept": "application/json",
        }

        if self.api_key:
            headers["X-MBX-APIKEY"] = self.api_key

        if method.upper() in {"GET", "DELETE"}:
            if encoded_query:
                url = f"{url}?{encoded_query}"
        else:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            data = encoded_query.encode("utf-8")

        req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            err_code = None
            err_msg = err_body
            try:
                parsed = json.loads(err_body)
                err_code = parsed.get("code")
                err_msg = parsed.get("msg", err_body)
            except Exception:
                pass

            logger.error(
                "Binance Testnet HTTP %d %s %s -> Code: %s, Msg: %s",
                exc.code, method, path, err_code, err_msg
            )

            if exc.code == 401 or err_code in (-2014, -2015):
                raise BinanceAuthError(f"Authentication failed: {err_msg} (code={err_code})", code=err_code, http_status=exc.code)
            elif err_code == -1013:
                raise BinanceOrderFilterError(f"Order filter rejected: {err_msg} (code={err_code})", code=err_code, http_status=exc.code)
            elif err_code == -2010:
                raise BinanceInsufficientBalanceError(f"Insufficient funds: {err_msg} (code={err_code})", code=err_code, http_status=exc.code)
            else:
                raise BinanceClientError(f"Binance API error: {err_msg} (code={err_code})", code=err_code, http_status=exc.code)
        except urllib.error.URLError as exc:
            logger.error("Binance Testnet network failure: %s", exc)
            raise BinanceClientError(f"Network error connecting to Binance: {exc}")

    def ping(self) -> bool:
        """Test connectivity to Binance Spot Testnet."""
        try:
            self._request("GET", "/api/v3/ping")
            return True
        except Exception as exc:
            logger.warning("Binance testnet ping failed: %s", exc)
            return False

    def get_server_time(self) -> int:
        """Fetch current Binance server timestamp in milliseconds."""
        res = self._request("GET", "/api/v3/time")
        return int(res.get("serverTime", int(time.time() * 1000)))

    def get_account(self) -> Dict[str, Any]:
        """Fetch testnet account info and balances (requires valid signed credentials)."""
        return self._request("GET", "/api/v3/account", signed=True)

    def get_symbol_info(self, symbol: str) -> Dict[str, Any]:
        """Fetch exchange filters (LOT_SIZE, PRICE_FILTER, MIN_NOTIONAL) for a symbol."""
        res = self._request("GET", "/api/v3/exchangeInfo", params={"symbol": symbol.upper()})
        symbols = res.get("symbols", [])
        if not symbols:
            raise BinanceClientError(f"Symbol {symbol} not found on Binance Testnet")
        return symbols[0]

    def get_ticker_price(self, symbol: str) -> float:
        """Fetch current ticker price for a symbol."""
        res = self._request("GET", "/api/v3/ticker/price", params={"symbol": symbol.upper()})
        return float(res["price"])

    def create_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        time_in_force: str = "GTC",
        client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Place an order (MARKET, LIMIT, STOP_LOSS_LIMIT) on Binance Spot Testnet."""
        params: Dict[str, Any] = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "type": order_type.upper(),
            "quantity": f"{quantity:.6f}".rstrip("0").rstrip("."),
        }

        if client_order_id:
            params["newClientOrderId"] = client_order_id

        if order_type.upper() == "LIMIT":
            if price is None:
                raise ValueError("Price is required for LIMIT orders")
            params["price"] = f"{price:.2f}"
            params["timeInForce"] = time_in_force

        elif order_type.upper() in {"STOP_LOSS_LIMIT", "STOP_LOSS"}:
            if stop_price is None:
                raise ValueError("stop_price is required for STOP_LOSS orders")
            params["stopPrice"] = f"{stop_price:.2f}"
            if price is not None:
                params["price"] = f"{price:.2f}"
            else:
                params["price"] = f"{stop_price:.2f}"
            params["timeInForce"] = time_in_force

        return self._request("POST", "/api/v3/order", params=params, signed=True)

    def get_order(
        self,
        symbol: str,
        order_id: Optional[int] = None,
        client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Query execution status of an order."""
        params: Dict[str, Any] = {"symbol": symbol.upper()}
        if order_id is not None:
            params["orderId"] = order_id
        elif client_order_id is not None:
            params["origClientOrderId"] = client_order_id
        else:
            raise ValueError("Either order_id or client_order_id must be provided")

        return self._request("GET", "/api/v3/order", params=params, signed=True)

    def cancel_order(
        self,
        symbol: str,
        order_id: Optional[int] = None,
        client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Cancel an active order on Binance Spot Testnet."""
        params: Dict[str, Any] = {"symbol": symbol.upper()}
        if order_id is not None:
            params["orderId"] = order_id
        elif client_order_id is not None:
            params["origClientOrderId"] = client_order_id
        else:
            raise ValueError("Either order_id or client_order_id must be provided")

        return self._request("DELETE", "/api/v3/order", params=params, signed=True)

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch all currently open orders."""
        params: Dict[str, Any] = {}
        if symbol:
            params["symbol"] = symbol.upper()
        res = self._request("GET", "/api/v3/openOrders", params=params, signed=True)
        return res if isinstance(res, list) else []

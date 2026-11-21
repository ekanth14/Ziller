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
from cryptoscope.execution.accounting import wire_amount

logger = logging.getLogger("cryptoscope.execution.binance_testnet")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


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


class BinanceRateLimitError(BinanceClientError):
    """A cooldown must elapse; order POSTs are never retried automatically."""
    pass


class BinanceClockSkewError(BinanceClientError):
    """Timestamp rejected by the exchange (-1021). The request was not processed."""
    pass


class BinanceNetworkError(BinanceClientError):
    """Transport failure (DNS, connect, read timeout). Order state after a POST is UNKNOWN."""
    pass


class BinanceTestnetClient:
    """Official Binance Spot Testnet REST client for order execution and safety controls."""

    DEFAULT_BASE_URL = "https://testnet.binance.vision"
    TIME_RESYNC_SECONDS = 30.0
    # During a rate-limit cooldown, safety-critical calls (cancel, exits/stops, order status)
    # may probe the exchange at most this often instead of being blocked outright.
    CRITICAL_PROBE_INTERVAL = 5.0

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 5.0,
    ):
        self.api_key = (api_key or os.getenv("BINANCE_TESTNET_API_KEY", "")).strip().strip("<>\"' \t\r\n")
        self.api_secret = (api_secret or os.getenv("BINANCE_TESTNET_API_SECRET", "")).strip().strip("<>\"' \t\r\n")
        self.base_url = (base_url or os.getenv('BINANCE_TESTNET_BASE_URL') or self.DEFAULT_BASE_URL).rstrip('/')
        from cryptoscope.security.config import validate_testnet_url
        self.base_url = validate_testnet_url(self.base_url)
        self.timeout = timeout
        self.retry_after_monotonic=0.0
        self._time_offset_ms=0
        self._time_synced_monotonic=-1e9
        self._last_critical_probe=-1e9
        self._opener=urllib.request.build_opener(_NoRedirect())

    @property
    def masked_api_key(self) -> str:
        if not self.api_key:
            return "<UNSET>"
        return '<CONFIGURED>'

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

    def _signed_timestamp(self) -> int:
        """Server-aligned timestamp from a cached clock offset (resynced at most every 30s).

        Avoids one extra /time request per signed call and never fails the caller: if a
        resync is impossible (network error, rate-limit cooldown) the last known offset is used.
        """
        now = time.monotonic()
        if now - self._time_synced_monotonic > self.TIME_RESYNC_SECONDS and now >= self.retry_after_monotonic:
            try:
                server = self.get_server_time()
                self._time_offset_ms = server - int(time.time() * 1000)
                self._time_synced_monotonic = now
            except BinanceClientError:
                logger.warning("Binance time resync failed; using last known clock offset")
        return int(time.time() * 1000) + self._time_offset_ms

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        signed: bool = False,
        critical: bool = False,
    ) -> Dict[str, Any]:
        """Execute an HTTP request with bounded, safe retries.

        - GET requests retry transport errors up to twice (short backoff).
        - A -1021 timestamp rejection (request never processed) is retried once after a clock resync.
        - Rate-limit errors and order-changing requests are never retried automatically.
        """
        net_retries = 2 if method.upper() == "GET" else 0
        attempt = 0
        skew_retried = False
        while True:
            try:
                return self._request_once(method, path, params, signed, critical)
            except BinanceClockSkewError:
                if skew_retried or not signed:
                    raise
                skew_retried = True
                self._time_synced_monotonic = -1e9  # force clock resync on the retry
            except BinanceNetworkError:
                if attempt >= net_retries:
                    raise
                attempt += 1
                time.sleep(0.2 * attempt)

    def _request_once(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        signed: bool = False,
        critical: bool = False,
    ) -> Dict[str, Any]:
        """Execute a single HTTP request against Binance Testnet."""
        params = params.copy() if params else {}
        now = time.monotonic()
        if now < self.retry_after_monotonic:
            if not critical or now - self._last_critical_probe < self.CRITICAL_PROBE_INTERVAL:
                raise BinanceRateLimitError('Exchange cooldown active',http_status=429)
            self._last_critical_probe = now

        if signed:
            if not self.api_key or not self.api_secret:
                raise BinanceAuthError("Binance API key and secret must be configured for signed endpoints.")
            # Automatically add timestamp and recvWindow
            server_time = self._signed_timestamp()
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
            with self._opener.open(req, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            err_code = None
            try:
                parsed = json.loads(err_body)
                candidate = parsed.get('code')
                err_code = candidate if type(candidate) is int else None
            except Exception:
                pass

            logger.error(
                "Binance Testnet request rejected: HTTP %d, code %s",
                exc.code, err_code
            )

            if exc.code in {418,429}:
                try:delay=max(1.,min(86400.,float((exc.headers or {}).get('Retry-After','60'))))
                except (ValueError,TypeError):delay=60.
                self.retry_after_monotonic=time.monotonic()+delay
                raise BinanceRateLimitError('Exchange cooldown active',code=err_code,http_status=exc.code) from None
            if err_code == -1021:
                raise BinanceClockSkewError('Timestamp outside recvWindow', code=err_code, http_status=exc.code) from None
            if exc.code == 401 or err_code in (-2014, -2015):
                raise BinanceAuthError('Authentication failed', code=err_code, http_status=exc.code) from None
            elif err_code == -1013:
                raise BinanceOrderFilterError('Order filter rejected', code=err_code, http_status=exc.code) from None
            elif err_code == -2010:
                raise BinanceInsufficientBalanceError('Insufficient funds', code=err_code, http_status=exc.code) from None
            else:
                raise BinanceClientError('Binance request failed', code=err_code, http_status=exc.code) from None
        except OSError:
            # URLError, socket timeouts and connection resets (HTTPError is handled above)
            logger.error('Binance Testnet network request failed')
            raise BinanceNetworkError('Network error connecting to Binance') from None

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
        quote_order_qty: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Place an order (MARKET, LIMIT, STOP_LOSS_LIMIT) on Binance Spot Testnet."""
        params: Dict[str, Any] = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "type": order_type.upper(),
            "quantity": wire_amount(quantity),
            "newOrderRespType": "FULL",
        }

        if client_order_id:
            params["newClientOrderId"] = client_order_id
        if quote_order_qty is not None:
            if side.upper()!='BUY' or order_type.upper()!='MARKET':raise ValueError('Quote budget is supported only for a Spot market buy')
            params.pop('quantity');params['quoteOrderQty']=wire_amount(quote_order_qty)

        if order_type.upper() in {"LIMIT","LIMIT_MAKER"}:
            if price is None:
                raise ValueError("Price is required for LIMIT orders")
            params["price"] = wire_amount(price)
            if order_type.upper()=='LIMIT':params["timeInForce"] = time_in_force

        elif order_type.upper() in {"STOP_LOSS_LIMIT", "STOP_LOSS"}:
            if stop_price is None:
                raise ValueError("stop_price is required for STOP_LOSS orders")
            params["stopPrice"] = wire_amount(stop_price)
            if order_type.upper() == 'STOP_LOSS_LIMIT':
                if price is None:raise ValueError('Limit price required for stop-limit order')
                params["price"] = wire_amount(price)
                params["timeInForce"] = time_in_force

        # Exits and protective stops must still reach the exchange during a rate-limit cooldown.
        critical = side.upper() == "SELL" or order_type.upper() in {"STOP_LOSS", "STOP_LOSS_LIMIT"}
        if critical:
            return self._request("POST", "/api/v3/order", params=params, signed=True, critical=True)
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

        return self._request("GET", "/api/v3/order", params=params, signed=True, critical=True)

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

        return self._request("DELETE", "/api/v3/order", params=params, signed=True, critical=True)

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch all currently open orders."""
        params: Dict[str, Any] = {}
        if symbol:
            params["symbol"] = symbol.upper()
        res = self._request("GET", "/api/v3/openOrders", params=params, signed=True)
        if not isinstance(res,list):raise BinanceClientError('Invalid exchange open-orders response')
        return res

    def get_my_trades(self,symbol,order_id):
        if not str(order_id).isdigit():raise BinanceClientError('Fill query requires an exact order identity')
        result=self._request('GET','/api/v3/myTrades',params=dict(symbol=symbol,orderId=order_id,limit=1000),signed=True,critical=True)
        if not isinstance(result,list):raise BinanceClientError('Invalid exchange fill response')
        return result

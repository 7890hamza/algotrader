from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal


def _read_str(name: str, default: str | None = None) -> str:
    value = os.getenv(name)
    if value is None:
        if default is None:
            raise ValueError(f"Missing required environment variable: {name}")
        return default
    return value


def _read_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be an integer") from exc


def _read_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be a float") from exc


def _read_optional_int(name: str) -> int | None:
    value = os.getenv(name)
    if value is None:
        return None
    if value in ("", "none", "None", "null", "NULL"):
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be an integer or empty") from exc


def _read_provider() -> Literal["ctrader", "mt5"]:
    value = _read_str("BROKER_PROVIDER", "ctrader").strip().lower()
    if value not in {"ctrader", "mt5"}:
        raise ValueError("BROKER_PROVIDER must be one of: ctrader, mt5")
    return value  # type: ignore[return-value]


def _read_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Environment variable {name} must be true or false")


@dataclass(frozen=True, slots=True)
class Mt5Settings:
    """MetaTrader 5 market-data settings. The MT5 adapter is read-only."""

    terminal_path: str | None
    require_demo: bool
    poll_interval_seconds: float
    server_utc_offset_minutes: int
    volume_source: Literal["real", "tick"]
    symbol_aliases: dict[str, str]
    history_settle_attempts: int

    @classmethod
    def from_env(cls) -> "Mt5Settings":
        volume = _read_str("MT5_VOLUME_SOURCE", "real").strip().lower()
        if volume not in {"real", "tick"}:
            raise ValueError("MT5_VOLUME_SOURCE must be one of: real, tick")
        poll = _read_float("MT5_POLL_INTERVAL_SECONDS", 0.25)
        if poll <= 0:
            raise ValueError("MT5_POLL_INTERVAL_SECONDS must be positive")
        return cls(
            terminal_path=(os.getenv("MT5_TERMINAL_PATH") or "").strip() or None,
            require_demo=_read_bool("MT5_REQUIRE_DEMO", True),
            poll_interval_seconds=poll,
            server_utc_offset_minutes=_read_int("MT5_SERVER_UTC_OFFSET_MINUTES", 0),
            volume_source=volume,  # type: ignore[arg-type]
            symbol_aliases=parse_symbol_aliases(_read_str("MT5_SYMBOLS", "ES=@EP")),
            history_settle_attempts=max(1, _read_int("MT5_HISTORY_SETTLE_ATTEMPTS", 6)),
        )


def parse_symbol_aliases(raw: str) -> dict[str, str]:
    """Parse ``ES=@EP,NQ=@ENQ`` into ``{"ES": "@EP", "NQ": "@ENQ"}``.

    The alias (left side) is the Market symbol AlgoTrader stores and uses in URLs
    and Redis stream names; the right side is the exact MT5 symbol name.
    """
    aliases: dict[str, str] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        alias, sep, mt5_name = part.partition("=")
        alias, mt5_name = alias.strip().upper(), mt5_name.strip()
        if not sep or not alias or not mt5_name:
            raise ValueError(f"MT5_SYMBOLS entry must look like ALIAS=MT5NAME, got: {part!r}")
        if not all(ch.isalnum() or ch in "._-" for ch in alias):
            raise ValueError(
                f"MT5_SYMBOLS alias may use letters, digits, '.', '_' or '-': {alias!r}"
            )
        aliases[alias] = mt5_name
    return aliases


@dataclass(frozen=True, slots=True)
class CtraderCredentials:
    client_id: str
    secret: str
    host_type: Literal["demo", "live"]
    access_token: str
    refresh_token: str
    token_url: str
    access_token_expires_in_seconds: int
    token_request_timeout_seconds: float

    @classmethod
    def from_env(cls) -> "CtraderCredentials":
        host_type = _read_str("CTRADER_HOST_TYPE").lower()
        if host_type not in {"demo", "live"}:
            raise ValueError("CTRADER_HOST_TYPE must be one of: demo, live")

        return cls(
            client_id=_read_str("CTRADER_CLIENT_ID"),
            secret=_read_str("CTRADER_SECRET"),
            host_type=host_type,  # type: ignore[arg-type]
            access_token=_read_str("CTRADER_ACCESS_TOKEN"),
            refresh_token=_read_str("CTRADER_REFRESH_TOKEN"),
            token_url=_read_str("CTRADER_TOKEN_URL", "https://openapi.ctrader.com/apps/token"),
            access_token_expires_in_seconds=_read_int(
                "CTRADER_ACCESS_TOKEN_EXPIRES_IN_SECONDS",
                2628000,
            ),
            token_request_timeout_seconds=_read_float(
                "CTRADER_TOKEN_REQUEST_TIMEOUT_SECONDS",
                10.0,
            ),
        )


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str = "broker-service"
    service_port: int = 8050
    redis_url: str = "redis://redis:6379/0"
    tick_queue_size: int = 1000
    tick_stream_maxlen: int | None = None
    candle_stream_maxlen: int | None = None
    broker_max_symbol_streams: int = 20
    broker_max_trendbar_streams: int = 10
    broker_token_redis_key: str = "broker:auth:ctrader:current"
    broker_token_refresh_early_seconds: int = 604800
    broker_token_refresh_retry_delay_seconds: int = 30
    broker_token_refresh_max_retries: int = 3
    log_level: str = "INFO"
    log_format: str = "pretty"
    ctrader_request_timeout_seconds: float = 20.0
    broker_provider: Literal["ctrader", "mt5"] = "ctrader"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            app_name=_read_str("BROKER_APP_NAME", "broker-service"),
            service_port=_read_int("BROKER_SERVICE_PORT", 8050),
            redis_url=_read_str("BROKER_REDIS_URL", "redis://redis:6379/0"),
            tick_queue_size=_read_int("BROKER_TICK_QUEUE_SIZE", 1000),
            tick_stream_maxlen=_read_optional_int("BROKER_TICK_STREAM_MAXLEN"),
            candle_stream_maxlen=_read_optional_int("BROKER_CANDLE_STREAM_MAXLEN"),
            broker_max_symbol_streams=_read_int("BROKER_MAX_SYMBOL_STREAMS", 20),
            broker_max_trendbar_streams=_read_int("BROKER_MAX_TRENDBAR_STREAMS", 10),
            broker_token_redis_key=_read_str(
                "BROKER_TOKEN_REDIS_KEY",
                "broker:auth:ctrader:current",
            ),
            broker_token_refresh_early_seconds=_read_int(
                "BROKER_TOKEN_REFRESH_EARLY_SECONDS",
                604800,
            ),
            broker_token_refresh_retry_delay_seconds=_read_int(
                "BROKER_TOKEN_REFRESH_RETRY_DELAY_SECONDS",
                30,
            ),
            broker_token_refresh_max_retries=_read_int(
                "BROKER_TOKEN_REFRESH_MAX_RETRIES",
                3,
            ),
            log_level=_read_str("BROKER_LOG_LEVEL", "INFO"),
            log_format=_read_str("BROKER_LOG_FORMAT", "pretty"),
            ctrader_request_timeout_seconds=_read_float(
                "BROKER_CTRADER_REQUEST_TIMEOUT_SECONDS", 20.0
            ),
            broker_provider=_read_provider(),
        )

    def load_credentials(self) -> CtraderCredentials:
        return CtraderCredentials.from_env()

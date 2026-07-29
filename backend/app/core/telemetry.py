"""OpenTelemetry tracing setup and small helpers used across the AI pipeline.

``setup_telemetry`` wires the global tracer provider (Arize Phoenix via OTLP)
and auto-instruments OpenAI calls. Remote export is skipped when Phoenix auth
is missing, and a circuit breaker stops log spam after repeated export failures
(invalid token, 502, truncated responses) so chat/LLM turns are not drowned out.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Mapping, Optional, Sequence
from urllib.parse import urlparse

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SpanExportResult,
    SpanExporter,
)
from opentelemetry.trace import Span, Status, StatusCode, Tracer
from openinference.instrumentation.openai import OpenAIInstrumentor

logger = logging.getLogger(__name__)

# After this many consecutive export failures, stop calling the remote collector.
_EXPORT_FAILURE_LIMIT = 3
_NOISE_LOGGER_NAMES = (
    "opentelemetry.exporter.otlp.proto.http.trace_exporter",
    "opentelemetry.sdk.trace.export",
)


class CircuitBreakingSpanExporter(SpanExporter):
    """Wrap an exporter and trip open after repeated failures.

    Prevents endless 401/502/ChunkedEncodingError retries from flooding logs
    while the application continues serving requests.
    """

    def __init__(
        self,
        inner: SpanExporter,
        *,
        failure_limit: int = _EXPORT_FAILURE_LIMIT,
    ) -> None:
        self._inner = inner
        self._failure_limit = max(1, failure_limit)
        self._consecutive_failures = 0
        self._open = False
        self._opened_at = 0.0

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        if self._open:
            return SpanExportResult.FAILURE
        try:
            result = self._inner.export(spans)
        except Exception as exc:  # noqa: BLE001 — must never raise into the app
            self._record_failure(exc)
            return SpanExportResult.FAILURE
        if result is SpanExportResult.SUCCESS:
            self._consecutive_failures = 0
            return result
        self._record_failure(None)
        return result

    def shutdown(self) -> None:
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        if self._open:
            return False
        return self._inner.force_flush(timeout_millis)

    def _record_failure(self, exc: Optional[BaseException]) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures < self._failure_limit or self._open:
            return
        self._open = True
        self._opened_at = time.monotonic()
        detail = f" ({exc})" if exc else ""
        logger.warning(
            "OpenTelemetry remote export disabled after %s consecutive failures%s. "
            "Chat/LLM continues normally. Fix PHOENIX_API_KEY / OTEL endpoint, "
            "or set OTEL_ENABLED=false for local development.",
            self._failure_limit,
            detail,
        )
        for name in _NOISE_LOGGER_NAMES:
            logging.getLogger(name).setLevel(logging.CRITICAL)


def _is_phoenix_cloud(endpoint: str) -> bool:
    host = (urlparse(endpoint).hostname or "").lower()
    return "phoenix.arize.com" in host or host.endswith("arize.com")


def _normalize_traces_endpoint(endpoint: str) -> str:
    value = (endpoint or "").strip().rstrip("/")
    if not value:
        return value
    if value.endswith("/v1/traces"):
        return value
    if value.endswith("/v1"):
        return f"{value}/traces"
    return f"{value}/v1/traces"


def _resolve_endpoint(settings) -> str:
    phoenix = str(getattr(settings, "phoenix_collector_endpoint", "") or "").strip().strip("'\"")
    if phoenix:
        return _normalize_traces_endpoint(phoenix)
    return _normalize_traces_endpoint(str(settings.otel_endpoint or ""))


def _resolve_headers(settings) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    raw = str(getattr(settings, "otel_headers", "") or "").strip()
    if raw:
        for part in raw.split(","):
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'\"")
            if key:
                headers[key] = value
    api_key = str(getattr(settings, "phoenix_api_key", "") or "").strip().strip("'\"")
    if api_key and "authorization" not in {k.lower() for k in headers}:
        # Phoenix Cloud expects Bearer auth on the OTLP HTTP exporter.
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def setup_telemetry(settings) -> None:
    """Configure the global OpenTelemetry tracer provider and OpenAI instrumentation.

    Args:
        settings: Application settings exposing ``otel_enabled``, endpoint,
            service name, and optional Phoenix API key / collector URL.
    """
    if not settings.otel_enabled:
        logger.info("OpenTelemetry disabled (OTEL_ENABLED=false)")
        return

    endpoint = _resolve_endpoint(settings)
    headers = _resolve_headers(settings)
    has_auth = any(k.lower() == "authorization" for k in headers)

    if not endpoint:
        logger.warning("OpenTelemetry enabled but no OTLP endpoint configured; skipping export")
        return

    if _is_phoenix_cloud(endpoint) and not has_auth:
        logger.warning(
            "OpenTelemetry Phoenix endpoint configured without PHOENIX_API_KEY / "
            "OTEL_EXPORTER_OTLP_HEADERS Authorization. Skipping remote export to "
            "avoid 401 spam. Set a valid key or OTEL_ENABLED=false."
        )
        return

    resource = Resource.create({"service.name": settings.otel_service_name})
    provider = TracerProvider(resource=resource)
    try:
        # Mute verbose exporter retries; circuit breaker logs one clear warning instead.
        for name in _NOISE_LOGGER_NAMES:
            logging.getLogger(name).setLevel(logging.CRITICAL)
        raw_exporter = OTLPSpanExporter(endpoint=endpoint, headers=headers or None)
        exporter = CircuitBreakingSpanExporter(raw_exporter)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        OpenAIInstrumentor().instrument()
        logger.info(
            "OpenTelemetry export enabled endpoint=%s auth=%s",
            endpoint,
            "yes" if has_auth else "no",
        )
    except Exception:
        logger.exception("Failed to configure OpenTelemetry; continuing without export")


def get_tracer(name: str) -> Tracer:
    """Return a tracer for the given instrumentation scope.

    Safe to call even when telemetry is disabled or not yet configured: the
    global provider defaults to a no-op provider until ``setup_telemetry``
    (or nothing) installs a real one.

    Args:
        name: Dotted module/component name for the tracer.

    Returns:
        An OpenTelemetry ``Tracer`` bound to the current global provider.
    """
    return trace.get_tracer(name)


def set_span_attrs(span: Optional[Span], attrs: Mapping[str, Any]) -> None:
    """Set multiple attributes on a span, tolerating disabled/no-op spans.

    Args:
        span: Target span. May be ``None`` or a non-recording span.
        attrs: Flat mapping of attribute name to a primitive value. ``None``
            values are skipped; non-primitive values are stringified.
    """
    if span is None or not span.is_recording():
        return
    for key, value in attrs.items():
        if value is None:
            continue
        if not isinstance(value, (str, bool, int, float)):
            value = str(value)
        span.set_attribute(key, value)


def record_exception(span: Optional[Span], exc: BaseException) -> None:
    """Record an exception on a span and mark it as errored.

    Args:
        span: Target span. May be ``None`` or a non-recording span.
        exc: The exception being handled.
    """
    if span is None:
        return
    span.record_exception(exc)
    span.set_status(Status(StatusCode.ERROR, str(exc)))

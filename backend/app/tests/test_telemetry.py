"""Tests for OpenTelemetry setup helpers and export circuit breaker."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from opentelemetry.sdk.trace.export import SpanExportResult

from app.core.telemetry import (
    CircuitBreakingSpanExporter,
    _normalize_traces_endpoint,
    _resolve_endpoint,
    _resolve_headers,
)


def test_normalize_traces_endpoint_appends_path() -> None:
    assert (
        _normalize_traces_endpoint("https://app.phoenix.arize.com/s/demo")
        == "https://app.phoenix.arize.com/s/demo/v1/traces"
    )
    assert (
        _normalize_traces_endpoint("https://app.phoenix.arize.com/s/demo/v1/traces")
        == "https://app.phoenix.arize.com/s/demo/v1/traces"
    )


def test_resolve_endpoint_prefers_phoenix_collector() -> None:
    settings = SimpleNamespace(
        phoenix_collector_endpoint="https://app.phoenix.arize.com/s/AI-Coding-Workspace",
        otel_endpoint="https://ignored.example/v1/traces",
    )
    assert _resolve_endpoint(settings).endswith("/v1/traces")
    assert "AI-Coding-Workspace" in _resolve_endpoint(settings)


def test_resolve_headers_from_phoenix_api_key() -> None:
    settings = SimpleNamespace(otel_headers="", phoenix_api_key="test-key")
    headers = _resolve_headers(settings)
    assert headers["Authorization"] == "Bearer test-key"


def test_circuit_breaker_opens_after_failures() -> None:
    inner = MagicMock()
    inner.export.return_value = SpanExportResult.FAILURE
    exporter = CircuitBreakingSpanExporter(inner, failure_limit=2)

    assert exporter.export([]) is SpanExportResult.FAILURE
    assert exporter.export([]) is SpanExportResult.FAILURE
    assert exporter._open is True
    # Further calls short-circuit without hitting the inner exporter again.
    before = inner.export.call_count
    assert exporter.export([]) is SpanExportResult.FAILURE
    assert inner.export.call_count == before

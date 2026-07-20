"""
SmartPrep AI - In-process Telemetry
Tracks latency, error rates, token costs, and usage counts as first-class metrics.
Exposed at GET /metrics in Prometheus text format.

Usage:
    from app.utils.telemetry import telemetry
    with telemetry.timer("evaluate_answer"):
        result = await llm_service.evaluate_answer(...)
    telemetry.record_tokens("evaluate_answer", prompt_tokens=400, completion_tokens=200)
    telemetry.record_error("evaluate_answer")
"""
import time
import threading
from contextlib import contextmanager
from typing import Dict, Optional
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Groq free-tier pricing estimate ($/1M tokens, as of 2024)
# llama3-70b-8192 pricing is $0.59 input / $0.79 output per 1M tokens
GROQ_INPUT_COST_PER_TOKEN  = 0.59 / 1_000_000
GROQ_OUTPUT_COST_PER_TOKEN = 0.79 / 1_000_000


class EndpointMetrics:
    """Per-endpoint metrics bucket (thread-safe with RLock)."""
    def __init__(self, name: str):
        self.name = name
        self._lock = threading.RLock()
        self.request_count = 0
        self.error_count = 0
        self.total_latency_ms = 0.0
        self.min_latency_ms: Optional[float] = None
        self.max_latency_ms: Optional[float] = None
        self.prompt_tokens_total = 0
        self.completion_tokens_total = 0
        self.estimated_cost_usd = 0.0
        self.created_at = time.time()

    def record_latency(self, latency_ms: float):
        with self._lock:
            self.request_count += 1
            self.total_latency_ms += latency_ms
            if self.min_latency_ms is None or latency_ms < self.min_latency_ms:
                self.min_latency_ms = latency_ms
            if self.max_latency_ms is None or latency_ms > self.max_latency_ms:
                self.max_latency_ms = latency_ms

    def record_error(self):
        with self._lock:
            self.error_count += 1

    def record_tokens(self, prompt_tokens: int, completion_tokens: int):
        with self._lock:
            self.prompt_tokens_total += prompt_tokens
            self.completion_tokens_total += completion_tokens
            self.estimated_cost_usd += (
                prompt_tokens * GROQ_INPUT_COST_PER_TOKEN
                + completion_tokens * GROQ_OUTPUT_COST_PER_TOKEN
            )

    @property
    def avg_latency_ms(self) -> Optional[float]:
        with self._lock:
            if self.request_count == 0:
                return None
            return round(self.total_latency_ms / self.request_count, 1)

    @property
    def error_rate(self) -> float:
        with self._lock:
            if self.request_count == 0:
                return 0.0
            return round(self.error_count / self.request_count, 4)

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "endpoint": self.name,
                "request_count": self.request_count,
                "error_count": self.error_count,
                "error_rate": self.error_rate,
                "avg_latency_ms": self.avg_latency_ms,
                "min_latency_ms": round(self.min_latency_ms, 1) if self.min_latency_ms else None,
                "max_latency_ms": round(self.max_latency_ms, 1) if self.max_latency_ms else None,
                "prompt_tokens_total": self.prompt_tokens_total,
                "completion_tokens_total": self.completion_tokens_total,
                "estimated_cost_usd": round(self.estimated_cost_usd, 6),
            }

    def to_prometheus(self) -> str:
        name_safe = self.name.replace("/", "_").replace("-", "_").lstrip("_")
        lines = [
            f'smartprep_request_total{{endpoint="{self.name}"}} {self.request_count}',
            f'smartprep_error_total{{endpoint="{self.name}"}} {self.error_count}',
            f'smartprep_prompt_tokens_total{{endpoint="{self.name}"}} {self.prompt_tokens_total}',
            f'smartprep_completion_tokens_total{{endpoint="{self.name}"}} {self.completion_tokens_total}',
            f'smartprep_cost_usd_total{{endpoint="{self.name}"}} {round(self.estimated_cost_usd, 6)}',
        ]
        if self.avg_latency_ms is not None:
            lines.append(f'smartprep_latency_ms_avg{{endpoint="{self.name}"}} {self.avg_latency_ms}')
            lines.append(f'smartprep_latency_ms_min{{endpoint="{self.name}"}} {self.min_latency_ms:.1f}')
            lines.append(f'smartprep_latency_ms_max{{endpoint="{self.name}"}} {self.max_latency_ms:.1f}')
        return "\n".join(lines)


class Telemetry:
    """Global telemetry registry. Singleton via module-level instance."""

    def __init__(self):
        self._endpoints: Dict[str, EndpointMetrics] = {}
        self._lock = threading.RLock()
        self._session_count = 0
        self._session_cost_total = 0.0

    def _get_or_create(self, endpoint: str) -> EndpointMetrics:
        with self._lock:
            if endpoint not in self._endpoints:
                self._endpoints[endpoint] = EndpointMetrics(endpoint)
            return self._endpoints[endpoint]

    @contextmanager
    def timer(self, endpoint: str):
        """Context manager that records latency for an operation."""
        t0 = time.perf_counter()
        try:
            yield
        except Exception:
            self._get_or_create(endpoint).record_error()
            raise
        finally:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            self._get_or_create(endpoint).record_latency(elapsed_ms)

    def record_tokens(self, endpoint: str, prompt_tokens: int, completion_tokens: int):
        self._get_or_create(endpoint).record_tokens(prompt_tokens, completion_tokens)
        with self._lock:
            cost = (
                prompt_tokens * GROQ_INPUT_COST_PER_TOKEN
                + completion_tokens * GROQ_OUTPUT_COST_PER_TOKEN
            )
            self._session_cost_total += cost

    def record_error(self, endpoint: str):
        self._get_or_create(endpoint).record_error()

    def increment_sessions(self):
        with self._lock:
            self._session_count += 1

    def get_summary(self) -> dict:
        with self._lock:
            total_cost = sum(
                e.estimated_cost_usd for e in self._endpoints.values()
            )
            total_requests = sum(e.request_count for e in self._endpoints.values())
            total_errors = sum(e.error_count for e in self._endpoints.values())
            return {
                "total_requests": total_requests,
                "total_errors": total_errors,
                "overall_error_rate": round(total_errors / max(total_requests, 1), 4),
                "total_estimated_cost_usd": round(total_cost, 4),
                "session_count": self._session_count,
                "cost_per_session_usd": round(
                    total_cost / max(self._session_count, 1), 4
                ),
                "endpoints": [e.to_dict() for e in self._endpoints.values()],
            }

    def to_prometheus_text(self) -> str:
        lines = [
            "# HELP smartprep_request_total Total requests per endpoint",
            "# TYPE smartprep_request_total counter",
            "# HELP smartprep_error_total Total errors per endpoint",
            "# TYPE smartprep_error_total counter",
            "# HELP smartprep_latency_ms_avg Average latency in milliseconds",
            "# TYPE smartprep_latency_ms_avg gauge",
            "# HELP smartprep_cost_usd_total Estimated LLM cost in USD",
            "# TYPE smartprep_cost_usd_total counter",
        ]
        with self._lock:
            for ep in self._endpoints.values():
                lines.append(ep.to_prometheus())
            lines.append(
                f"smartprep_sessions_total {self._session_count}"
            )
        return "\n".join(lines) + "\n"


# Singleton
telemetry = Telemetry()

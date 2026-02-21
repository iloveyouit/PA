"""
LLM Observability Tracer — Langfuse integration for self-improvement.

Wraps every LLM call, tool invocation, and orchestrator step with
structured tracing. This is "The Mirror" — how the agent sees its
own performance and identifies improvement opportunities.

Features:
- Trace every LLM call with model, tokens, latency, cost
- Trace tool calls (Perplexity, Pinecone, E2B) with input/output
- Track orchestrator spans (triage, context, engineer, critic, distill)
- Score traces with Critic quality scores
- Graceful no-op when Langfuse keys aren't configured

Usage:
    from src.observability.tracer import get_tracer
    tracer = get_tracer()

    # Trace an orchestrator run
    with tracer.trace("orchestrator", input={"query": query}) as trace:
        with trace.span("triage") as span:
            result = triage_node(state)
            span.end(output={"route": result.route})

    # Or use the decorator
    @tracer.observe(name="engineer_node")
    def engineer_node(state):
        ...
"""
import os
import time
import json
import logging
import functools
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Any, Callable
from dataclasses import dataclass, field, asdict

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

logger = logging.getLogger("observability.tracer")

# ---------------------------------------------------------------------------
# Local trace storage (always available, no external deps)
# ---------------------------------------------------------------------------
TRACE_DIR = Path(__file__).resolve().parent.parent.parent / "traces"


@dataclass
class TraceEvent:
    """A single traced event (LLM call, tool call, or span)."""
    event_type: str          # "llm", "tool", "span"
    name: str                # e.g., "triage_node", "search_perplexity"
    started_at: str = ""
    ended_at: str = ""
    duration_ms: float = 0
    model: str = ""
    input_data: dict = field(default_factory=dict)
    output_data: dict = field(default_factory=dict)
    tokens_prompt: int = 0
    tokens_completion: int = 0
    tokens_total: int = 0
    cost_usd: float = 0.0
    status: str = "ok"       # "ok", "error"
    error: str = ""
    score: Optional[float] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class Trace:
    """A full orchestrator trace containing multiple events."""
    trace_id: str
    query: str = ""
    route: str = ""
    started_at: str = ""
    ended_at: str = ""
    duration_ms: float = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    final_score: Optional[float] = None
    events: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Langfuse client wrapper
# ---------------------------------------------------------------------------
class _LangfuseWrapper:
    """Thin wrapper around Langfuse client with lazy init and graceful fallback."""

    def __init__(self):
        self._client = None
        self._enabled = False
        self._init_attempted = False

    def _init(self):
        if self._init_attempted:
            return
        self._init_attempted = True

        public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
        secret_key = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
        host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com").strip()

        if not public_key or not secret_key:
            logger.info("[Tracer] Langfuse keys not configured — using local trace storage only")
            return

        try:
            from langfuse import Langfuse
            self._client = Langfuse(
                public_key=public_key,
                secret_key=secret_key,
                host=host,
            )
            self._enabled = True
            logger.info("[Tracer] Langfuse connected: %s", host)
        except ImportError:
            logger.warning("[Tracer] langfuse package not installed — using local traces only")
        except Exception as e:
            logger.warning("[Tracer] Langfuse init failed (%s) — using local traces only", e)

    @property
    def client(self):
        if not self._init_attempted:
            self._init()
        return self._client

    @property
    def enabled(self) -> bool:
        if not self._init_attempted:
            self._init()
        return self._enabled


_langfuse = _LangfuseWrapper()


# ---------------------------------------------------------------------------
# Tracer class
# ---------------------------------------------------------------------------
class AgentTracer:
    """
    Main tracer for the self-improving agent.

    Provides both Langfuse cloud tracing (when configured) and local
    JSON trace storage (always available). This dual approach ensures
    observability data is never lost.
    """

    def __init__(self):
        self._current_trace: Optional[Trace] = None
        self._langfuse_trace = None

    def trace(self, name: str, *, input_data: Optional[dict] = None, metadata: Optional[dict] = None):
        """Start a new trace (top-level orchestrator run)."""
        return _TraceContext(self, name, input_data=input_data, metadata=metadata)

    def span(self, name: str, *, input_data: Optional[dict] = None):
        """Create a span within the current trace."""
        return _SpanContext(self, name, "span", input_data=input_data)

    def llm_call(self, name: str, *, model: str = "", input_data: Optional[dict] = None):
        """Create a tracked LLM call within the current trace."""
        return _SpanContext(self, name, "llm", input_data=input_data, model=model)

    def tool_call(self, name: str, *, input_data: Optional[dict] = None):
        """Create a tracked tool call within the current trace."""
        return _SpanContext(self, name, "tool", input_data=input_data)

    def observe(self, *, name: Optional[str] = None, event_type: str = "span"):
        """Decorator to trace a function call."""
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                span_name = name or func.__name__
                with _SpanContext(self, span_name, event_type):
                    return func(*args, **kwargs)
            return wrapper
        return decorator

    def score(self, value: float, *, name: str = "quality", comment: str = ""):
        """Record a quality score for the current trace."""
        if self._current_trace:
            self._current_trace.final_score = value

        if _langfuse.enabled and self._langfuse_trace:
            try:
                self._langfuse_trace.score(name=name, value=value, comment=comment)
            except Exception as e:
                logger.debug("Langfuse score failed: %s", e)

    def _add_event(self, event: TraceEvent):
        """Add an event to the current trace."""
        if self._current_trace:
            self._current_trace.events.append(asdict(event))
            self._current_trace.total_tokens += event.tokens_total
            self._current_trace.total_cost_usd += event.cost_usd

    def _save_trace(self, trace: Trace):
        """Save trace to local JSON storage."""
        TRACE_DIR.mkdir(exist_ok=True)
        date_str = datetime.now().strftime("%Y-%m-%d")
        trace_file = TRACE_DIR / f"traces-{date_str}.jsonl"

        try:
            with open(trace_file, "a") as f:
                f.write(json.dumps(asdict(trace), default=str) + "\n")
            logger.debug("[Tracer] Saved trace to %s", trace_file)
        except Exception as e:
            logger.warning("[Tracer] Failed to save local trace: %s", e)

        # Flush Langfuse
        if _langfuse.enabled and _langfuse.client:
            try:
                _langfuse.client.flush()
            except Exception:
                pass


class _TraceContext:
    """Context manager for a top-level trace."""

    def __init__(self, tracer: AgentTracer, name: str, *, input_data: Optional[dict] = None, metadata: Optional[dict] = None):
        self.tracer = tracer
        self.name = name
        self.input_data = input_data or {}
        self.metadata = metadata or {}
        self.trace: Optional[Trace] = None
        self._start_time = 0.0

    def __enter__(self):
        self._start_time = time.time()
        now = datetime.now(timezone.utc).isoformat()
        trace_id = f"trace-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}"

        self.trace = Trace(
            trace_id=trace_id,
            query=self.input_data.get("query", ""),
            started_at=now,
            metadata=self.metadata,
        )
        self.tracer._current_trace = self.trace

        # Create Langfuse trace
        if _langfuse.enabled and _langfuse.client:
            try:
                self.tracer._langfuse_trace = _langfuse.client.trace(
                    name=self.name,
                    input=self.input_data,
                    metadata=self.metadata,
                )
            except Exception as e:
                logger.debug("Langfuse trace creation failed: %s", e)

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.trace:
            self.trace.ended_at = datetime.now(timezone.utc).isoformat()
            self.trace.duration_ms = round((time.time() - self._start_time) * 1000, 1)

            if exc_type:
                self.trace.metadata["error"] = str(exc_val)

            self.tracer._save_trace(self.trace)
            self.tracer._current_trace = None
            self.tracer._langfuse_trace = None

        return False  # Don't suppress exceptions

    def span(self, name: str, *, input_data: Optional[dict] = None):
        return _SpanContext(self.tracer, name, "span", input_data=input_data)

    def llm_call(self, name: str, *, model: str = "", input_data: Optional[dict] = None):
        return _SpanContext(self.tracer, name, "llm", input_data=input_data, model=model)

    def tool_call(self, name: str, *, input_data: Optional[dict] = None):
        return _SpanContext(self.tracer, name, "tool", input_data=input_data)


class _SpanContext:
    """Context manager for a span/event within a trace."""

    def __init__(self, tracer: AgentTracer, name: str, event_type: str, *, input_data: Optional[dict] = None, model: str = ""):
        self.tracer = tracer
        self.name = name
        self.event_type = event_type
        self.input_data = input_data or {}
        self.model = model
        self.event: Optional[TraceEvent] = None
        self._start_time = 0.0
        self._langfuse_span = None

    def __enter__(self):
        self._start_time = time.time()
        self.event = TraceEvent(
            event_type=self.event_type,
            name=self.name,
            started_at=datetime.now(timezone.utc).isoformat(),
            model=self.model,
            input_data=self.input_data,
        )

        # Create Langfuse span
        if _langfuse.enabled and self.tracer._langfuse_trace:
            try:
                if self.event_type == "llm":
                    self._langfuse_span = self.tracer._langfuse_trace.generation(
                        name=self.name,
                        model=self.model,
                        input=self.input_data,
                    )
                else:
                    self._langfuse_span = self.tracer._langfuse_trace.span(
                        name=self.name,
                        input=self.input_data,
                    )
            except Exception as e:
                logger.debug("Langfuse span creation failed: %s", e)

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.event:
            self.event.ended_at = datetime.now(timezone.utc).isoformat()
            self.event.duration_ms = round((time.time() - self._start_time) * 1000, 1)

            if exc_type:
                self.event.status = "error"
                self.event.error = str(exc_val)

            self.tracer._add_event(self.event)

            # Update Langfuse span
            if self._langfuse_span:
                try:
                    self._langfuse_span.end(
                        output=self.event.output_data,
                        metadata={"duration_ms": self.event.duration_ms},
                    )
                except Exception:
                    pass

        return False

    def set_output(self, data: dict):
        """Set the output data for this span."""
        if self.event:
            self.event.output_data = data

    def set_usage(self, prompt_tokens: int = 0, completion_tokens: int = 0, cost_usd: float = 0.0):
        """Set token usage and cost for LLM calls."""
        if self.event:
            self.event.tokens_prompt = prompt_tokens
            self.event.tokens_completion = completion_tokens
            self.event.tokens_total = prompt_tokens + completion_tokens
            self.event.cost_usd = cost_usd

        if self._langfuse_span and hasattr(self._langfuse_span, 'update'):
            try:
                self._langfuse_span.update(
                    usage={
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": prompt_tokens + completion_tokens,
                    }
                )
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------
_tracer_instance: Optional[AgentTracer] = None


def get_tracer() -> AgentTracer:
    """Get or create the global tracer instance."""
    global _tracer_instance
    if _tracer_instance is None:
        _tracer_instance = AgentTracer()
    return _tracer_instance


# ---------------------------------------------------------------------------
# Utility: read local traces
# ---------------------------------------------------------------------------
def read_traces(
    days_back: int = 7,
    trace_dir: Optional[str] = None,
) -> list[dict]:
    """Read local trace files from the last N days."""
    tdir = Path(trace_dir) if trace_dir else TRACE_DIR
    if not tdir.exists():
        return []

    traces = []
    for f in sorted(tdir.glob("traces-*.jsonl")):
        try:
            with open(f) as fp:
                for line in fp:
                    line = line.strip()
                    if line:
                        traces.append(json.loads(line))
        except Exception as e:
            logger.warning("Failed to read %s: %s", f, e)

    return traces


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    tracer = get_tracer()

    # Demo trace
    with tracer.trace("demo-orchestrator", input_data={"query": "test query"}) as t:
        with t.span("triage", input_data={"query": "test"}) as s:
            time.sleep(0.1)
            s.set_output({"route": "engineer"})

        with t.llm_call("engineer", model="claude-sonnet-4-20250514") as lc:
            time.sleep(0.2)
            lc.set_output({"draft": "# Draft code..."})
            lc.set_usage(prompt_tokens=500, completion_tokens=1200)

        tracer.score(8.0, name="quality", comment="Good output")

    print("✅ Demo trace created")
    traces = read_traces()
    print(f"Total traces on disk: {len(traces)}")

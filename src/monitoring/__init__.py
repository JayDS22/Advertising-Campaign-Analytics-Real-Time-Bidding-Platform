"""Process-local metrics registry. Prometheus exporter wires onto this."""
from .metrics import MetricsRegistry

__all__ = ["MetricsRegistry"]

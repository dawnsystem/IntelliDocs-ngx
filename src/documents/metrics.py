"""
Metrics module for IntelliDocs AI Scanner.

This module provides Prometheus metrics for monitoring and observability of the AI Scanner:
- AI scan operations (success/failure)
- Scan duration
- Suggestions by action (applied/rejected/ignored)
- Confidence levels by suggestion type
- Error rates for alerting

Integrates with Prometheus for metrics collection and Grafana for visualization.
"""

from __future__ import annotations

import logging
from typing import Optional

from prometheus_client import Counter, Histogram, Gauge, Info

logger = logging.getLogger("paperless.metrics")

# ============================================================================
# AI Scanner Metrics
# ============================================================================

# Counter for total AI scans
ai_scans_total = Counter(
    "ai_scans_total",
    "Total number of AI document scans performed",
    ["status"],  # status: success, failure
)

# Histogram for scan duration
ai_scan_duration_seconds = Histogram(
    "ai_scan_duration_seconds",
    "Duration of AI document scans in seconds",
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0),
)

# Counter for suggestions by action
ai_suggestions_total = Counter(
    "ai_suggestions_total",
    "Total number of AI suggestions by action taken",
    ["suggestion_type", "action"],  # action: applied, rejected, ignored
)

# Gauge for confidence levels by type
ai_confidence_by_type = Gauge(
    "ai_confidence_by_type",
    "AI confidence levels by suggestion type",
    ["suggestion_type", "document_id"],
)

# Counter for AI errors
ai_errors_total = Counter(
    "ai_errors_total",
    "Total number of AI errors",
    ["error_type"],  # error_type: ml_load_failure, ner_failure, classification_failure, etc.
)

# Info metric for AI scanner configuration
ai_scanner_info = Info(
    "ai_scanner_info",
    "AI Scanner configuration information",
)

# ============================================================================
# Metric Helper Functions
# ============================================================================


def record_scan_success():
    """Record a successful AI scan."""
    ai_scans_total.labels(status="success").inc()


def record_scan_failure():
    """Record a failed AI scan."""
    ai_scans_total.labels(status="failure").inc()


def record_scan_duration(duration: float):
    """
    Record the duration of an AI scan.
    
    Args:
        duration: Duration in seconds
    """
    ai_scan_duration_seconds.observe(duration)


def record_suggestion_applied(suggestion_type: str):
    """
    Record an AI suggestion that was applied.
    
    Args:
        suggestion_type: Type of suggestion (tags, correspondent, document_type, etc.)
    """
    ai_suggestions_total.labels(
        suggestion_type=suggestion_type,
        action="applied"
    ).inc()


def record_suggestion_rejected(suggestion_type: str):
    """
    Record an AI suggestion that was rejected by the user.
    
    Args:
        suggestion_type: Type of suggestion (tags, correspondent, document_type, etc.)
    """
    ai_suggestions_total.labels(
        suggestion_type=suggestion_type,
        action="rejected"
    ).inc()


def record_suggestion_ignored(suggestion_type: str):
    """
    Record an AI suggestion that was ignored (below threshold).
    
    Args:
        suggestion_type: Type of suggestion (tags, correspondent, document_type, etc.)
    """
    ai_suggestions_total.labels(
        suggestion_type=suggestion_type,
        action="ignored"
    ).inc()


def record_confidence(suggestion_type: str, document_id: int, confidence: float):
    """
    Record confidence level for a suggestion.
    
    Args:
        suggestion_type: Type of suggestion
        document_id: Document ID
        confidence: Confidence score (0.0 to 1.0)
    """
    ai_confidence_by_type.labels(
        suggestion_type=suggestion_type,
        document_id=str(document_id)
    ).set(confidence)


def record_error(error_type: str):
    """
    Record an AI error.
    
    Args:
        error_type: Type of error (ml_load_failure, ner_failure, etc.)
    """
    ai_errors_total.labels(error_type=error_type).inc()
    logger.error(f"AI error recorded: {error_type}")


def set_scanner_info(
    ml_enabled: bool,
    advanced_ocr_enabled: bool,
    auto_apply_threshold: float,
    suggest_threshold: float,
):
    """
    Set AI scanner configuration information.
    
    Args:
        ml_enabled: Whether ML features are enabled
        advanced_ocr_enabled: Whether advanced OCR is enabled
        auto_apply_threshold: Threshold for auto-applying suggestions
        suggest_threshold: Threshold for suggesting (not auto-applying)
    """
    ai_scanner_info.info({
        "ml_enabled": str(ml_enabled),
        "advanced_ocr_enabled": str(advanced_ocr_enabled),
        "auto_apply_threshold": str(auto_apply_threshold),
        "suggest_threshold": str(suggest_threshold),
    })


# ============================================================================
# Metrics Context Manager
# ============================================================================


class ScanMetricsContext:
    """
    Context manager for tracking AI scan metrics.
    
    Usage:
        with ScanMetricsContext(document_id=123):
            # perform scan
            pass
    """
    
    def __init__(self, document_id: Optional[int] = None):
        """
        Initialize metrics context.
        
        Args:
            document_id: Optional document ID for tracking
        """
        self.document_id = document_id
        self._timer = None
    
    def __enter__(self):
        """Start timing the scan."""
        self._timer = ai_scan_duration_seconds.time()
        self._timer.__enter__()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Record scan completion."""
        self._timer.__exit__(exc_type, exc_val, exc_tb)
        
        if exc_type is None:
            record_scan_success()
        else:
            record_scan_failure()
            # Don't suppress the exception
            return False


# ============================================================================
# Utility Functions
# ============================================================================


def get_failure_rate() -> float:
    """
    Calculate the current AI scan failure rate.
    
    Returns:
        Failure rate as a percentage (0-100)
    """
    try:
        success = ai_scans_total.labels(status="success")._value.get()
        failure = ai_scans_total.labels(status="failure")._value.get()
        
        total = success + failure
        if total == 0:
            return 0.0
        
        return (failure / total) * 100
    except Exception as e:
        logger.warning(f"Failed to calculate failure rate: {e}")
        return 0.0


def log_metrics_summary():
    """Log a summary of current metrics."""
    try:
        success = ai_scans_total.labels(status="success")._value.get()
        failure = ai_scans_total.labels(status="failure")._value.get()
        failure_rate = get_failure_rate()
        
        logger.info(
            f"AI Scanner Metrics Summary: "
            f"Success={success}, Failure={failure}, "
            f"Failure Rate={failure_rate:.2f}%"
        )
    except Exception as e:
        logger.warning(f"Failed to log metrics summary: {e}")

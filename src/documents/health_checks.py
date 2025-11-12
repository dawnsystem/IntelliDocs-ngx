"""
Health Checks for AI/ML Components in IntelliDocs-ngx.

Provides comprehensive health monitoring for:
- AI Scanner status
- ML Classifier model loading and functionality
- NER (Named Entity Recognition) functionality
- Memory usage monitoring
- GPU availability and status

All checks are designed to run quickly (<100ms) and provide
detailed information about component failures.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict

import psutil
import torch
from django.conf import settings
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

logger = logging.getLogger("paperless.health_checks")


class AIHealthStatus:
    """Container for AI health check results."""
    
    def __init__(self):
        self.overall_status = "healthy"  # healthy, degraded, unhealthy
        self.checks = {}
        self.response_time_ms = 0.0
        self.timestamp = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "status": self.overall_status,
            "response_time_ms": round(self.response_time_ms, 2),
            "timestamp": self.timestamp,
            "checks": self.checks,
        }


def check_ai_scanner_status() -> Dict[str, Any]:
    """
    Check if AI Scanner is enabled and configured.
    
    Returns:
        Dict with status, enabled flag, and any error messages
    """
    try:
        ai_scanner_enabled = getattr(settings, "PAPERLESS_ENABLE_AI_SCANNER", False)
        
        if not ai_scanner_enabled:
            return {
                "status": "disabled",
                "enabled": False,
                "message": "AI Scanner is not enabled in settings",
            }
        
        # Try to import and instantiate the scanner
        from documents.ai_scanner import get_ai_scanner
        
        scanner = get_ai_scanner()
        
        return {
            "status": "healthy",
            "enabled": True,
            "ml_enabled": scanner.ml_enabled,
            "advanced_ocr_enabled": scanner.advanced_ocr_enabled,
            "auto_apply_threshold": scanner.auto_apply_threshold,
            "suggest_threshold": scanner.suggest_threshold,
        }
    
    except Exception as e:
        logger.error(f"AI Scanner health check failed: {e}", exc_info=True)
        return {
            "status": "unhealthy",
            "enabled": True,
            "error": str(e),
            "error_type": type(e).__name__,
        }


def check_ml_classifier_loaded() -> Dict[str, Any]:
    """
    Check if ML classifier models are loaded correctly.
    
    Returns:
        Dict with status and model information
    """
    try:
        ml_enabled = getattr(settings, "PAPERLESS_ENABLE_ML_FEATURES", True)
        
        if not ml_enabled:
            return {
                "status": "disabled",
                "enabled": False,
                "message": "ML features are not enabled in settings",
            }
        
        # Try to load the classifier
        from documents.ml.classifier import TransformerDocumentClassifier
        
        model_name = getattr(
            settings,
            "PAPERLESS_ML_CLASSIFIER_MODEL",
            "distilbert-base-uncased",
        )
        
        # Quick instantiation test (lazy loading)
        classifier = TransformerDocumentClassifier(model_name=model_name)
        
        # Check if model and tokenizer exist
        has_model = hasattr(classifier, "model") and classifier.model is not None
        has_tokenizer = hasattr(classifier, "tokenizer") and classifier.tokenizer is not None
        
        return {
            "status": "healthy" if (has_model or has_tokenizer) else "initializing",
            "enabled": True,
            "model_name": model_name,
            "model_loaded": has_model,
            "tokenizer_loaded": has_tokenizer,
        }
    
    except Exception as e:
        logger.error(f"ML Classifier health check failed: {e}", exc_info=True)
        return {
            "status": "unhealthy",
            "enabled": True,
            "error": str(e),
            "error_type": type(e).__name__,
        }


def check_ner_functional() -> Dict[str, Any]:
    """
    Check if NER (Named Entity Recognition) is functional.
    
    Returns:
        Dict with status and functionality test results
    """
    try:
        ml_enabled = getattr(settings, "PAPERLESS_ENABLE_ML_FEATURES", True)
        
        if not ml_enabled:
            return {
                "status": "disabled",
                "enabled": False,
                "message": "ML features are not enabled in settings",
            }
        
        # Try to load and test NER
        from documents.ml.ner import DocumentNER
        
        # Quick instantiation test
        ner = DocumentNER()
        
        # Quick functional test with simple text
        test_text = "John Doe works at Acme Corp in New York."
        result = ner.extract_all(test_text)
        
        # Check if we got any entities
        has_entities = any(result.get(key) for key in ["persons", "organizations", "locations"])
        
        return {
            "status": "healthy" if has_entities else "degraded",
            "enabled": True,
            "functional": has_entities,
            "test_entities_found": sum(len(result.get(key, [])) for key in ["persons", "organizations", "locations"]),
        }
    
    except Exception as e:
        logger.error(f"NER health check failed: {e}", exc_info=True)
        return {
            "status": "unhealthy",
            "enabled": True,
            "error": str(e),
            "error_type": type(e).__name__,
        }


def check_memory_usage() -> Dict[str, Any]:
    """
    Check system memory usage.
    
    Returns:
        Dict with memory statistics and status
    """
    try:
        # Get memory info
        memory = psutil.virtual_memory()
        
        # Calculate percentages
        used_percent = memory.percent
        available_gb = memory.available / (1024 ** 3)
        total_gb = memory.total / (1024 ** 3)
        used_gb = memory.used / (1024 ** 3)
        
        # Determine status based on usage
        if used_percent < 75:
            mem_status = "healthy"
        elif used_percent < 90:
            mem_status = "degraded"
        else:
            mem_status = "critical"
        
        return {
            "status": mem_status,
            "used_percent": round(used_percent, 1),
            "available_gb": round(available_gb, 2),
            "total_gb": round(total_gb, 2),
            "used_gb": round(used_gb, 2),
        }
    
    except Exception as e:
        logger.error(f"Memory health check failed: {e}", exc_info=True)
        return {
            "status": "unknown",
            "error": str(e),
            "error_type": type(e).__name__,
        }


def check_gpu_status() -> Dict[str, Any]:
    """
    Check GPU availability and status (if enabled).
    
    Returns:
        Dict with GPU information and status
    """
    try:
        use_gpu = getattr(settings, "PAPERLESS_USE_GPU", False)
        
        if not use_gpu:
            return {
                "status": "disabled",
                "enabled": False,
                "message": "GPU usage is not enabled in settings",
            }
        
        # Check if CUDA is available
        cuda_available = torch.cuda.is_available()
        
        if not cuda_available:
            return {
                "status": "unavailable",
                "enabled": True,
                "cuda_available": False,
                "message": "CUDA is not available on this system",
            }
        
        # Get GPU info
        device_count = torch.cuda.device_count()
        current_device = torch.cuda.current_device()
        device_name = torch.cuda.get_device_name(current_device)
        
        # Get memory info for current device
        memory_allocated = torch.cuda.memory_allocated(current_device) / (1024 ** 3)
        memory_reserved = torch.cuda.memory_reserved(current_device) / (1024 ** 3)
        
        # Get total memory if available
        try:
            total_memory = torch.cuda.get_device_properties(current_device).total_memory / (1024 ** 3)
            memory_usage_percent = (memory_allocated / total_memory) * 100 if total_memory > 0 else 0
        except:
            total_memory = None
            memory_usage_percent = None
        
        return {
            "status": "healthy",
            "enabled": True,
            "cuda_available": True,
            "device_count": device_count,
            "current_device": current_device,
            "device_name": device_name,
            "memory_allocated_gb": round(memory_allocated, 2),
            "memory_reserved_gb": round(memory_reserved, 2),
            "total_memory_gb": round(total_memory, 2) if total_memory else None,
            "memory_usage_percent": round(memory_usage_percent, 1) if memory_usage_percent else None,
        }
    
    except Exception as e:
        logger.error(f"GPU health check failed: {e}", exc_info=True)
        return {
            "status": "error",
            "enabled": True,
            "error": str(e),
            "error_type": type(e).__name__,
        }


def perform_ai_health_checks() -> AIHealthStatus:
    """
    Perform all AI/ML health checks.
    
    Returns:
        AIHealthStatus object with all check results
    """
    start_time = time.time()
    
    health_status = AIHealthStatus()
    health_status.timestamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    
    # Run all health checks
    health_status.checks["ai_scanner"] = check_ai_scanner_status()
    health_status.checks["ml_classifier"] = check_ml_classifier_loaded()
    health_status.checks["ner"] = check_ner_functional()
    health_status.checks["memory"] = check_memory_usage()
    health_status.checks["gpu"] = check_gpu_status()
    
    # Calculate response time
    health_status.response_time_ms = (time.time() - start_time) * 1000
    
    # Determine overall status
    unhealthy_checks = [
        name for name, check in health_status.checks.items()
        if check.get("status") in ["unhealthy", "critical", "error"]
    ]
    
    degraded_checks = [
        name for name, check in health_status.checks.items()
        if check.get("status") == "degraded"
    ]
    
    if unhealthy_checks:
        health_status.overall_status = "unhealthy"
    elif degraded_checks:
        health_status.overall_status = "degraded"
    else:
        health_status.overall_status = "healthy"
    
    # Log results
    logger.info(
        f"AI health check completed in {health_status.response_time_ms:.2f}ms "
        f"- Status: {health_status.overall_status}"
    )
    
    if unhealthy_checks:
        logger.warning(f"Unhealthy components: {', '.join(unhealthy_checks)}")
    
    return health_status


# API Endpoint
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def ai_health_check_view(request):
    """
    API endpoint for AI/ML component health checks.
    
    GET /api/health/ai/
    
    Returns comprehensive health status of all AI/ML components including:
    - AI Scanner status
    - ML Classifier model status
    - NER functionality
    - Memory usage
    - GPU status (if enabled)
    
    Response format:
    {
        "status": "healthy|degraded|unhealthy",
        "response_time_ms": 45.23,
        "timestamp": "2025-11-12 15:30:00 UTC",
        "checks": {
            "ai_scanner": {...},
            "ml_classifier": {...},
            "ner": {...},
            "memory": {...},
            "gpu": {...}
        }
    }
    """
    try:
        health_status = perform_ai_health_checks()
        response_data = health_status.to_dict()
        
        # Set HTTP status based on overall health
        http_status = status.HTTP_200_OK
        if health_status.overall_status == "unhealthy":
            http_status = status.HTTP_503_SERVICE_UNAVAILABLE
        elif health_status.overall_status == "degraded":
            http_status = status.HTTP_200_OK  # Still 200, but degraded
        
        return Response(response_data, status=http_status)
    
    except Exception as e:
        logger.error(f"AI health check endpoint failed: {e}", exc_info=True)
        return Response(
            {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

"""
Training pipeline for custom ML models in IntelliDocs-ngx.

This module provides functionality for:
- Collecting training data from confirmed document metadata
- Preparing and validating training data
- Training custom models with hyperparameter tuning
- Evaluating models with comprehensive metrics
- Versioning and managing trained models
- A/B testing of models
"""

from __future__ import annotations

__all__ = [
    "DataCollector",
    "DataPreparator",
    "ModelTrainer",
    "ModelEvaluator",
    "ModelVersionManager",
    "ABTestManager",
]

# Lazy imports to avoid loading all dependencies at once
_loaded = {}


def __getattr__(name: str):
    """Lazy load training modules."""
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    if name not in _loaded:
        if name == "DataCollector":
            from .data_collector import DataCollector

            _loaded[name] = DataCollector
        elif name == "DataPreparator":
            from .data_preparator import DataPreparator

            _loaded[name] = DataPreparator
        elif name == "ModelTrainer":
            from .trainer import ModelTrainer

            _loaded[name] = ModelTrainer
        elif name == "ModelEvaluator":
            from .evaluator import ModelEvaluator

            _loaded[name] = ModelEvaluator
        elif name == "ModelVersionManager":
            from .version_manager import ModelVersionManager

            _loaded[name] = ModelVersionManager
        elif name == "ABTestManager":
            from .ab_testing import ABTestManager

            _loaded[name] = ABTestManager

    return _loaded[name]

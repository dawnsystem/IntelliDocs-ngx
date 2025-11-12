"""
Model versioning and management.

Manages different versions of trained models with metadata.
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .evaluator import EvaluationMetrics
    from .trainer import TrainingResult

logger = logging.getLogger("paperless.ml.training.version_manager")


@dataclass
class ModelVersion:
    """Information about a model version."""

    version: str
    model_path: str
    created_at: str
    metrics: dict
    config: dict
    notes: str
    is_active: bool


class ModelVersionManager:
    """
    Manages versioning of trained models.

    Provides:
    - Version creation and tracking
    - Model promotion (dev -> staging -> production)
    - Version comparison
    - Model rollback
    """

    def __init__(self, models_dir: str | Path = "./models"):
        """
        Initialize version manager.

        Args:
            models_dir: Base directory for model storage
        """
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)

        # Versions file tracks all versions
        self.versions_file = self.models_dir / "versions.json"
        self.versions = self._load_versions()

        logger.info(f"ModelVersionManager initialized at {self.models_dir}")

    def create_version(
        self,
        model_path: str | Path,
        training_result: TrainingResult,
        eval_metrics: EvaluationMetrics,
        version_name: str | None = None,
        notes: str = "",
    ) -> ModelVersion:
        """
        Create a new model version.

        Args:
            model_path: Path to trained model
            training_result: Training results
            eval_metrics: Evaluation metrics
            version_name: Optional version name (auto-generated if None)
            notes: Optional notes about this version

        Returns:
            ModelVersion object
        """
        model_path = Path(model_path)

        # Generate version name if not provided
        if version_name is None:
            version_name = datetime.now().strftime("v%Y%m%d_%H%M%S")

        logger.info(f"Creating model version: {version_name}")

        # Create version directory
        version_dir = self.models_dir / version_name
        if version_dir.exists():
            msg = f"Version {version_name} already exists"
            raise ValueError(msg)

        # Copy model files
        shutil.copytree(model_path, version_dir)

        # Create version metadata
        version_info = ModelVersion(
            version=version_name,
            model_path=str(version_dir),
            created_at=datetime.now().isoformat(),
            metrics={
                "train_loss": training_result.train_loss,
                "eval_loss": training_result.eval_loss,
                "accuracy": eval_metrics.accuracy,
                "precision": eval_metrics.precision,
                "recall": eval_metrics.recall,
                "f1_score": eval_metrics.f1_score,
            },
            config={
                "model_name": training_result.config.model_name,
                "num_epochs": training_result.config.num_epochs,
                "batch_size": training_result.config.batch_size,
                "learning_rate": training_result.config.learning_rate,
            },
            notes=notes,
            is_active=False,
        )

        # Save version metadata
        metadata_path = version_dir / "version_metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(
                {
                    "version": version_info.version,
                    "created_at": version_info.created_at,
                    "metrics": version_info.metrics,
                    "config": version_info.config,
                    "notes": version_info.notes,
                    "is_active": version_info.is_active,
                },
                f,
                indent=2,
            )

        # Add to versions registry
        self.versions[version_name] = version_info
        self._save_versions()

        logger.info(
            f"Version {version_name} created with "
            f"accuracy={eval_metrics.accuracy:.4f}",
        )

        return version_info

    def list_versions(self, active_only: bool = False) -> list[ModelVersion]:
        """
        List all model versions.

        Args:
            active_only: Only return active versions

        Returns:
            List of ModelVersion objects
        """
        versions = list(self.versions.values())

        if active_only:
            versions = [v for v in versions if v.is_active]

        # Sort by creation date (newest first)
        versions.sort(key=lambda v: v.created_at, reverse=True)

        return versions

    def get_version(self, version_name: str) -> ModelVersion | None:
        """
        Get specific version.

        Args:
            version_name: Version name

        Returns:
            ModelVersion object or None if not found
        """
        return self.versions.get(version_name)

    def activate_version(self, version_name: str) -> None:
        """
        Mark a version as active (for production use).

        Args:
            version_name: Version to activate
        """
        version = self.versions.get(version_name)
        if version is None:
            msg = f"Version {version_name} not found"
            raise ValueError(msg)

        logger.info(f"Activating version: {version_name}")

        version.is_active = True
        self._save_versions()

        # Update version metadata file
        metadata_path = Path(version.model_path) / "version_metadata.json"
        if metadata_path.exists():
            with open(metadata_path) as f:
                data = json.load(f)
            data["is_active"] = True
            with open(metadata_path, "w") as f:
                json.dump(data, f, indent=2)

    def deactivate_version(self, version_name: str) -> None:
        """
        Mark a version as inactive.

        Args:
            version_name: Version to deactivate
        """
        version = self.versions.get(version_name)
        if version is None:
            msg = f"Version {version_name} not found"
            raise ValueError(msg)

        logger.info(f"Deactivating version: {version_name}")

        version.is_active = False
        self._save_versions()

        # Update version metadata file
        metadata_path = Path(version.model_path) / "version_metadata.json"
        if metadata_path.exists():
            with open(metadata_path) as f:
                data = json.load(f)
            data["is_active"] = False
            with open(metadata_path, "w") as f:
                json.dump(data, f, indent=2)

    def compare_versions(
        self,
        version1: str,
        version2: str,
    ) -> dict:
        """
        Compare two model versions.

        Args:
            version1: First version name
            version2: Second version name

        Returns:
            Dictionary with comparison
        """
        v1 = self.versions.get(version1)
        v2 = self.versions.get(version2)

        if v1 is None:
            msg = f"Version {version1} not found"
            raise ValueError(msg)
        if v2 is None:
            msg = f"Version {version2} not found"
            raise ValueError(msg)

        comparison = {
            "version1": {
                "name": v1.version,
                "metrics": v1.metrics,
                "created_at": v1.created_at,
            },
            "version2": {
                "name": v2.version,
                "metrics": v2.metrics,
                "created_at": v2.created_at,
            },
            "improvements": {},
        }

        # Calculate improvements
        for metric in ["accuracy", "precision", "recall", "f1_score"]:
            if metric in v1.metrics and metric in v2.metrics:
                diff = v2.metrics[metric] - v1.metrics[metric]
                pct = (diff / v1.metrics[metric] * 100) if v1.metrics[metric] > 0 else 0
                comparison["improvements"][metric] = {
                    "absolute": diff,
                    "percent": pct,
                }

        logger.info(f"Compared {version1} vs {version2}")

        return comparison

    def delete_version(self, version_name: str, confirm: bool = False) -> None:
        """
        Delete a model version.

        Args:
            version_name: Version to delete
            confirm: Must be True to actually delete
        """
        if not confirm:
            msg = "Must confirm deletion by passing confirm=True"
            raise ValueError(msg)

        version = self.versions.get(version_name)
        if version is None:
            msg = f"Version {version_name} not found"
            raise ValueError(msg)

        if version.is_active:
            msg = f"Cannot delete active version {version_name}"
            raise ValueError(msg)

        logger.warning(f"Deleting version: {version_name}")

        # Delete directory
        model_path = Path(version.model_path)
        if model_path.exists():
            shutil.rmtree(model_path)

        # Remove from registry
        del self.versions[version_name]
        self._save_versions()

        logger.info(f"Version {version_name} deleted")

    def get_best_version(self, metric: str = "f1_score") -> ModelVersion | None:
        """
        Get the best model version based on a metric.

        Args:
            metric: Metric to compare ('accuracy', 'f1_score', etc.)

        Returns:
            Best ModelVersion or None if no versions
        """
        versions = self.list_versions()
        if not versions:
            return None

        # Filter versions that have the metric
        versions_with_metric = [
            v for v in versions if metric in v.metrics
        ]

        if not versions_with_metric:
            return None

        # Find best
        best = max(versions_with_metric, key=lambda v: v.metrics[metric])

        logger.info(
            f"Best version by {metric}: {best.version} "
            f"({metric}={best.metrics[metric]:.4f})",
        )

        return best

    def _load_versions(self) -> dict[str, ModelVersion]:
        """Load versions from registry file."""
        if not self.versions_file.exists():
            return {}

        with open(self.versions_file) as f:
            data = json.load(f)

        versions = {}
        for version_name, version_data in data.items():
            versions[version_name] = ModelVersion(**version_data)

        return versions

    def _save_versions(self) -> None:
        """Save versions to registry file."""
        data = {}
        for version_name, version in self.versions.items():
            data[version_name] = {
                "version": version.version,
                "model_path": version.model_path,
                "created_at": version.created_at,
                "metrics": version.metrics,
                "config": version.config,
                "notes": version.notes,
                "is_active": version.is_active,
            }

        with open(self.versions_file, "w") as f:
            json.dump(data, f, indent=2)

    def export_version_history(self, output_path: str | Path) -> None:
        """
        Export version history to JSON file.

        Args:
            output_path: Path to save history
        """
        output_path = Path(output_path)

        versions_list = [
            {
                "version": v.version,
                "created_at": v.created_at,
                "metrics": v.metrics,
                "config": v.config,
                "notes": v.notes,
                "is_active": v.is_active,
            }
            for v in self.list_versions()
        ]

        with open(output_path, "w") as f:
            json.dump(
                {
                    "exported_at": datetime.now().isoformat(),
                    "total_versions": len(versions_list),
                    "versions": versions_list,
                },
                f,
                indent=2,
            )

        logger.info(f"Exported version history to {output_path}")

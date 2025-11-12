"""
Model evaluation module with comprehensive metrics.

Evaluates trained models with accuracy, precision, recall, F1, and more.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import torch
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from transformers import AutoModelForSequenceClassification, AutoTokenizer

if TYPE_CHECKING:
    from .data_preparator import PreparedDataset

logger = logging.getLogger("paperless.ml.training.evaluator")


@dataclass
class EvaluationMetrics:
    """Comprehensive evaluation metrics."""

    accuracy: float
    precision: float
    recall: float
    f1_score: float
    confusion_matrix: list[list[int]]
    classification_report: dict
    per_class_metrics: dict[str, dict]
    predictions: list[int]
    true_labels: list[int]
    timestamp: str


class ModelEvaluator:
    """
    Evaluates trained models with comprehensive metrics.

    Provides:
    - Standard classification metrics (accuracy, precision, recall, F1)
    - Per-class metrics
    - Confusion matrix
    - Detailed classification report
    - Confidence score analysis
    """

    def __init__(self, model_path: str | Path):
        """
        Initialize evaluator with trained model.

        Args:
            model_path: Path to trained model directory
        """
        self.model_path = Path(model_path)

        if not self.model_path.exists():
            msg = f"Model path does not exist: {model_path}"
            raise ValueError(msg)

        logger.info(f"Loading model from {self.model_path}")

        # Load model and tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(str(self.model_path))
        self.model = AutoModelForSequenceClassification.from_pretrained(
            str(self.model_path),
        )
        self.model.eval()  # Set to evaluation mode

        # Load label maps
        label_map_path = self.model_path / "label_map.json"
        if label_map_path.exists():
            with open(label_map_path) as f:
                maps = json.load(f)
                self.label_map = maps["label_map"]
                # Convert string keys back to int
                self.reverse_label_map = {
                    int(k): v for k, v in maps["reverse_label_map"].items()
                }
        else:
            logger.warning("No label map found, using numeric labels")
            self.label_map = None
            self.reverse_label_map = None

        logger.info("Model loaded successfully")

    def evaluate(
        self,
        test_dataset: PreparedDataset,
        batch_size: int = 16,
    ) -> EvaluationMetrics:
        """
        Evaluate model on test dataset.

        Args:
            test_dataset: Test data
            batch_size: Batch size for inference

        Returns:
            EvaluationMetrics with comprehensive results
        """
        logger.info(f"Evaluating on {len(test_dataset.texts)} test samples")

        # Get predictions
        predictions, confidences = self._predict_batch(
            test_dataset.texts,
            batch_size,
        )

        true_labels = test_dataset.labels

        # Calculate metrics
        accuracy = accuracy_score(true_labels, predictions)
        precision = precision_score(
            true_labels,
            predictions,
            average="weighted",
            zero_division=0,
        )
        recall = recall_score(
            true_labels,
            predictions,
            average="weighted",
            zero_division=0,
        )
        f1 = f1_score(
            true_labels,
            predictions,
            average="weighted",
            zero_division=0,
        )

        # Confusion matrix
        cm = confusion_matrix(true_labels, predictions)

        # Classification report (per-class metrics)
        # Get class names
        if self.reverse_label_map:
            target_names = [
                self.reverse_label_map[i]
                for i in range(len(self.reverse_label_map))
            ]
        else:
            target_names = None

        class_report = classification_report(
            true_labels,
            predictions,
            target_names=target_names,
            output_dict=True,
            zero_division=0,
        )

        # Per-class metrics
        per_class = {}
        for label_idx in range(test_dataset.metadata["num_classes"]):
            label_name = (
                self.reverse_label_map[label_idx]
                if self.reverse_label_map
                else str(label_idx)
            )

            # Get indices for this class
            true_mask = np.array(true_labels) == label_idx
            pred_mask = np.array(predictions) == label_idx

            # Calculate metrics for this class
            tp = np.sum(true_mask & pred_mask)
            fp = np.sum(~true_mask & pred_mask)
            fn = np.sum(true_mask & ~pred_mask)
            tn = np.sum(~true_mask & ~pred_mask)

            class_precision = tp / (tp + fp) if (tp + fp) > 0 else 0
            class_recall = tp / (tp + fn) if (tp + fn) > 0 else 0
            class_f1 = (
                2 * class_precision * class_recall / (class_precision + class_recall)
                if (class_precision + class_recall) > 0
                else 0
            )

            # Average confidence for this class
            class_confidences = [
                confidences[i] for i, pred in enumerate(predictions) if pred == label_idx
            ]
            avg_confidence = (
                np.mean(class_confidences) if class_confidences else 0.0
            )

            per_class[label_name] = {
                "precision": class_precision,
                "recall": class_recall,
                "f1_score": class_f1,
                "support": int(np.sum(true_mask)),
                "avg_confidence": avg_confidence,
            }

        metrics = EvaluationMetrics(
            accuracy=accuracy,
            precision=precision,
            recall=recall,
            f1_score=f1,
            confusion_matrix=cm.tolist(),
            classification_report=class_report,
            per_class_metrics=per_class,
            predictions=predictions,
            true_labels=true_labels,
            timestamp=datetime.now().isoformat(),
        )

        logger.info(
            f"Evaluation complete: accuracy={accuracy:.4f}, "
            f"precision={precision:.4f}, recall={recall:.4f}, f1={f1:.4f}",
        )

        return metrics

    def compare_with_baseline(
        self,
        test_dataset: PreparedDataset,
        baseline_model_path: str | Path,
        batch_size: int = 16,
    ) -> dict:
        """
        Compare current model with baseline model.

        Args:
            test_dataset: Test data
            baseline_model_path: Path to baseline model
            batch_size: Batch size for inference

        Returns:
            Dictionary with comparison results
        """
        logger.info("Comparing with baseline model")

        # Evaluate current model
        current_metrics = self.evaluate(test_dataset, batch_size)

        # Evaluate baseline
        baseline_evaluator = ModelEvaluator(baseline_model_path)
        baseline_metrics = baseline_evaluator.evaluate(test_dataset, batch_size)

        # Calculate improvements
        comparison = {
            "current": {
                "accuracy": current_metrics.accuracy,
                "precision": current_metrics.precision,
                "recall": current_metrics.recall,
                "f1_score": current_metrics.f1_score,
            },
            "baseline": {
                "accuracy": baseline_metrics.accuracy,
                "precision": baseline_metrics.precision,
                "recall": baseline_metrics.recall,
                "f1_score": baseline_metrics.f1_score,
            },
            "improvement": {
                "accuracy": current_metrics.accuracy - baseline_metrics.accuracy,
                "precision": current_metrics.precision - baseline_metrics.precision,
                "recall": current_metrics.recall - baseline_metrics.recall,
                "f1_score": current_metrics.f1_score - baseline_metrics.f1_score,
            },
            "improvement_percent": {
                "accuracy": (
                    (current_metrics.accuracy - baseline_metrics.accuracy)
                    / baseline_metrics.accuracy
                    * 100
                    if baseline_metrics.accuracy > 0
                    else 0
                ),
                "f1_score": (
                    (current_metrics.f1_score - baseline_metrics.f1_score)
                    / baseline_metrics.f1_score
                    * 100
                    if baseline_metrics.f1_score > 0
                    else 0
                ),
            },
        }

        logger.info(
            f"Comparison: accuracy improvement = "
            f"{comparison['improvement_percent']['accuracy']:.2f}%",
        )

        return comparison

    def save_evaluation_report(
        self,
        metrics: EvaluationMetrics,
        output_path: str | Path,
    ) -> None:
        """
        Save evaluation report to file.

        Args:
            metrics: Evaluation metrics
            output_path: Path to save report (JSON)
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        report = {
            "summary": {
                "accuracy": metrics.accuracy,
                "precision": metrics.precision,
                "recall": metrics.recall,
                "f1_score": metrics.f1_score,
            },
            "per_class_metrics": metrics.per_class_metrics,
            "confusion_matrix": metrics.confusion_matrix,
            "classification_report": metrics.classification_report,
            "timestamp": metrics.timestamp,
            "model_path": str(self.model_path),
        }

        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)

        logger.info(f"Evaluation report saved to {output_path}")

    def _predict_batch(
        self,
        texts: list[str],
        batch_size: int,
    ) -> tuple[list[int], list[float]]:
        """
        Predict labels for batch of texts.

        Args:
            texts: List of texts
            batch_size: Batch size

        Returns:
            Tuple of (predictions, confidences)
        """
        predictions = []
        confidences = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]

            # Tokenize
            inputs = self.tokenizer(
                batch,
                truncation=True,
                padding=True,
                max_length=512,
                return_tensors="pt",
            )

            # Predict
            with torch.no_grad():
                outputs = self.model(**inputs)
                probs = torch.nn.functional.softmax(outputs.logits, dim=-1)
                batch_preds = torch.argmax(probs, dim=-1).cpu().numpy()
                batch_confs = torch.max(probs, dim=-1).values.cpu().numpy()

            predictions.extend(batch_preds.tolist())
            confidences.extend(batch_confs.tolist())

        return predictions, confidences

    def analyze_errors(
        self,
        metrics: EvaluationMetrics,
        test_dataset: PreparedDataset,
        top_n: int = 10,
    ) -> dict:
        """
        Analyze most common errors.

        Args:
            metrics: Evaluation metrics
            test_dataset: Test dataset
            top_n: Number of top errors to analyze

        Returns:
            Dictionary with error analysis
        """
        # Find misclassified examples
        errors = []
        for i, (true, pred) in enumerate(
            zip(metrics.true_labels, metrics.predictions)
        ):
            if true != pred:
                true_label = (
                    self.reverse_label_map[true] if self.reverse_label_map else true
                )
                pred_label = (
                    self.reverse_label_map[pred] if self.reverse_label_map else pred
                )

                errors.append(
                    {
                        "index": i,
                        "true_label": true_label,
                        "predicted_label": pred_label,
                        "text_preview": test_dataset.texts[i][:200],
                    },
                )

        # Count error patterns
        from collections import Counter

        error_patterns = Counter(
            (err["true_label"], err["predicted_label"]) for err in errors
        )

        analysis = {
            "total_errors": len(errors),
            "error_rate": len(errors) / len(metrics.true_labels),
            "most_common_errors": [
                {
                    "true_label": true,
                    "predicted_label": pred,
                    "count": count,
                }
                for (true, pred), count in error_patterns.most_common(top_n)
            ],
            "sample_errors": errors[:top_n],
        }

        logger.info(
            f"Error analysis: {len(errors)} errors "
            f"({analysis['error_rate']:.2%} error rate)",
        )

        return analysis

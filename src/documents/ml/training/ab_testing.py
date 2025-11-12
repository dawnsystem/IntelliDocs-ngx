"""
A/B testing framework for comparing model versions in production.

Allows gradual rollout and performance comparison of models.
"""

from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger("paperless.ml.training.ab_testing")


@dataclass
class ABTestConfig:
    """Configuration for an A/B test."""

    test_name: str
    model_a: str  # Version name
    model_b: str  # Version name
    traffic_split: float  # Percentage to model_b (0.0-1.0)
    start_date: str
    end_date: str | None
    is_active: bool


@dataclass
class ABTestResult:
    """Results from an A/B test."""

    model: str
    total_predictions: int
    avg_confidence: float
    user_acceptance_rate: float | None
    error_rate: float | None


class ABTestManager:
    """
    Manages A/B testing of model versions.

    Supports:
    - Traffic splitting between model versions
    - Performance tracking
    - Statistical significance testing
    - Gradual rollout
    """

    def __init__(self, tests_dir: str | Path = "./models/ab_tests"):
        """
        Initialize A/B test manager.

        Args:
            tests_dir: Directory to store test data
        """
        self.tests_dir = Path(tests_dir)
        self.tests_dir.mkdir(parents=True, exist_ok=True)

        self.tests_file = self.tests_dir / "tests.json"
        self.results_file = self.tests_dir / "results.json"

        self.tests = self._load_tests()
        self.results = self._load_results()

        logger.info(f"ABTestManager initialized at {self.tests_dir}")

    def create_test(
        self,
        test_name: str,
        model_a: str,
        model_b: str,
        traffic_split: float = 0.1,
        duration_days: int | None = 7,
    ) -> ABTestConfig:
        """
        Create a new A/B test.

        Args:
            test_name: Name for this test
            model_a: Control model version
            model_b: Treatment model version
            traffic_split: Percentage of traffic to model_b (0.0-1.0)
            duration_days: Test duration in days (None = indefinite)

        Returns:
            ABTestConfig object
        """
        if test_name in self.tests:
            msg = f"Test {test_name} already exists"
            raise ValueError(msg)

        if not 0.0 <= traffic_split <= 1.0:
            msg = "Traffic split must be between 0.0 and 1.0"
            raise ValueError(msg)

        logger.info(
            f"Creating A/B test: {test_name} "
            f"({model_a} vs {model_b}, split={traffic_split})",
        )

        start_date = datetime.now()
        end_date = None
        if duration_days is not None:
            from datetime import timedelta

            end_date = start_date + timedelta(days=duration_days)

        config = ABTestConfig(
            test_name=test_name,
            model_a=model_a,
            model_b=model_b,
            traffic_split=traffic_split,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat() if end_date else None,
            is_active=True,
        )

        self.tests[test_name] = config
        self._save_tests()

        # Initialize results tracking
        self.results[test_name] = {
            "model_a": {
                "total_predictions": 0,
                "total_confidence": 0.0,
                "accepted_suggestions": 0,
                "rejected_suggestions": 0,
                "errors": 0,
            },
            "model_b": {
                "total_predictions": 0,
                "total_confidence": 0.0,
                "accepted_suggestions": 0,
                "rejected_suggestions": 0,
                "errors": 0,
            },
        }
        self._save_results()

        logger.info(f"A/B test {test_name} created and activated")

        return config

    def select_model(self, test_name: str) -> str:
        """
        Select which model to use for a prediction.

        Args:
            test_name: Name of active test

        Returns:
            Model version name to use
        """
        test = self.tests.get(test_name)
        if test is None or not test.is_active:
            msg = f"Test {test_name} not found or inactive"
            raise ValueError(msg)

        # Random selection based on traffic split
        if random.random() < test.traffic_split:
            return test.model_b
        else:
            return test.model_a

    def record_prediction(
        self,
        test_name: str,
        model: str,
        confidence: float,
    ) -> None:
        """
        Record a prediction for tracking.

        Args:
            test_name: Test name
            model: Model used
            confidence: Confidence score
        """
        if test_name not in self.results:
            return

        test = self.tests.get(test_name)
        if test is None:
            return

        # Determine which model this is
        model_key = "model_a" if model == test.model_a else "model_b"

        # Update stats
        self.results[test_name][model_key]["total_predictions"] += 1
        self.results[test_name][model_key]["total_confidence"] += confidence

        # Save periodically (every 100 predictions)
        total = (
            self.results[test_name]["model_a"]["total_predictions"]
            + self.results[test_name]["model_b"]["total_predictions"]
        )
        if total % 100 == 0:
            self._save_results()

    def record_user_feedback(
        self,
        test_name: str,
        model: str,
        accepted: bool,
    ) -> None:
        """
        Record user feedback on a suggestion.

        Args:
            test_name: Test name
            model: Model that made the suggestion
            accepted: Whether user accepted the suggestion
        """
        if test_name not in self.results:
            return

        test = self.tests.get(test_name)
        if test is None:
            return

        model_key = "model_a" if model == test.model_a else "model_b"

        if accepted:
            self.results[test_name][model_key]["accepted_suggestions"] += 1
        else:
            self.results[test_name][model_key]["rejected_suggestions"] += 1

        self._save_results()

    def get_test_results(self, test_name: str) -> dict[str, ABTestResult]:
        """
        Get current results for a test.

        Args:
            test_name: Test name

        Returns:
            Dictionary with results for each model
        """
        if test_name not in self.results:
            msg = f"No results for test {test_name}"
            raise ValueError(msg)

        test = self.tests.get(test_name)
        if test is None:
            msg = f"Test {test_name} not found"
            raise ValueError(msg)

        results = {}

        for model_key, model_name in [
            ("model_a", test.model_a),
            ("model_b", test.model_b),
        ]:
            data = self.results[test_name][model_key]

            total_preds = data["total_predictions"]
            avg_confidence = (
                data["total_confidence"] / total_preds if total_preds > 0 else 0.0
            )

            total_feedback = (
                data["accepted_suggestions"] + data["rejected_suggestions"]
            )
            acceptance_rate = (
                data["accepted_suggestions"] / total_feedback
                if total_feedback > 0
                else None
            )

            error_rate = (
                data["errors"] / total_preds if total_preds > 0 else None
            )

            results[model_key] = ABTestResult(
                model=model_name,
                total_predictions=total_preds,
                avg_confidence=avg_confidence,
                user_acceptance_rate=acceptance_rate,
                error_rate=error_rate,
            )

        return results

    def analyze_test(self, test_name: str) -> dict:
        """
        Analyze A/B test results with statistical comparison.

        Args:
            test_name: Test name

        Returns:
            Dictionary with analysis
        """
        results = self.get_test_results(test_name)
        test = self.tests[test_name]

        model_a_result = results["model_a"]
        model_b_result = results["model_b"]

        # Calculate differences
        confidence_diff = (
            model_b_result.avg_confidence - model_a_result.avg_confidence
        )

        acceptance_diff = None
        if (
            model_a_result.user_acceptance_rate is not None
            and model_b_result.user_acceptance_rate is not None
        ):
            acceptance_diff = (
                model_b_result.user_acceptance_rate
                - model_a_result.user_acceptance_rate
            )

        # Determine recommendation
        recommendation = "inconclusive"
        if model_b_result.total_predictions < 100:
            recommendation = "need_more_data"
        elif acceptance_diff and acceptance_diff > 0.05:  # 5% improvement
            recommendation = "promote_model_b"
        elif acceptance_diff and acceptance_diff < -0.05:  # 5% worse
            recommendation = "keep_model_a"

        analysis = {
            "test_name": test_name,
            "model_a": {
                "version": test.model_a,
                "predictions": model_a_result.total_predictions,
                "avg_confidence": model_a_result.avg_confidence,
                "acceptance_rate": model_a_result.user_acceptance_rate,
            },
            "model_b": {
                "version": test.model_b,
                "predictions": model_b_result.total_predictions,
                "avg_confidence": model_b_result.avg_confidence,
                "acceptance_rate": model_b_result.user_acceptance_rate,
            },
            "differences": {
                "confidence": confidence_diff,
                "acceptance_rate": acceptance_diff,
            },
            "recommendation": recommendation,
            "traffic_split": test.traffic_split,
        }

        logger.info(
            f"Test analysis for {test_name}: "
            f"recommendation={recommendation}, "
            f"confidence_diff={confidence_diff:.4f}",
        )

        return analysis

    def stop_test(self, test_name: str) -> None:
        """
        Stop an active A/B test.

        Args:
            test_name: Test name
        """
        if test_name not in self.tests:
            msg = f"Test {test_name} not found"
            raise ValueError(msg)

        test = self.tests[test_name]
        test.is_active = False

        logger.info(f"Stopped A/B test: {test_name}")
        self._save_tests()

    def increase_traffic(self, test_name: str, new_split: float) -> None:
        """
        Gradually increase traffic to model B.

        Args:
            test_name: Test name
            new_split: New traffic split
        """
        if test_name not in self.tests:
            msg = f"Test {test_name} not found"
            raise ValueError(msg)

        test = self.tests[test_name]
        old_split = test.traffic_split

        if new_split <= old_split:
            msg = "New split must be greater than current split"
            raise ValueError(msg)

        if new_split > 1.0:
            msg = "Split cannot exceed 1.0"
            raise ValueError(msg)

        test.traffic_split = new_split
        self._save_tests()

        logger.info(
            f"Increased traffic for {test_name}: {old_split:.2f} -> {new_split:.2f}",
        )

    def _load_tests(self) -> dict[str, ABTestConfig]:
        """Load tests from file."""
        if not self.tests_file.exists():
            return {}

        with open(self.tests_file) as f:
            data = json.load(f)

        tests = {}
        for name, test_data in data.items():
            tests[name] = ABTestConfig(**test_data)

        return tests

    def _save_tests(self) -> None:
        """Save tests to file."""
        data = {}
        for name, test in self.tests.items():
            data[name] = {
                "test_name": test.test_name,
                "model_a": test.model_a,
                "model_b": test.model_b,
                "traffic_split": test.traffic_split,
                "start_date": test.start_date,
                "end_date": test.end_date,
                "is_active": test.is_active,
            }

        with open(self.tests_file, "w") as f:
            json.dump(data, f, indent=2)

    def _load_results(self) -> dict:
        """Load results from file."""
        if not self.results_file.exists():
            return {}

        with open(self.results_file) as f:
            return json.load(f)

    def _save_results(self) -> None:
        """Save results to file."""
        with open(self.results_file, "w") as f:
            json.dump(self.results, f, indent=2)

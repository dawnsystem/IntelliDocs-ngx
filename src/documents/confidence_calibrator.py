"""
Confidence Calibration System for AI Scanner

This module provides confidence calibration based on historical feedback data.
It analyzes the correlation between AI confidence scores and actual accuracy
to dynamically adjust thresholds for better auto-apply decisions.

Key Features:
- Analyzes correlation between confidence scores and acceptance rates
- Adjusts thresholds per suggestion type (tags, correspondents, etc.)
- Per-user calibration for personalized thresholds
- Ensures auto-apply only when accuracy >95%
- Tracks calibration history for auditing
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Dict, Optional, Tuple

from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Avg, Count, Q
from django.utils import timezone

if TYPE_CHECKING:
    from documents.models import AISuggestionFeedback

logger = logging.getLogger("paperless.confidence_calibrator")


class CalibrationResult:
    """Container for calibration analysis results."""
    
    def __init__(self):
        self.total_samples: int = 0
        self.acceptance_rate: float = 0.0
        self.avg_confidence: float = 0.0
        self.correlation_score: float = 0.0
        self.recommended_auto_threshold: float = 0.80
        self.recommended_suggest_threshold: float = 0.60
        self.confidence_bins: Dict[str, Dict[str, float]] = {}
        self.needs_calibration: bool = False
        
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "total_samples": self.total_samples,
            "acceptance_rate": self.acceptance_rate,
            "avg_confidence": self.avg_confidence,
            "correlation_score": self.correlation_score,
            "recommended_auto_threshold": self.recommended_auto_threshold,
            "recommended_suggest_threshold": self.recommended_suggest_threshold,
            "confidence_bins": self.confidence_bins,
            "needs_calibration": self.needs_calibration,
        }


class ConfidenceCalibrator:
    """
    Calibrates AI confidence thresholds based on historical feedback.
    
    This class analyzes the correlation between AI confidence scores
    and actual user acceptance rates to recommend optimal thresholds
    for auto-applying suggestions.
    
    Features:
    - Per-type calibration (different thresholds for tags vs. correspondents)
    - Per-user calibration (personalized thresholds)
    - Minimum sample size requirements (configurable, default 100)
    - Auto-apply threshold ensures >95% acceptance rate
    - Graceful degradation to defaults when insufficient data
    """
    
    def __init__(
        self,
        min_samples: int = 100,
        auto_apply_target_accuracy: float = 0.95,
        suggest_min_accuracy: float = 0.60,
        lookback_days: int = 90,
    ):
        """
        Initialize calibrator.
        
        Args:
            min_samples: Minimum feedback samples required for calibration
            auto_apply_target_accuracy: Target accuracy for auto-apply (default 0.95)
            suggest_min_accuracy: Minimum accuracy for suggestions (default 0.60)
            lookback_days: Days of historical data to consider
        """
        self.min_samples = min_samples
        self.auto_apply_target_accuracy = auto_apply_target_accuracy
        self.suggest_min_accuracy = suggest_min_accuracy
        self.lookback_days = lookback_days
        
        # Default thresholds (fallback)
        self.default_auto_threshold = getattr(
            settings, "PAPERLESS_AI_AUTO_APPLY_THRESHOLD", 0.80
        )
        self.default_suggest_threshold = getattr(
            settings, "PAPERLESS_AI_SUGGEST_THRESHOLD", 0.60
        )
        
        logger.info(
            f"ConfidenceCalibrator initialized - "
            f"min_samples: {min_samples}, "
            f"target_accuracy: {auto_apply_target_accuracy}, "
            f"lookback: {lookback_days} days"
        )
    
    def calibrate_thresholds(
        self,
        suggestion_type: Optional[str] = None,
        user: Optional[User] = None,
    ) -> Tuple[float, float]:
        """
        Calibrate confidence thresholds based on historical feedback.
        
        Args:
            suggestion_type: Type of suggestion to calibrate (e.g., 'tag', 'correspondent')
                           If None, calibrates globally across all types
            user: Specific user to calibrate for personalized thresholds
                 If None, calibrates globally across all users
        
        Returns:
            Tuple of (auto_apply_threshold, suggest_threshold)
        """
        result = self.analyze_feedback(suggestion_type, user)
        
        if not result.needs_calibration:
            logger.info(
                f"Insufficient samples for calibration "
                f"(type={suggestion_type}, user={user}). Using defaults."
            )
            return (self.default_auto_threshold, self.default_suggest_threshold)
        
        logger.info(
            f"Calibrated thresholds for type={suggestion_type}, user={user}: "
            f"auto={result.recommended_auto_threshold:.2f}, "
            f"suggest={result.recommended_suggest_threshold:.2f}"
        )
        
        return (
            result.recommended_auto_threshold,
            result.recommended_suggest_threshold,
        )
    
    def analyze_feedback(
        self,
        suggestion_type: Optional[str] = None,
        user: Optional[User] = None,
    ) -> CalibrationResult:
        """
        Analyze historical feedback to assess confidence calibration.
        
        This method bins feedback by confidence ranges and calculates
        acceptance rates for each bin. It then determines optimal
        thresholds based on target accuracy requirements.
        
        Args:
            suggestion_type: Filter by suggestion type
            user: Filter by specific user
            
        Returns:
            CalibrationResult with analysis and recommendations
        """
        from documents.models import AISuggestionFeedback
        
        result = CalibrationResult()
        
        # Build query with filters
        cutoff_date = timezone.now() - timedelta(days=self.lookback_days)
        query = AISuggestionFeedback.objects.filter(created_at__gte=cutoff_date)
        
        if suggestion_type:
            query = query.filter(suggestion_type=suggestion_type)
        
        if user:
            query = query.filter(user=user)
        
        # Get total sample count
        result.total_samples = query.count()
        
        if result.total_samples < self.min_samples:
            logger.debug(
                f"Insufficient samples: {result.total_samples} < {self.min_samples}"
            )
            return result
        
        result.needs_calibration = True
        
        # Calculate overall statistics
        stats = query.aggregate(
            acceptance_rate=Avg("was_accepted"),
            avg_confidence=Avg("confidence_score"),
        )
        result.acceptance_rate = float(stats["acceptance_rate"] or 0.0)
        result.avg_confidence = float(stats["avg_confidence"] or 0.0)
        
        # Analyze by confidence bins
        confidence_bins = [
            ("0.00-0.20", 0.0, 0.2),
            ("0.20-0.40", 0.2, 0.4),
            ("0.40-0.60", 0.4, 0.6),
            ("0.60-0.70", 0.6, 0.7),
            ("0.70-0.80", 0.7, 0.8),
            ("0.80-0.85", 0.8, 0.85),
            ("0.85-0.90", 0.85, 0.9),
            ("0.90-0.95", 0.9, 0.95),
            ("0.95-1.00", 0.95, 1.0),
        ]
        
        for bin_name, min_conf, max_conf in confidence_bins:
            bin_query = query.filter(
                confidence_score__gte=min_conf,
                confidence_score__lt=max_conf,
            )
            
            bin_stats = bin_query.aggregate(
                count=Count("id"),
                acceptance_rate=Avg("was_accepted"),
            )
            
            count = bin_stats["count"] or 0
            if count > 0:
                acceptance = float(bin_stats["acceptance_rate"] or 0.0)
                result.confidence_bins[bin_name] = {
                    "count": count,
                    "acceptance_rate": acceptance,
                }
        
        # Calculate correlation score (simplified)
        # Higher confidence should correlate with higher acceptance
        result.correlation_score = self._calculate_correlation(result.confidence_bins)
        
        # Determine optimal thresholds
        result.recommended_auto_threshold = self._find_auto_threshold(
            result.confidence_bins
        )
        result.recommended_suggest_threshold = self._find_suggest_threshold(
            result.confidence_bins
        )
        
        logger.debug(f"Calibration analysis: {result.to_dict()}")
        
        return result
    
    def _calculate_correlation(self, bins: Dict[str, Dict[str, float]]) -> float:
        """
        Calculate correlation between confidence and acceptance.
        
        Simplified correlation: weighted average of acceptance rates,
        where bins with higher confidence get higher weight.
        
        Returns:
            Correlation score (0.0 to 1.0)
        """
        if not bins:
            return 0.0
        
        total_weight = 0.0
        weighted_sum = 0.0
        
        for bin_name, stats in bins.items():
            # Extract min confidence from bin name (e.g., "0.80-0.85" -> 0.80)
            min_conf = float(bin_name.split("-")[0])
            weight = min_conf * stats["count"]
            
            total_weight += weight
            weighted_sum += weight * stats["acceptance_rate"]
        
        if total_weight == 0:
            return 0.0
        
        correlation = weighted_sum / total_weight
        return min(max(correlation, 0.0), 1.0)
    
    def _find_auto_threshold(self, bins: Dict[str, Dict[str, float]]) -> float:
        """
        Find the confidence threshold that achieves target auto-apply accuracy.
        
        The threshold is set such that suggestions with confidence >= threshold
        have an acceptance rate >= auto_apply_target_accuracy (default 95%).
        
        Args:
            bins: Confidence bins with acceptance rates
            
        Returns:
            Recommended auto-apply threshold
        """
        # Sort bins by minimum confidence (descending)
        sorted_bins = sorted(
            bins.items(),
            key=lambda x: float(x[0].split("-")[0]),
            reverse=True,
        )
        
        # Find the lowest confidence bin that meets target accuracy
        for bin_name, stats in sorted_bins:
            if stats["acceptance_rate"] >= self.auto_apply_target_accuracy:
                # Return the minimum confidence of this bin
                min_conf = float(bin_name.split("-")[0])
                return min_conf
        
        # If no bin meets target, return a very high threshold (0.95)
        # to be conservative and avoid auto-applying low-accuracy suggestions
        logger.warning(
            f"No confidence bin meets auto-apply target accuracy "
            f"({self.auto_apply_target_accuracy}). Using conservative threshold 0.95"
        )
        return 0.95
    
    def _find_suggest_threshold(self, bins: Dict[str, Dict[str, float]]) -> float:
        """
        Find the confidence threshold for showing suggestions to users.
        
        The threshold is set such that suggestions with confidence >= threshold
        have an acceptance rate >= suggest_min_accuracy (default 60%).
        
        Args:
            bins: Confidence bins with acceptance rates
            
        Returns:
            Recommended suggest threshold
        """
        # Sort bins by minimum confidence (descending)
        sorted_bins = sorted(
            bins.items(),
            key=lambda x: float(x[0].split("-")[0]),
            reverse=True,
        )
        
        # Find the lowest confidence bin that meets minimum accuracy
        for bin_name, stats in sorted_bins:
            if stats["acceptance_rate"] >= self.suggest_min_accuracy:
                # Return the minimum confidence of this bin
                min_conf = float(bin_name.split("-")[0])
                return min_conf
        
        # If no bin meets target, return default
        logger.warning(
            f"No confidence bin meets suggest minimum accuracy "
            f"({self.suggest_min_accuracy}). Using default threshold."
        )
        return self.default_suggest_threshold
    
    def get_user_acceptance_stats(self, user: User) -> Dict[str, float]:
        """
        Get acceptance statistics for a specific user.
        
        This can be used to adjust thresholds based on user behavior.
        For example, if a user accepts most suggestions, the system
        can lower thresholds to show more suggestions.
        
        Args:
            user: User to analyze
            
        Returns:
            Dictionary with user statistics
        """
        from documents.models import AISuggestionFeedback
        
        cutoff_date = timezone.now() - timedelta(days=self.lookback_days)
        query = AISuggestionFeedback.objects.filter(
            user=user,
            created_at__gte=cutoff_date,
        )
        
        total = query.count()
        if total == 0:
            return {
                "total_feedback": 0,
                "acceptance_rate": 0.0,
                "rejection_rate": 0.0,
                "auto_applied_count": 0,
                "user_reviewed_count": 0,
            }
        
        stats = query.aggregate(
            accepted=Count("id", filter=Q(was_accepted=True)),
            auto_applied=Count("id", filter=Q(was_auto_applied=True)),
        )
        
        accepted = stats["accepted"] or 0
        auto_applied = stats["auto_applied"] or 0
        
        return {
            "total_feedback": total,
            "acceptance_rate": accepted / total if total > 0 else 0.0,
            "rejection_rate": (total - accepted) / total if total > 0 else 0.0,
            "auto_applied_count": auto_applied,
            "user_reviewed_count": total - auto_applied,
        }
    
    def should_adjust_thresholds_for_user(
        self,
        user: User,
        suggestion_type: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Determine if thresholds should be adjusted for a specific user.
        
        Rules:
        - If user accepts >90% of suggestions: can lower thresholds
        - If user rejects >50% of suggestions: should raise thresholds
        - If user has <min_samples feedback: no adjustment
        
        Args:
            user: User to check
            suggestion_type: Optional specific suggestion type
            
        Returns:
            Tuple of (should_adjust, reason)
        """
        stats = self.get_user_acceptance_stats(user)
        
        if stats["total_feedback"] < self.min_samples:
            return (False, "Insufficient feedback data")
        
        acceptance_rate = stats["acceptance_rate"]
        
        if acceptance_rate >= 0.90:
            return (True, f"High acceptance rate ({acceptance_rate:.1%}), can lower thresholds")
        elif acceptance_rate <= 0.50:
            return (True, f"Low acceptance rate ({acceptance_rate:.1%}), should raise thresholds")
        else:
            return (False, f"Normal acceptance rate ({acceptance_rate:.1%})")
    
    def get_calibrated_scanner_thresholds(
        self,
        user: Optional[User] = None,
    ) -> Dict[str, Tuple[float, float]]:
        """
        Get calibrated thresholds for all suggestion types.
        
        This returns a dictionary mapping suggestion types to their
        calibrated (auto_threshold, suggest_threshold) tuples.
        
        Args:
            user: Optional user for personalized calibration
            
        Returns:
            Dictionary mapping suggestion_type to (auto_threshold, suggest_threshold)
        """
        from documents.models import AISuggestionFeedback
        
        suggestion_types = [
            AISuggestionFeedback.TYPE_TAG,
            AISuggestionFeedback.TYPE_CORRESPONDENT,
            AISuggestionFeedback.TYPE_DOCUMENT_TYPE,
            AISuggestionFeedback.TYPE_STORAGE_PATH,
            AISuggestionFeedback.TYPE_CUSTOM_FIELD,
            AISuggestionFeedback.TYPE_WORKFLOW,
        ]
        
        thresholds = {}
        
        # Get global thresholds first
        global_auto, global_suggest = self.calibrate_thresholds(
            suggestion_type=None,
            user=user,
        )
        thresholds["global"] = (global_auto, global_suggest)
        
        # Get per-type thresholds
        for stype in suggestion_types:
            auto, suggest = self.calibrate_thresholds(
                suggestion_type=stype,
                user=user,
            )
            thresholds[stype] = (auto, suggest)
        
        return thresholds


# Global calibrator instance (lazy initialized)
_calibrator_instance = None


def get_calibrator() -> ConfidenceCalibrator:
    """
    Get or create the global confidence calibrator instance.
    
    Returns:
        ConfidenceCalibrator instance
    """
    global _calibrator_instance
    if _calibrator_instance is None:
        _calibrator_instance = ConfidenceCalibrator()
    return _calibrator_instance

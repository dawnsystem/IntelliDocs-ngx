"""
Active Learning Loop for IntelliDocs-ngx ML/AI System.

This module implements continuous learning based on user feedback,
enabling the ML models to improve over time through active learning.

Key Features:
- Track user acceptance/rejection of AI suggestions
- Identify difficult cases (low confidence predictions)
- Schedule periodic retraining with new data
- Monitor accuracy metrics over time
- Provide performance dashboard data

Requirements (from Issue 6.2):
- Tracking de sugerencias aceptadas/rechazadas
- Identificar casos difíciles (low confidence)
- Re-training periódico con nuevos datos
- Métricas de mejora de accuracy over time
- Dashboard de ML performance
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone
from django.core.cache import cache

if TYPE_CHECKING:
    from documents.models import Document, User

logger = logging.getLogger("paperless.ml.active_learning")


class SuggestionFeedback(models.Model):
    """
    Tracks user feedback on AI suggestions for active learning.
    
    This model stores every AI suggestion and whether it was accepted,
    rejected, or modified by the user. This data is crucial for:
    - Measuring model accuracy
    - Identifying difficult cases
    - Retraining models with improved data
    """
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    # Document and user
    document = models.ForeignKey(
        'documents.Document',
        on_delete=models.CASCADE,
        related_name='ai_feedbacks',
        help_text="Document that received AI suggestions",
    )
    user = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ai_feedbacks',
        help_text="User who provided feedback",
    )
    
    # Suggestion details
    SUGGESTION_TYPE_TAG = 'tag'
    SUGGESTION_TYPE_CORRESPONDENT = 'correspondent'
    SUGGESTION_TYPE_DOCUMENT_TYPE = 'document_type'
    SUGGESTION_TYPE_STORAGE_PATH = 'storage_path'
    SUGGESTION_TYPE_CUSTOM_FIELD = 'custom_field'
    SUGGESTION_TYPE_WORKFLOW = 'workflow'
    SUGGESTION_TYPE_TITLE = 'title'
    
    SUGGESTION_TYPES = [
        (SUGGESTION_TYPE_TAG, 'Tag'),
        (SUGGESTION_TYPE_CORRESPONDENT, 'Correspondent'),
        (SUGGESTION_TYPE_DOCUMENT_TYPE, 'Document Type'),
        (SUGGESTION_TYPE_STORAGE_PATH, 'Storage Path'),
        (SUGGESTION_TYPE_CUSTOM_FIELD, 'Custom Field'),
        (SUGGESTION_TYPE_WORKFLOW, 'Workflow'),
        (SUGGESTION_TYPE_TITLE, 'Title'),
    ]
    
    suggestion_type = models.CharField(
        max_length=20,
        choices=SUGGESTION_TYPES,
        db_index=True,
    )
    
    suggested_value_id = models.IntegerField(
        null=True,
        blank=True,
        help_text="ID of suggested object (for FK suggestions)",
    )
    suggested_value_text = models.TextField(
        blank=True,
        help_text="Text value for non-FK suggestions",
    )
    
    confidence = models.FloatField(
        help_text="AI confidence score (0.0 - 1.0)",
    )
    
    # User action
    ACTION_ACCEPTED = 'accepted'
    ACTION_REJECTED = 'rejected'
    ACTION_MODIFIED = 'modified'
    ACTION_IGNORED = 'ignored'
    
    ACTIONS = [
        (ACTION_ACCEPTED, 'Accepted'),
        (ACTION_REJECTED, 'Rejected'),
        (ACTION_MODIFIED, 'Modified'),
        (ACTION_IGNORED, 'Ignored'),
    ]
    
    user_action = models.CharField(
        max_length=20,
        choices=ACTIONS,
        db_index=True,
    )
    
    actual_value_id = models.IntegerField(
        null=True,
        blank=True,
        help_text="ID of actual chosen value (if different from suggestion)",
    )
    actual_value_text = models.TextField(
        blank=True,
        help_text="Actual text value chosen by user",
    )
    
    # Context for analysis
    document_text_sample = models.TextField(
        blank=True,
        help_text="Sample of document text for retraining",
    )
    
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional metadata (entities extracted, etc.)",
    )
    
    # Retraining tracking
    used_for_training = models.BooleanField(
        default=False,
        help_text="Whether this feedback was used in retraining",
    )
    training_session_id = models.CharField(
        max_length=50,
        blank=True,
        help_text="ID of training session that used this feedback",
    )
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['suggestion_type', 'user_action']),
            models.Index(fields=['confidence']),
            models.Index(fields=['created_at', 'suggestion_type']),
            models.Index(fields=['used_for_training']),
        ]
        verbose_name = "AI Suggestion Feedback"
        verbose_name_plural = "AI Suggestion Feedbacks"
    
    def __str__(self):
        return (f"{self.suggestion_type} suggestion for doc {self.document_id}: "
                f"{self.user_action} (confidence: {self.confidence:.2f})")
    
    @property
    def is_correct(self) -> bool:
        """Check if AI suggestion was correct (accepted by user)."""
        return self.user_action == self.ACTION_ACCEPTED


class MLPerformanceMetric(models.Model):
    """
    Stores ML performance metrics over time for tracking improvements.
    
    Metrics are calculated periodically (daily/weekly) to track:
    - Accuracy per suggestion type
    - Confidence calibration
    - Model improvement over time
    """
    
    # Timestamp
    calculated_at = models.DateTimeField(auto_now_add=True, db_index=True)
    period_start = models.DateTimeField(db_index=True)
    period_end = models.DateTimeField(db_index=True)
    
    # Metric type
    suggestion_type = models.CharField(
        max_length=20,
        choices=SuggestionFeedback.SUGGESTION_TYPES,
        db_index=True,
    )
    
    # Performance metrics
    total_suggestions = models.IntegerField(default=0)
    accepted_count = models.IntegerField(default=0)
    rejected_count = models.IntegerField(default=0)
    modified_count = models.IntegerField(default=0)
    ignored_count = models.IntegerField(default=0)
    
    # Calculated metrics
    accuracy = models.FloatField(
        help_text="Acceptance rate: accepted / total",
    )
    precision = models.FloatField(
        null=True,
        blank=True,
        help_text="Precision considering modified as incorrect",
    )
    
    # Confidence analysis
    avg_confidence = models.FloatField(
        help_text="Average confidence score",
    )
    avg_confidence_accepted = models.FloatField(
        null=True,
        blank=True,
        help_text="Average confidence for accepted suggestions",
    )
    avg_confidence_rejected = models.FloatField(
        null=True,
        blank=True,
        help_text="Average confidence for rejected suggestions",
    )
    
    # Difficult cases
    low_confidence_count = models.IntegerField(
        default=0,
        help_text="Count of suggestions with confidence < 0.7",
    )
    high_confidence_errors = models.IntegerField(
        default=0,
        help_text="Count of rejected suggestions with confidence > 0.8",
    )
    
    # Additional metadata
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional metric data",
    )
    
    class Meta:
        ordering = ['-calculated_at']
        indexes = [
            models.Index(fields=['suggestion_type', 'calculated_at']),
            models.Index(fields=['period_start', 'period_end']),
        ]
        unique_together = [['period_start', 'period_end', 'suggestion_type']]
        verbose_name = "ML Performance Metric"
        verbose_name_plural = "ML Performance Metrics"
    
    def __str__(self):
        return (f"{self.suggestion_type} metrics for "
                f"{self.period_start.date()} - {self.period_end.date()}: "
                f"accuracy={self.accuracy:.2%}")


class RetrainingSession(models.Model):
    """
    Tracks ML model retraining sessions.
    
    Each time models are retrained with new feedback data,
    a session record is created to track:
    - What data was used
    - Performance before/after
    - Training parameters
    """
    
    # Timestamps
    started_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Session details
    session_id = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
    )
    
    model_type = models.CharField(
        max_length=50,
        help_text="Type of model being retrained (classifier, ner, etc.)",
    )
    
    # Training data
    training_samples_count = models.IntegerField(default=0)
    feedback_items_used = models.IntegerField(default=0)
    
    data_period_start = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Start of feedback data period used",
    )
    data_period_end = models.DateTimeField(
        null=True,
        blank=True,
        help_text="End of feedback data period used",
    )
    
    # Performance
    STATUS_RUNNING = 'running'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'
    STATUS_CANCELLED = 'cancelled'
    
    STATUS_CHOICES = [
        (STATUS_RUNNING, 'Running'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_RUNNING,
    )
    
    # Metrics before/after
    accuracy_before = models.FloatField(null=True, blank=True)
    accuracy_after = models.FloatField(null=True, blank=True)
    
    # Training details
    training_config = models.JSONField(
        default=dict,
        help_text="Training parameters and configuration",
    )
    
    training_metrics = models.JSONField(
        default=dict,
        help_text="Detailed training metrics (loss, validation, etc.)",
    )
    
    error_message = models.TextField(
        blank=True,
        help_text="Error message if training failed",
    )
    
    # Model artifacts
    model_path = models.CharField(
        max_length=500,
        blank=True,
        help_text="Path to saved model",
    )
    
    class Meta:
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['model_type', 'started_at']),
            models.Index(fields=['status']),
        ]
        verbose_name = "Retraining Session"
        verbose_name_plural = "Retraining Sessions"
    
    def __str__(self):
        return f"{self.model_type} retraining {self.session_id} - {self.status}"
    
    @property
    def duration(self) -> Optional[timedelta]:
        """Calculate training duration."""
        if self.completed_at:
            return self.completed_at - self.started_at
        return None
    
    @property
    def improvement(self) -> Optional[float]:
        """Calculate accuracy improvement."""
        if self.accuracy_before is not None and self.accuracy_after is not None:
            return self.accuracy_after - self.accuracy_before
        return None


class FeedbackTracker:
    """
    Service class for tracking and analyzing user feedback on AI suggestions.
    
    Main responsibilities:
    - Record user decisions on suggestions
    - Provide feedback statistics
    - Identify patterns in user corrections
    """
    
    def __init__(self):
        """Initialize feedback tracker."""
        self.cache_timeout = getattr(settings, 'PAPERLESS_ML_CACHE_TIMEOUT', 3600)
    
    def record_feedback(
        self,
        document: Document,
        suggestion_type: str,
        suggested_value_id: Optional[int],
        suggested_value_text: str,
        confidence: float,
        user_action: str,
        actual_value_id: Optional[int] = None,
        actual_value_text: str = "",
        user: Optional[User] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SuggestionFeedback:
        """
        Record user feedback on an AI suggestion.
        
        Args:
            document: Document that received the suggestion
            suggestion_type: Type of suggestion (tag, correspondent, etc.)
            suggested_value_id: ID of suggested value
            suggested_value_text: Text of suggested value
            confidence: AI confidence score
            user_action: User action (accepted, rejected, modified, ignored)
            actual_value_id: Actual value chosen (if different)
            actual_value_text: Actual text chosen
            user: User who provided feedback
            metadata: Additional metadata
            
        Returns:
            Created SuggestionFeedback instance
        """
        # Get document text sample for retraining
        document_text_sample = ""
        if hasattr(document, 'content'):
            document_text_sample = document.content[:1000]  # First 1000 chars
        
        feedback = SuggestionFeedback.objects.create(
            document=document,
            user=user,
            suggestion_type=suggestion_type,
            suggested_value_id=suggested_value_id,
            suggested_value_text=suggested_value_text,
            confidence=confidence,
            user_action=user_action,
            actual_value_id=actual_value_id,
            actual_value_text=actual_value_text,
            document_text_sample=document_text_sample,
            metadata=metadata or {},
        )
        
        logger.info(
            f"Recorded feedback: {suggestion_type} suggestion "
            f"for doc {document.id} was {user_action}"
        )
        
        # Invalidate cached metrics
        cache.delete(f"ml_metrics_{suggestion_type}_recent")
        
        return feedback
    
    def get_acceptance_rate(
        self,
        suggestion_type: Optional[str] = None,
        days: int = 30,
    ) -> float:
        """
        Calculate acceptance rate for suggestions.
        
        Args:
            suggestion_type: Filter by suggestion type (None for all)
            days: Number of days to look back
            
        Returns:
            Acceptance rate (0.0 - 1.0)
        """
        since = timezone.now() - timedelta(days=days)
        
        qs = SuggestionFeedback.objects.filter(created_at__gte=since)
        if suggestion_type:
            qs = qs.filter(suggestion_type=suggestion_type)
        
        total = qs.count()
        if total == 0:
            return 0.0
        
        accepted = qs.filter(user_action=SuggestionFeedback.ACTION_ACCEPTED).count()
        return accepted / total
    
    def get_recent_feedbacks(
        self,
        suggestion_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[SuggestionFeedback]:
        """
        Get recent feedback entries.
        
        Args:
            suggestion_type: Filter by suggestion type
            limit: Maximum number of entries
            
        Returns:
            List of SuggestionFeedback instances
        """
        qs = SuggestionFeedback.objects.select_related('document', 'user')
        
        if suggestion_type:
            qs = qs.filter(suggestion_type=suggestion_type)
        
        return list(qs[:limit])


class CaseDifficulty:
    """
    Analyzer for identifying difficult cases requiring manual review or retraining.
    
    Identifies:
    - Low confidence predictions
    - High confidence errors
    - Frequent corrections
    - Ambiguous cases
    """
    
    LOW_CONFIDENCE_THRESHOLD = 0.7
    HIGH_CONFIDENCE_THRESHOLD = 0.8
    
    def __init__(self):
        """Initialize case difficulty analyzer."""
        pass
    
    def identify_difficult_cases(
        self,
        suggestion_type: Optional[str] = None,
        days: int = 30,
    ) -> Dict[str, Any]:
        """
        Identify difficult cases for manual review.
        
        Args:
            suggestion_type: Filter by suggestion type
            days: Number of days to analyze
            
        Returns:
            Dictionary with difficult cases analysis
        """
        since = timezone.now() - timedelta(days=days)
        
        qs = SuggestionFeedback.objects.filter(created_at__gte=since)
        if suggestion_type:
            qs = qs.filter(suggestion_type=suggestion_type)
        
        # Low confidence cases
        low_confidence = qs.filter(
            confidence__lt=self.LOW_CONFIDENCE_THRESHOLD
        )
        
        # High confidence errors
        high_conf_errors = qs.filter(
            confidence__gte=self.HIGH_CONFIDENCE_THRESHOLD,
            user_action__in=[
                SuggestionFeedback.ACTION_REJECTED,
                SuggestionFeedback.ACTION_MODIFIED,
            ],
        )
        
        # Cases with modifications
        modified_cases = qs.filter(
            user_action=SuggestionFeedback.ACTION_MODIFIED
        )
        
        return {
            'low_confidence_count': low_confidence.count(),
            'low_confidence_cases': list(low_confidence[:10]),
            'high_confidence_errors_count': high_conf_errors.count(),
            'high_confidence_errors': list(high_conf_errors[:10]),
            'modified_cases_count': modified_cases.count(),
            'modified_cases': list(modified_cases[:10]),
            'total_cases': qs.count(),
        }
    
    def get_confidence_calibration(
        self,
        suggestion_type: Optional[str] = None,
        days: int = 30,
    ) -> Dict[str, Any]:
        """
        Analyze confidence calibration (do high confidence predictions perform better?).
        
        Args:
            suggestion_type: Filter by suggestion type
            days: Number of days to analyze
            
        Returns:
            Dictionary with calibration analysis
        """
        since = timezone.now() - timedelta(days=days)
        
        qs = SuggestionFeedback.objects.filter(created_at__gte=since)
        if suggestion_type:
            qs = qs.filter(suggestion_type=suggestion_type)
        
        # Bin confidence scores
        bins = [
            (0.5, 0.6, "50-60%"),
            (0.6, 0.7, "60-70%"),
            (0.7, 0.8, "70-80%"),
            (0.8, 0.9, "80-90%"),
            (0.9, 1.0, "90-100%"),
        ]
        
        calibration = []
        for min_conf, max_conf, label in bins:
            bin_qs = qs.filter(
                confidence__gte=min_conf,
                confidence__lt=max_conf,
            )
            total = bin_qs.count()
            if total > 0:
                accepted = bin_qs.filter(
                    user_action=SuggestionFeedback.ACTION_ACCEPTED
                ).count()
                accuracy = accepted / total
                
                calibration.append({
                    'confidence_range': label,
                    'total': total,
                    'accepted': accepted,
                    'accuracy': accuracy,
                })
        
        return {
            'calibration': calibration,
            'suggestion_type': suggestion_type or 'all',
        }


class RetrainingScheduler:
    """
    Manages periodic retraining of ML models with new feedback data.
    
    Responsibilities:
    - Determine when retraining is needed
    - Prepare training data from feedback
    - Execute retraining
    - Evaluate improvements
    """
    
    MIN_FEEDBACK_COUNT = 100  # Minimum feedback items for retraining
    
    def __init__(self):
        """Initialize retraining scheduler."""
        self.enabled = getattr(settings, 'PAPERLESS_ENABLE_ML_RETRAINING', True)
    
    def should_retrain(
        self,
        model_type: str,
        suggestion_type: str,
    ) -> bool:
        """
        Determine if a model should be retrained.
        
        Args:
            model_type: Type of model (classifier, ner, etc.)
            suggestion_type: Type of suggestions
            
        Returns:
            True if retraining is recommended
        """
        if not self.enabled:
            return False
        
        # Check last retraining time
        last_session = RetrainingSession.objects.filter(
            model_type=model_type,
            status=RetrainingSession.STATUS_COMPLETED,
        ).first()
        
        if last_session:
            days_since = (timezone.now() - last_session.completed_at).days
            min_days = getattr(settings, 'PAPERLESS_ML_RETRAINING_MIN_DAYS', 7)
            
            if days_since < min_days:
                logger.debug(f"Too soon to retrain {model_type} (only {days_since} days)")
                return False
        
        # Check available feedback
        unused_feedback = SuggestionFeedback.objects.filter(
            suggestion_type=suggestion_type,
            used_for_training=False,
        ).count()
        
        if unused_feedback < self.MIN_FEEDBACK_COUNT:
            logger.debug(
                f"Not enough feedback for {model_type}: "
                f"{unused_feedback} < {self.MIN_FEEDBACK_COUNT}"
            )
            return False
        
        logger.info(
            f"Retraining recommended for {model_type}: "
            f"{unused_feedback} feedback items available"
        )
        return True
    
    def prepare_training_data(
        self,
        suggestion_type: str,
        max_samples: Optional[int] = None,
    ) -> Tuple[List[str], List[Any], List[int]]:
        """
        Prepare training data from feedback.
        
        Args:
            suggestion_type: Type of suggestions to use
            max_samples: Maximum number of samples (None for all)
            
        Returns:
            Tuple of (texts, labels, feedback_ids)
        """
        # Get feedback with accepted or modified actions
        feedbacks = SuggestionFeedback.objects.filter(
            suggestion_type=suggestion_type,
            used_for_training=False,
            user_action__in=[
                SuggestionFeedback.ACTION_ACCEPTED,
                SuggestionFeedback.ACTION_MODIFIED,
            ],
        ).select_related('document')
        
        if max_samples:
            feedbacks = feedbacks[:max_samples]
        
        texts = []
        labels = []
        feedback_ids = []
        
        for feedback in feedbacks:
            if feedback.document_text_sample:
                texts.append(feedback.document_text_sample)
                
                # Use actual value if modified, otherwise use suggested value
                if feedback.user_action == SuggestionFeedback.ACTION_MODIFIED:
                    label = feedback.actual_value_id or feedback.actual_value_text
                else:
                    label = feedback.suggested_value_id or feedback.suggested_value_text
                
                labels.append(label)
                feedback_ids.append(feedback.id)
        
        logger.info(
            f"Prepared {len(texts)} training samples for {suggestion_type}"
        )
        
        return texts, labels, feedback_ids
    
    def create_retraining_session(
        self,
        model_type: str,
        training_config: Optional[Dict[str, Any]] = None,
    ) -> RetrainingSession:
        """
        Create a new retraining session.
        
        Args:
            model_type: Type of model being retrained
            training_config: Training configuration
            
        Returns:
            Created RetrainingSession instance
        """
        session_id = f"{model_type}_{timezone.now().strftime('%Y%m%d_%H%M%S')}"
        
        session = RetrainingSession.objects.create(
            session_id=session_id,
            model_type=model_type,
            training_config=training_config or {},
        )
        
        logger.info(f"Created retraining session: {session_id}")
        
        return session
    
    def mark_feedback_used(
        self,
        feedback_ids: List[int],
        session_id: str,
    ) -> int:
        """
        Mark feedback as used in training.
        
        Args:
            feedback_ids: List of feedback IDs
            session_id: Training session ID
            
        Returns:
            Number of feedbacks marked
        """
        count = SuggestionFeedback.objects.filter(
            id__in=feedback_ids
        ).update(
            used_for_training=True,
            training_session_id=session_id,
        )
        
        logger.info(
            f"Marked {count} feedback items as used in session {session_id}"
        )
        
        return count


class ActiveLearningMetrics:
    """
    Service for calculating and tracking ML performance metrics over time.
    
    Tracks:
    - Accuracy trends
    - Confidence calibration
    - Model improvements
    - User satisfaction
    """
    
    def __init__(self):
        """Initialize metrics calculator."""
        pass
    
    def calculate_period_metrics(
        self,
        period_start: datetime,
        period_end: datetime,
        suggestion_type: Optional[str] = None,
    ) -> List[MLPerformanceMetric]:
        """
        Calculate metrics for a time period.
        
        Args:
            period_start: Start of period
            period_end: End of period
            suggestion_type: Filter by suggestion type (None for all)
            
        Returns:
            List of created MLPerformanceMetric instances
        """
        suggestion_types = [suggestion_type] if suggestion_type else [
            t[0] for t in SuggestionFeedback.SUGGESTION_TYPES
        ]
        
        metrics = []
        
        for stype in suggestion_types:
            metric = self._calculate_type_metrics(
                stype, period_start, period_end
            )
            if metric:
                metrics.append(metric)
        
        return metrics
    
    def _calculate_type_metrics(
        self,
        suggestion_type: str,
        period_start: datetime,
        period_end: datetime,
    ) -> Optional[MLPerformanceMetric]:
        """Calculate metrics for a specific suggestion type."""
        feedbacks = SuggestionFeedback.objects.filter(
            suggestion_type=suggestion_type,
            created_at__gte=period_start,
            created_at__lt=period_end,
        )
        
        total = feedbacks.count()
        if total == 0:
            return None
        
        # Count actions
        accepted = feedbacks.filter(
            user_action=SuggestionFeedback.ACTION_ACCEPTED
        ).count()
        rejected = feedbacks.filter(
            user_action=SuggestionFeedback.ACTION_REJECTED
        ).count()
        modified = feedbacks.filter(
            user_action=SuggestionFeedback.ACTION_MODIFIED
        ).count()
        ignored = feedbacks.filter(
            user_action=SuggestionFeedback.ACTION_IGNORED
        ).count()
        
        # Calculate metrics
        accuracy = accepted / total if total > 0 else 0.0
        precision = accepted / (accepted + modified) if (accepted + modified) > 0 else 0.0
        
        # Confidence analysis
        from django.db.models import Avg
        
        avg_confidence = feedbacks.aggregate(
            avg=Avg('confidence')
        )['avg'] or 0.0
        
        avg_conf_accepted = feedbacks.filter(
            user_action=SuggestionFeedback.ACTION_ACCEPTED
        ).aggregate(avg=Avg('confidence'))['avg']
        
        avg_conf_rejected = feedbacks.filter(
            user_action=SuggestionFeedback.ACTION_REJECTED
        ).aggregate(avg=Avg('confidence'))['avg']
        
        # Difficult cases
        low_confidence = feedbacks.filter(confidence__lt=0.7).count()
        high_conf_errors = feedbacks.filter(
            confidence__gte=0.8,
            user_action__in=[
                SuggestionFeedback.ACTION_REJECTED,
                SuggestionFeedback.ACTION_MODIFIED,
            ],
        ).count()
        
        # Create metric
        metric = MLPerformanceMetric.objects.create(
            period_start=period_start,
            period_end=period_end,
            suggestion_type=suggestion_type,
            total_suggestions=total,
            accepted_count=accepted,
            rejected_count=rejected,
            modified_count=modified,
            ignored_count=ignored,
            accuracy=accuracy,
            precision=precision,
            avg_confidence=avg_confidence,
            avg_confidence_accepted=avg_conf_accepted,
            avg_confidence_rejected=avg_conf_rejected,
            low_confidence_count=low_confidence,
            high_confidence_errors=high_conf_errors,
        )
        
        logger.info(
            f"Calculated metrics for {suggestion_type}: "
            f"accuracy={accuracy:.2%}, precision={precision:.2%}"
        )
        
        return metric
    
    def get_accuracy_trend(
        self,
        suggestion_type: str,
        days: int = 90,
    ) -> List[Dict[str, Any]]:
        """
        Get accuracy trend over time.
        
        Args:
            suggestion_type: Type of suggestions
            days: Number of days to look back
            
        Returns:
            List of trend data points
        """
        since = timezone.now() - timedelta(days=days)
        
        metrics = MLPerformanceMetric.objects.filter(
            suggestion_type=suggestion_type,
            period_start__gte=since,
        ).order_by('period_start')
        
        trend = []
        for metric in metrics:
            trend.append({
                'date': metric.period_start.date().isoformat(),
                'accuracy': metric.accuracy,
                'total_suggestions': metric.total_suggestions,
                'avg_confidence': metric.avg_confidence,
            })
        
        return trend


class MLPerformanceDashboard:
    """
    Service for generating ML performance dashboard data.
    
    Provides:
    - Overall performance summary
    - Per-type metrics
    - Trends over time
    - Retraining recommendations
    """
    
    def __init__(self):
        """Initialize dashboard service."""
        self.feedback_tracker = FeedbackTracker()
        self.case_difficulty = CaseDifficulty()
        self.metrics = ActiveLearningMetrics()
        self.scheduler = RetrainingScheduler()
    
    def get_summary(self, days: int = 30) -> Dict[str, Any]:
        """
        Get overall performance summary.
        
        Args:
            days: Number of days to analyze
            
        Returns:
            Dictionary with summary data
        """
        summary = {
            'period_days': days,
            'generated_at': timezone.now().isoformat(),
            'by_type': {},
            'overall': {},
            'retraining': {},
        }
        
        # Per-type metrics
        for stype, _ in SuggestionFeedback.SUGGESTION_TYPES:
            acceptance_rate = self.feedback_tracker.get_acceptance_rate(
                suggestion_type=stype,
                days=days,
            )
            
            difficult_cases = self.case_difficulty.identify_difficult_cases(
                suggestion_type=stype,
                days=days,
            )
            
            summary['by_type'][stype] = {
                'acceptance_rate': acceptance_rate,
                'difficult_cases': difficult_cases['total_cases'],
                'low_confidence_cases': difficult_cases['low_confidence_count'],
                'high_confidence_errors': difficult_cases['high_confidence_errors_count'],
            }
        
        # Overall metrics
        total_feedbacks = SuggestionFeedback.objects.filter(
            created_at__gte=timezone.now() - timedelta(days=days)
        ).count()
        
        overall_acceptance = self.feedback_tracker.get_acceptance_rate(days=days)
        
        summary['overall'] = {
            'total_feedbacks': total_feedbacks,
            'acceptance_rate': overall_acceptance,
        }
        
        # Retraining status
        recent_sessions = RetrainingSession.objects.filter(
            started_at__gte=timezone.now() - timedelta(days=days)
        ).count()
        
        summary['retraining'] = {
            'recent_sessions': recent_sessions,
            'enabled': self.scheduler.enabled,
        }
        
        return summary
    
    def get_detailed_report(
        self,
        suggestion_type: Optional[str] = None,
        days: int = 30,
    ) -> Dict[str, Any]:
        """
        Get detailed performance report.
        
        Args:
            suggestion_type: Filter by suggestion type
            days: Number of days to analyze
            
        Returns:
            Dictionary with detailed report
        """
        report = {
            'suggestion_type': suggestion_type or 'all',
            'period_days': days,
            'generated_at': timezone.now().isoformat(),
        }
        
        # Acceptance rate
        report['acceptance_rate'] = self.feedback_tracker.get_acceptance_rate(
            suggestion_type=suggestion_type,
            days=days,
        )
        
        # Difficult cases
        report['difficult_cases'] = self.case_difficulty.identify_difficult_cases(
            suggestion_type=suggestion_type,
            days=days,
        )
        
        # Confidence calibration
        report['calibration'] = self.case_difficulty.get_confidence_calibration(
            suggestion_type=suggestion_type,
            days=days,
        )
        
        # Accuracy trend
        if suggestion_type:
            report['accuracy_trend'] = self.metrics.get_accuracy_trend(
                suggestion_type=suggestion_type,
                days=days,
            )
        
        # Recent training sessions
        sessions = RetrainingSession.objects.all()
        if suggestion_type:
            # Map suggestion types to model types
            type_mapping = {
                'tag': 'classifier',
                'correspondent': 'ner',
                'document_type': 'classifier',
            }
            model_type = type_mapping.get(suggestion_type)
            if model_type:
                sessions = sessions.filter(model_type=model_type)
        
        sessions = sessions[:5]
        
        report['recent_training'] = [
            {
                'session_id': s.session_id,
                'model_type': s.model_type,
                'started_at': s.started_at.isoformat(),
                'status': s.status,
                'accuracy_before': s.accuracy_before,
                'accuracy_after': s.accuracy_after,
                'improvement': s.improvement,
            }
            for s in sessions
        ]
        
        return report

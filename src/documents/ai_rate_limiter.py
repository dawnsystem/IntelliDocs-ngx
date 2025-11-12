"""
AI Rate Limiter for IntelliDocs-ngx

This module provides rate limiting functionality specifically for AI operations
to prevent abuse and ensure fair resource usage.

Features:
- Per-user rate limits for AI scan operations
- Global rate limits for all AI operations
- Rate limits for deletion requests
- Admin/superuser bypass
- Detailed metrics tracking
- Clear error messages

According to issue requirements:
- Rate limit por usuario: X scans/hora
- Rate limit global: Y scans/minuto
- Rate limit para deletion requests: Z requests/día
- Bypass para admin/superuser
- Mensajes de error claros cuando se excede
- Métricas de rate limiting
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Optional, Tuple

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.utils import timezone
from django.utils.translation import gettext as _

if TYPE_CHECKING:
    from documents.models import Document

logger = logging.getLogger("paperless.ai_rate_limiter")


class RateLimitExceeded(Exception):
    """Exception raised when a rate limit is exceeded."""
    
    def __init__(self, message: str, retry_after: int = None):
        """
        Initialize exception.
        
        Args:
            message: Human-readable error message
            retry_after: Seconds until the user can retry
        """
        self.message = message
        self.retry_after = retry_after
        super().__init__(self.message)


class AIRateLimiter:
    """
    Rate limiter for AI operations.
    
    Provides granular rate limiting for different AI operations:
    - AI document scans (per user, per hour)
    - AI document scans (global, per minute)
    - AI deletion requests (per user, per day)
    
    Superusers and staff can bypass rate limits if configured.
    """
    
    # Default rate limits (can be overridden by settings)
    DEFAULT_SCAN_LIMIT_PER_USER = 100  # scans per hour
    DEFAULT_SCAN_LIMIT_GLOBAL = 50  # scans per minute
    DEFAULT_DELETION_LIMIT = 10  # deletion requests per day
    
    # Cache key prefixes
    CACHE_PREFIX_SCAN_USER = "ai_rate_limit_scan_user"
    CACHE_PREFIX_SCAN_GLOBAL = "ai_rate_limit_scan_global"
    CACHE_PREFIX_DELETION = "ai_rate_limit_deletion"
    CACHE_PREFIX_METRICS = "ai_rate_limit_metrics"
    
    @classmethod
    def _get_setting(cls, name: str, default):
        """Get a rate limit setting with a default value."""
        return getattr(settings, name, default)
    
    @classmethod
    def _should_bypass(cls, user: Optional[User]) -> bool:
        """
        Check if a user should bypass rate limits.
        
        Args:
            user: User to check (can be None for anonymous)
            
        Returns:
            True if user should bypass rate limits
        """
        if user is None:
            return False
        
        # Check if superuser bypass is enabled
        bypass_superuser = cls._get_setting(
            "PAPERLESS_RATE_LIMIT_BYPASS_SUPERUSER",
            True
        )
        
        if bypass_superuser and user.is_superuser:
            logger.debug(f"User {user.username} bypassing rate limit (superuser)")
            return True
        
        # Check if staff bypass is enabled
        bypass_staff = cls._get_setting(
            "PAPERLESS_RATE_LIMIT_BYPASS_STAFF",
            False
        )
        
        if bypass_staff and user.is_staff:
            logger.debug(f"User {user.username} bypassing rate limit (staff)")
            return True
        
        return False
    
    @classmethod
    def _check_limit(
        cls,
        cache_key: str,
        limit: int,
        window_seconds: int,
        operation_name: str,
    ) -> Tuple[bool, Optional[int]]:
        """
        Check if a rate limit has been exceeded.
        
        Args:
            cache_key: Cache key for this limit
            limit: Maximum number of operations
            window_seconds: Time window in seconds
            operation_name: Human-readable operation name for logging
            
        Returns:
            Tuple of (is_allowed, retry_after_seconds)
        """
        # Get current count
        current = cache.get(cache_key, 0)
        
        if current >= limit:
            # Calculate retry_after based on TTL of cache key
            ttl = cache.ttl(cache_key) if hasattr(cache, 'ttl') else window_seconds
            retry_after = max(1, ttl) if ttl > 0 else window_seconds
            
            logger.warning(
                f"Rate limit exceeded for {operation_name}: "
                f"{current}/{limit} in {window_seconds}s window. "
                f"Retry after {retry_after}s"
            )
            return False, retry_after
        
        # Increment counter
        # Use get_or_set pattern to handle race conditions
        if current == 0:
            cache.set(cache_key, 1, window_seconds)
        else:
            cache.incr(cache_key)
        
        logger.debug(
            f"Rate limit check passed for {operation_name}: "
            f"{current + 1}/{limit} in {window_seconds}s window"
        )
        return True, None
    
    @classmethod
    def _record_metric(
        cls,
        user: Optional[User],
        operation: str,
        allowed: bool,
    ):
        """
        Record rate limiting metrics for monitoring.
        
        Args:
            user: User performing the operation
            operation: Type of operation (scan, deletion)
            allowed: Whether the operation was allowed
        """
        date_key = timezone.now().strftime("%Y-%m-%d")
        metric_key = f"{cls.CACHE_PREFIX_METRICS}:{date_key}:{operation}"
        
        # Increment counters
        if allowed:
            cache.incr(f"{metric_key}:allowed", 1)
        else:
            cache.incr(f"{metric_key}:blocked", 1)
        
        # Set expiry for 7 days
        cache.expire(f"{metric_key}:allowed", 7 * 24 * 60 * 60)
        cache.expire(f"{metric_key}:blocked", 7 * 24 * 60 * 60)
        
        # Track per-user metrics if authenticated
        if user and user.is_authenticated:
            user_metric_key = f"{metric_key}:user_{user.id}"
            if allowed:
                cache.incr(f"{user_metric_key}:allowed", 1)
            else:
                cache.incr(f"{user_metric_key}:blocked", 1)
            
            cache.expire(f"{user_metric_key}:allowed", 7 * 24 * 60 * 60)
            cache.expire(f"{user_metric_key}:blocked", 7 * 24 * 60 * 60)
    
    @classmethod
    def check_scan_limit(
        cls,
        user: Optional[User],
        document: Optional[Document] = None,
    ) -> None:
        """
        Check if AI scan operation is allowed.
        
        Enforces both per-user and global rate limits.
        
        Args:
            user: User performing the scan (can be None for system scans)
            document: Document being scanned (for logging)
            
        Raises:
            RateLimitExceeded: If rate limit is exceeded
        """
        # Check bypass
        if cls._should_bypass(user):
            cls._record_metric(user, "scan", allowed=True)
            return
        
        # Get limits from settings
        user_limit = cls._get_setting(
            "PAPERLESS_AI_SCAN_RATE_LIMIT_PER_USER",
            cls.DEFAULT_SCAN_LIMIT_PER_USER
        )
        global_limit = cls._get_setting(
            "PAPERLESS_AI_SCAN_RATE_LIMIT_GLOBAL",
            cls.DEFAULT_SCAN_LIMIT_GLOBAL
        )
        
        # Check per-user limit (hourly)
        if user and user.is_authenticated:
            user_key = f"{cls.CACHE_PREFIX_SCAN_USER}:{user.id}"
            user_allowed, user_retry = cls._check_limit(
                user_key,
                user_limit,
                3600,  # 1 hour
                f"AI scan (user {user.username})"
            )
            
            if not user_allowed:
                cls._record_metric(user, "scan", allowed=False)
                raise RateLimitExceeded(
                    _(
                        "You have exceeded the AI scan rate limit. "
                        f"Maximum {user_limit} scans per hour allowed. "
                        f"Please try again in {user_retry} seconds."
                    ),
                    retry_after=user_retry
                )
        
        # Check global limit (per minute)
        global_key = f"{cls.CACHE_PREFIX_SCAN_GLOBAL}:all"
        global_allowed, global_retry = cls._check_limit(
            global_key,
            global_limit,
            60,  # 1 minute
            "AI scan (global)"
        )
        
        if not global_allowed:
            cls._record_metric(user, "scan", allowed=False)
            raise RateLimitExceeded(
                _(
                    "The system is currently experiencing high AI scan demand. "
                    f"Please try again in {global_retry} seconds."
                ),
                retry_after=global_retry
            )
        
        # All checks passed
        cls._record_metric(user, "scan", allowed=True)
        logger.info(
            f"AI scan rate limit check passed for user {user.username if user else 'system'}"
            + (f" on document {document.id}" if document else "")
        )
    
    @classmethod
    def check_deletion_limit(
        cls,
        user: User,
        document_count: int = 1,
    ) -> None:
        """
        Check if AI deletion request is allowed.
        
        Enforces per-user daily limit on deletion requests.
        
        Args:
            user: User making the deletion request
            document_count: Number of documents in the deletion request
            
        Raises:
            RateLimitExceeded: If rate limit is exceeded
        """
        if not user or not user.is_authenticated:
            raise RateLimitExceeded(
                _("Authentication required for deletion requests.")
            )
        
        # Check bypass
        if cls._should_bypass(user):
            cls._record_metric(user, "deletion", allowed=True)
            return
        
        # Get limit from settings
        deletion_limit = cls._get_setting(
            "PAPERLESS_AI_DELETION_RATE_LIMIT",
            cls.DEFAULT_DELETION_LIMIT
        )
        
        # Check per-user limit (daily)
        user_key = f"{cls.CACHE_PREFIX_DELETION}:{user.id}"
        allowed, retry_after = cls._check_limit(
            user_key,
            deletion_limit,
            86400,  # 24 hours
            f"AI deletion request (user {user.username})"
        )
        
        if not allowed:
            cls._record_metric(user, "deletion", allowed=False)
            hours = retry_after // 3600
            minutes = (retry_after % 3600) // 60
            
            time_str = ""
            if hours > 0:
                time_str = f"{hours} hour{'s' if hours != 1 else ''}"
            if minutes > 0:
                if time_str:
                    time_str += f" and {minutes} minute{'s' if minutes != 1 else ''}"
                else:
                    time_str = f"{minutes} minute{'s' if minutes != 1 else ''}"
            
            raise RateLimitExceeded(
                _(
                    "You have exceeded the AI deletion request rate limit. "
                    f"Maximum {deletion_limit} deletion requests per day allowed. "
                    f"Please try again in {time_str}."
                ),
                retry_after=retry_after
            )
        
        # All checks passed
        cls._record_metric(user, "deletion", allowed=True)
        logger.info(
            f"AI deletion rate limit check passed for user {user.username} "
            f"({document_count} document{'s' if document_count != 1 else ''})"
        )
    
    @classmethod
    def get_usage_stats(
        cls,
        user: Optional[User] = None,
        operation: Optional[str] = None,
    ) -> dict:
        """
        Get rate limiting usage statistics.
        
        Args:
            user: Optional user to get stats for
            operation: Optional operation type (scan, deletion)
            
        Returns:
            Dictionary with usage statistics
        """
        date_key = timezone.now().strftime("%Y-%m-%d")
        stats = {}
        
        operations = [operation] if operation else ["scan", "deletion"]
        
        for op in operations:
            metric_key = f"{cls.CACHE_PREFIX_METRICS}:{date_key}:{op}"
            
            # Get global stats
            allowed = cache.get(f"{metric_key}:allowed", 0)
            blocked = cache.get(f"{metric_key}:blocked", 0)
            
            stats[op] = {
                "allowed": allowed,
                "blocked": blocked,
                "total": allowed + blocked,
                "block_rate": blocked / (allowed + blocked) if (allowed + blocked) > 0 else 0,
            }
            
            # Get user-specific stats if requested
            if user and user.is_authenticated:
                user_metric_key = f"{metric_key}:user_{user.id}"
                user_allowed = cache.get(f"{user_metric_key}:allowed", 0)
                user_blocked = cache.get(f"{user_metric_key}:blocked", 0)
                
                stats[op]["user"] = {
                    "allowed": user_allowed,
                    "blocked": user_blocked,
                    "total": user_allowed + user_blocked,
                }
        
        return stats
    
    @classmethod
    def get_rate_limited_users(cls, operation: Optional[str] = None) -> list:
        """
        Get list of users who are currently rate limited.
        
        This is for admin visibility into who is rate limited.
        
        Args:
            operation: Optional operation type to filter by
            
        Returns:
            List of dictionaries with user info and limit status
        """
        # This would require scanning cache keys, which is expensive
        # For now, return empty list and rely on metrics
        # In production, this could be implemented with a separate tracking model
        logger.warning(
            "get_rate_limited_users is not fully implemented. "
            "Use get_usage_stats for metrics instead."
        )
        return []

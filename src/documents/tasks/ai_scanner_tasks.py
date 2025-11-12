"""
AI Scanner Celery Tasks for IntelliDocs-ngx

This module implements asynchronous AI document scanning using Celery.
AI scanning is performed in background to prevent blocking document consumption.

According to Issue 5.2 (AI Scanner Improvement Plan):
- AI tasks run in separate queue (priority: low)
- Rate limiting to prevent resource exhaustion
- Progress tracking for long scans
- Retry logic for temporary failures
- Does not block document consumption
"""

import logging
from typing import Optional

from celery import Task
from celery import shared_task
from celery.exceptions import MaxRetriesExceededError
from django.core.exceptions import ObjectDoesNotExist

from documents.models import Document

logger = logging.getLogger("paperless.tasks.ai_scanner")


class AITaskWithRetry(Task):
    """
    Custom task class for AI scanning with retry logic.
    
    Handles temporary failures gracefully with exponential backoff.
    Prevents overwhelming the system during high load periods.
    """
    
    autoretry_for = (
        ConnectionError,
        TimeoutError,
        MemoryError,
    )
    retry_kwargs = {
        "max_retries": 3,
        "countdown": 5,  # Initial delay in seconds
    }
    retry_backoff = True  # Exponential backoff
    retry_backoff_max = 300  # Max 5 minutes between retries
    retry_jitter = True  # Add randomness to prevent thundering herd


@shared_task(
    bind=True,
    base=AITaskWithRetry,
    name="documents.tasks.scan_document_ai",
    queue="ai_tasks",
    priority=1,  # Low priority (1-10 scale, 1 is lowest)
    time_limit=600,  # 10 minutes hard limit
    soft_time_limit=540,  # 9 minutes soft limit
    track_started=True,
    acks_late=True,  # Acknowledge after task completes
    reject_on_worker_lost=True,
)
def scan_document_ai(
    self: Task,
    document_id: int,
    document_text: str,
    original_file_path: Optional[str] = None,
    auto_apply: bool = True,
) -> dict:
    """
    Asynchronously scan a document with AI/ML for metadata suggestions.
    
    This task runs in a separate low-priority queue to prevent blocking
    the main document consumption pipeline. It performs comprehensive
    AI analysis including:
    - Tag suggestions
    - Correspondent detection
    - Document type classification
    - Storage path suggestions
    - Custom field extraction
    - Workflow recommendations
    
    Args:
        self: Task instance (injected by bind=True)
        document_id: ID of the document to scan
        document_text: Extracted text content of the document
        original_file_path: Optional path to the original file for OCR/image analysis
        auto_apply: Whether to auto-apply high-confidence suggestions (default: True)
        
    Returns:
        dict: Results summary with applied and suggested metadata
        
    Raises:
        ObjectDoesNotExist: If document is not found
        MaxRetriesExceededError: If all retries are exhausted
        
    Example:
        >>> # Call asynchronously
        >>> scan_document_ai.delay(document_id=123, document_text="Invoice...")
        
        >>> # Call synchronously (for testing)
        >>> scan_document_ai.apply(args=(123, "Invoice...")).get()
    """
    try:
        # Update task state to show progress
        self.update_state(
            state="PROGRESS",
            meta={
                "current": 0,
                "total": 100,
                "status": "Initializing AI scanner...",
            },
        )
        
        # Get document instance
        try:
            document = Document.objects.get(pk=document_id)
        except ObjectDoesNotExist:
            logger.error(f"Document {document_id} not found, cannot scan")
            return {
                "success": False,
                "error": f"Document {document_id} not found",
            }
        
        logger.info(
            f"Starting async AI scan for document: {document.title} (ID: {document_id})"
        )
        
        # Update progress
        self.update_state(
            state="PROGRESS",
            meta={
                "current": 10,
                "total": 100,
                "status": "Loading AI scanner...",
            },
        )
        
        # Import and initialize AI scanner
        try:
            from documents.ai_scanner import get_ai_scanner
            
            scanner = get_ai_scanner()
        except ImportError as e:
            logger.error(f"AI scanner not available: {e}")
            return {
                "success": False,
                "error": "AI scanner not available",
            }
        except Exception as e:
            logger.error(f"Failed to initialize AI scanner: {e}", exc_info=True)
            # Retry if initialization fails
            try:
                self.retry(countdown=30, exc=e)
            except MaxRetriesExceededError:
                logger.error(
                    f"Max retries exceeded for AI scan of document {document_id}"
                )
                return {
                    "success": False,
                    "error": f"Failed to initialize AI scanner after retries: {e}",
                }
        
        # Update progress
        self.update_state(
            state="PROGRESS",
            meta={
                "current": 30,
                "total": 100,
                "status": "Scanning document...",
            },
        )
        
        # Perform AI scan
        try:
            scan_result = scanner.scan_document(
                document=document,
                document_text=document_text,
                original_file_path=original_file_path,
            )
        except Exception as e:
            logger.error(
                f"AI scan failed for document {document_id}: {e}",
                exc_info=True,
            )
            # Retry on scan failure
            try:
                self.retry(countdown=60, exc=e)
            except MaxRetriesExceededError:
                logger.error(
                    f"Max retries exceeded for AI scan of document {document_id}"
                )
                return {
                    "success": False,
                    "error": f"AI scan failed after retries: {e}",
                }
        
        # Update progress
        self.update_state(
            state="PROGRESS",
            meta={
                "current": 70,
                "total": 100,
                "status": "Applying scan results...",
            },
        )
        
        # Apply scan results
        try:
            results = scanner.apply_scan_results(
                document=document,
                scan_result=scan_result,
                auto_apply=auto_apply,
            )
        except Exception as e:
            logger.error(
                f"Failed to apply AI scan results for document {document_id}: {e}",
                exc_info=True,
            )
            # Don't retry on application failure - scan succeeded
            return {
                "success": False,
                "error": f"Failed to apply scan results: {e}",
                "scan_completed": True,
            }
        
        # Update progress
        self.update_state(
            state="PROGRESS",
            meta={
                "current": 90,
                "total": 100,
                "status": "Finalizing...",
            },
        )
        
        # Log results
        applied = results.get("applied", {})
        suggestions = results.get("suggestions", {})
        
        if applied.get("tags"):
            logger.info(
                f"AI auto-applied {len(applied['tags'])} tags to document {document_id}"
            )
        
        if applied.get("correspondent"):
            logger.info(
                f"AI auto-applied correspondent to document {document_id}: "
                f"{applied['correspondent'].get('name')}"
            )
        
        if applied.get("document_type"):
            logger.info(
                f"AI auto-applied document type to document {document_id}: "
                f"{applied['document_type'].get('name')}"
            )
        
        if applied.get("storage_path"):
            logger.info(
                f"AI auto-applied storage path to document {document_id}: "
                f"{applied['storage_path'].get('name')}"
            )
        
        # Log suggestions for user review
        if suggestions.get("tags"):
            logger.info(
                f"AI suggested {len(suggestions['tags'])} tags for review "
                f"(document {document_id})"
            )
        
        if suggestions.get("correspondent"):
            logger.info(
                f"AI suggested correspondent for review (document {document_id}): "
                f"{suggestions['correspondent'].get('name')}"
            )
        
        # Update progress to complete
        self.update_state(
            state="PROGRESS",
            meta={
                "current": 100,
                "total": 100,
                "status": "Completed",
            },
        )
        
        logger.info(
            f"AI scan completed successfully for document {document_id}: "
            f"{document.title}"
        )
        
        return {
            "success": True,
            "document_id": document_id,
            "document_title": document.title,
            "applied_count": {
                "tags": len(applied.get("tags", [])),
                "correspondent": 1 if applied.get("correspondent") else 0,
                "document_type": 1 if applied.get("document_type") else 0,
                "storage_path": 1 if applied.get("storage_path") else 0,
                "custom_fields": len(applied.get("custom_fields", [])),
            },
            "suggestions_count": {
                "tags": len(suggestions.get("tags", [])),
                "correspondent": 1 if suggestions.get("correspondent") else 0,
                "document_type": 1 if suggestions.get("document_type") else 0,
                "storage_path": 1 if suggestions.get("storage_path") else 0,
                "custom_fields": len(suggestions.get("custom_fields", [])),
            },
        }
        
    except Exception as e:
        logger.error(
            f"Unexpected error in AI scan task for document {document_id}: {e}",
            exc_info=True,
        )
        # Try to retry on unexpected errors
        try:
            self.retry(countdown=120, exc=e)
        except MaxRetriesExceededError:
            logger.error(
                f"Max retries exceeded for AI scan of document {document_id}"
            )
            return {
                "success": False,
                "error": f"Unexpected error after retries: {e}",
            }

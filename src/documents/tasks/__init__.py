"""
Document-related Celery tasks.

This module contains asynchronous tasks for document processing,
including AI scanning and other background operations.
"""

from documents.tasks.ai_scanner_tasks import scan_document_ai

__all__ = ["scan_document_ai"]

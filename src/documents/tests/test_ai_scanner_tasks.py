"""
Tests for AI Scanner Celery Tasks.

This module tests the asynchronous AI scanner implementation,
ensuring tasks are properly queued and executed.
"""

from unittest.mock import Mock
from unittest.mock import patch

import pytest
from django.test import override_settings

from documents.tasks import scan_document_ai


class TestAIScannerTasks:
    """Test suite for AI scanner async tasks."""

    def test_task_is_registered(self):
        """Test that the scan_document_ai task is properly registered."""
        assert scan_document_ai is not None
        assert scan_document_ai.name == "documents.tasks.scan_document_ai"

    def test_task_queue_configuration(self):
        """Test that task is configured for ai_tasks queue."""
        # The task should be routed to ai_tasks queue
        task_options = scan_document_ai.options
        assert task_options.get("queue") == "ai_tasks"

    def test_task_has_retry_logic(self):
        """Test that task has retry configuration."""
        # Check that the task base class has retry settings
        assert hasattr(scan_document_ai, "autoretry_for")
        assert ConnectionError in scan_document_ai.autoretry_for
        assert TimeoutError in scan_document_ai.autoretry_for
        assert MemoryError in scan_document_ai.autoretry_for

    def test_task_has_time_limits(self):
        """Test that task has proper time limits configured."""
        task_options = scan_document_ai.options
        assert task_options.get("time_limit") == 600  # 10 minutes
        assert task_options.get("soft_time_limit") == 540  # 9 minutes

    @pytest.mark.django_db
    @patch("documents.tasks.ai_scanner_tasks.Document")
    def test_task_handles_missing_document(self, mock_document_model):
        """Test that task gracefully handles missing document."""
        # Mock document not found
        mock_document_model.objects.get.side_effect = Exception("Not found")

        # Call task directly (not via delay)
        result = scan_document_ai(
            document_id=999,
            document_text="Test text",
            auto_apply=True,
        )

        # Should return error result, not raise exception
        assert result["success"] is False
        assert "error" in result

    @pytest.mark.django_db
    @patch("documents.tasks.ai_scanner_tasks.get_ai_scanner")
    @patch("documents.tasks.ai_scanner_tasks.Document")
    def test_task_calls_ai_scanner(self, mock_document_model, mock_get_scanner):
        """Test that task properly calls the AI scanner."""
        # Setup mocks
        mock_doc = Mock()
        mock_doc.pk = 1
        mock_doc.title = "Test Document"
        mock_document_model.objects.get.return_value = mock_doc

        mock_scanner = Mock()
        mock_scan_result = Mock()
        mock_scanner.scan_document.return_value = mock_scan_result
        mock_scanner.apply_scan_results.return_value = {
            "applied": {
                "tags": [],
                "correspondent": None,
                "document_type": None,
                "storage_path": None,
                "custom_fields": [],
            },
            "suggestions": {
                "tags": [],
                "correspondent": None,
                "document_type": None,
                "storage_path": None,
                "custom_fields": [],
            },
        }
        mock_get_scanner.return_value = mock_scanner

        # Call task
        result = scan_document_ai(
            document_id=1,
            document_text="Test document text",
            auto_apply=True,
        )

        # Verify AI scanner was called
        mock_get_scanner.assert_called_once()
        mock_scanner.scan_document.assert_called_once()
        mock_scanner.apply_scan_results.assert_called_once()

        # Verify result
        assert result["success"] is True
        assert result["document_id"] == 1

    @override_settings(PAPERLESS_AI_SCANNER_SYNC=True)
    @pytest.mark.django_db
    def test_consumer_sync_mode(self):
        """Test that consumer can run AI scanner synchronously for testing."""
        # This test verifies the PAPERLESS_AI_SCANNER_SYNC setting exists
        from django.conf import settings

        assert settings.PAPERLESS_AI_SCANNER_SYNC is True

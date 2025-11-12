"""
AI Deletion Manager for IntelliDocs-ngx

This module ensures that AI cannot delete files without explicit user authorization.
It provides a comprehensive confirmation workflow that informs users about
what will be deleted and requires explicit approval.

According to agents.md requirements:
- AI CANNOT delete files without user validation
- AI must inform users comprehensively about deletions
- AI must request explicit authorization before any deletion
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Dict, List, Optional, Any

from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    from documents.models import Document, DeletionRequest

logger = logging.getLogger("paperless.ai_deletion")


class AIDeletionManager:
    """
    Manager for AI-initiated deletion requests.
    
    Ensures all deletions go through proper user approval workflow.
    """
    
    @staticmethod
    def create_deletion_request(
        documents: List,
        reason: str,
        user: User,
        impact_analysis: Optional[Dict[str, Any]] = None,
    ):
        """
        Create a new deletion request that requires user approval.
        
        Args:
            documents: List of documents to be deleted
            reason: Detailed explanation from AI
            user: User who must approve
            impact_analysis: Optional detailed impact analysis
            
        Returns:
            Created DeletionRequest instance
        """
        from documents.models import DeletionRequest
        
        # Analyze impact if not provided
        if impact_analysis is None:
            impact_analysis = AIDeletionManager._analyze_impact(documents)
        
        # Create request
        request = DeletionRequest.objects.create(
            requested_by_ai=True,
            ai_reason=reason,
            user=user,
            status=DeletionRequest.STATUS_PENDING,
            impact_summary=impact_analysis,
        )
        
        # Add documents
        request.documents.set(documents)
        
        logger.info(
            _("Created deletion request %(request_id)s for %(count)d documents requiring approval from user %(user)s") % {
                'request_id': request.id,
                'count': len(documents),
                'user': user.username
            }
        )
        
        # TODO: Send notification to user about pending deletion request
        # This could be via email, in-app notification, or both
        
        return request
    
    @staticmethod
    def _analyze_impact(documents: List) -> Dict[str, Any]:
        """
        Analyze the impact of deleting the given documents.
        
        Returns comprehensive information about what will be affected.
        """
        impact = {
            "document_count": len(documents),
            "total_size_bytes": 0,
            "documents": [],
            "affected_tags": set(),
            "affected_correspondents": set(),
            "affected_types": set(),
            "date_range": {
                "earliest": None,
                "latest": None,
            },
        }
        
        for doc in documents:
            # Document details
            doc_info = {
                "id": doc.id,
                "title": doc.title,
                "created": doc.created.isoformat() if doc.created else None,
                "correspondent": doc.correspondent.name if doc.correspondent else None,
                "document_type": doc.document_type.name if doc.document_type else None,
                "tags": [tag.name for tag in doc.tags.all()],
            }
            impact["documents"].append(doc_info)
            
            # Track size (if available)
            # Note: This would need actual file size tracking
            
            # Track affected metadata
            if doc.correspondent:
                impact["affected_correspondents"].add(doc.correspondent.name)
            
            if doc.document_type:
                impact["affected_types"].add(doc.document_type.name)
            
            for tag in doc.tags.all():
                impact["affected_tags"].add(tag.name)
            
            # Track date range
            if doc.created:
                if impact["date_range"]["earliest"] is None or doc.created < impact["date_range"]["earliest"]:
                    impact["date_range"]["earliest"] = doc.created
                
                if impact["date_range"]["latest"] is None or doc.created > impact["date_range"]["latest"]:
                    impact["date_range"]["latest"] = doc.created
        
        # Convert sets to lists for JSON serialization
        impact["affected_tags"] = list(impact["affected_tags"])
        impact["affected_correspondents"] = list(impact["affected_correspondents"])
        impact["affected_types"] = list(impact["affected_types"])
        
        # Convert dates to ISO format
        if impact["date_range"]["earliest"]:
            impact["date_range"]["earliest"] = impact["date_range"]["earliest"].isoformat()
        if impact["date_range"]["latest"]:
            impact["date_range"]["latest"] = impact["date_range"]["latest"].isoformat()
        
        return impact
    
    @staticmethod
    def get_pending_requests(user: User) -> List:
        """
        Get all pending deletion requests for a user.
        
        Args:
            user: User to get requests for
            
        Returns:
            List of pending DeletionRequest instances
        """
        from documents.models import DeletionRequest
        
        return list(
            DeletionRequest.objects.filter(
                user=user,
                status=DeletionRequest.STATUS_PENDING,
            )
        )
    
    @staticmethod
    def format_deletion_request_for_user(request) -> str:
        """
        Format a deletion request into a human-readable message.
        
        This provides comprehensive information to the user about what
        will be deleted, as required by agents.md.
        
        Args:
            request: DeletionRequest to format
            
        Returns:
            Formatted message string
        """
        impact = request.impact_summary
        
        separator = "==========================================="
        
        header = _("AI DELETION REQUEST #%(id)s") % {'id': request.id}
        
        reason_section = _("REASON:\n%(reason)s") % {'reason': request.ai_reason}
        
        impact_summary = _("IMPACT SUMMARY:\n- Number of documents: %(count)d\n- Affected tags: %(tags)s\n- Affected correspondents: %(correspondents)s\n- Affected document types: %(types)s") % {
            'count': impact.get('document_count', 0),
            'tags': ', '.join(impact.get('affected_tags', [])) or str(_('None')),
            'correspondents': ', '.join(impact.get('affected_correspondents', [])) or str(_('None')),
            'types': ', '.join(impact.get('affected_types', [])) or str(_('None'))
        }
        
        date_range = _("DATE RANGE:\n- Earliest: %(earliest)s\n- Latest: %(latest)s") % {
            'earliest': impact.get('date_range', {}).get('earliest', str(_('Unknown'))),
            'latest': impact.get('date_range', {}).get('latest', str(_('Unknown')))
        }
        
        docs_header = _("DOCUMENTS TO BE DELETED:")
        
        message = f"""
{separator}
{header}
{separator}

{reason_section}

{impact_summary}

{date_range}

{docs_header}
"""
        
        for i, doc in enumerate(impact.get('documents', []), 1):
            doc_info = _(
                "%(num)d. ID: %(id)s - %(title)s\n"
                "   Created: %(created)s\n"
                "   Correspondent: %(correspondent)s\n"
                "   Type: %(type)s\n"
                "   Tags: %(tags)s"
            ) % {
                'num': i,
                'id': doc['id'],
                'title': doc['title'],
                'created': doc['created'],
                'correspondent': doc['correspondent'] or str(_('None')),
                'type': doc['document_type'] or str(_('None')),
                'tags': ', '.join(doc['tags']) or str(_('None'))
            }
            message += f"\n{doc_info}\n"
        
        required_action = _(
            "REQUIRED ACTION:\n"
            "This deletion request requires your explicit approval.\n"
            "No files will be deleted until you confirm this action.\n\n"
            "Please review the above information carefully before\n"
            "approving or rejecting this request."
        )
        
        message += f"""
{separator}

{required_action}
"""
        
        return message
    
    @staticmethod
    def can_ai_delete_automatically() -> bool:
        """
        Check if AI is allowed to delete automatically.
        
        According to agents.md, AI should NEVER delete without user approval.
        This method always returns False as a safety measure.
        
        Returns:
            Always False - AI cannot auto-delete
        """
        return False


__all__ = ['AIDeletionManager']

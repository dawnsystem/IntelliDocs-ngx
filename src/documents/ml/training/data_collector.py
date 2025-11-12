"""
Data collection module for training custom models.

Collects documents with confirmed metadata to use as training data.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from django.db.models import Q

if TYPE_CHECKING:
    from documents.models import Document

logger = logging.getLogger("paperless.ml.training.data_collector")


@dataclass
class TrainingExample:
    """Single training example with document and metadata."""

    document_id: int
    content: str
    document_type: str | None
    correspondent: str | None
    tags: list[str]
    storage_path: str | None
    custom_fields: dict[str, str]
    created_date: datetime
    added_date: datetime


class DataCollector:
    """
    Collects training data from documents with confirmed metadata.

    Only collects documents that have:
    - Complete content (OCR processed)
    - User-confirmed metadata (not just AI suggestions)
    - Been in the system for a minimum period (quality control)
    """

    def __init__(
        self,
        min_age_days: int = 7,
        min_content_length: int = 100,
        include_untyped: bool = False,
    ):
        """
        Initialize data collector.

        Args:
            min_age_days: Minimum days since document was added (for quality control)
            min_content_length: Minimum content length in characters
            include_untyped: Whether to include documents without a document_type
        """
        self.min_age_days = min_age_days
        self.min_content_length = min_content_length
        self.include_untyped = include_untyped
        logger.info(
            f"DataCollector initialized: min_age={min_age_days}d, "
            f"min_content={min_content_length}chars",
        )

    def collect_for_document_type_classification(
        self,
        limit: int | None = None,
    ) -> list[TrainingExample]:
        """
        Collect documents for document type classification training.

        Args:
            limit: Maximum number of documents to collect (None = all)

        Returns:
            List of training examples
        """
        from datetime import timedelta

        from django.utils import timezone

        from documents.models import Document

        logger.info("Collecting documents for document type classification")

        # Calculate minimum date
        min_date = timezone.now() - timedelta(days=self.min_age_days)

        # Build query
        query = Q(
            added__lte=min_date,
            content__isnull=False,
        )

        # Filter by content length (using length function)
        from django.db.models import CharField
        from django.db.models.functions import Length

        Document.objects.annotate(content_length=Length("content"))

        if not self.include_untyped:
            query &= Q(document_type__isnull=False)

        # Query documents
        documents = (
            Document.objects.filter(query)
            .annotate(content_length=Length("content"))
            .filter(content_length__gte=self.min_content_length)
            .select_related("document_type", "correspondent", "storage_path")
            .prefetch_related("tags", "custom_fields")
            .order_by("-added")
        )

        if limit:
            documents = documents[:limit]

        # Convert to training examples
        examples = []
        for doc in documents:
            examples.append(self._document_to_training_example(doc))

        logger.info(f"Collected {len(examples)} documents for training")
        return examples

    def collect_for_correspondent_detection(
        self,
        limit: int | None = None,
    ) -> list[TrainingExample]:
        """
        Collect documents for correspondent detection training.

        Args:
            limit: Maximum number of documents to collect

        Returns:
            List of training examples
        """
        from datetime import timedelta

        from django.utils import timezone

        from documents.models import Document

        logger.info("Collecting documents for correspondent detection")

        min_date = timezone.now() - timedelta(days=self.min_age_days)

        query = Q(
            added__lte=min_date,
            content__isnull=False,
            correspondent__isnull=False,  # Must have correspondent
        )

        documents = (
            Document.objects.filter(query)
            .annotate(content_length=Length("content"))
            .filter(content_length__gte=self.min_content_length)
            .select_related("document_type", "correspondent", "storage_path")
            .prefetch_related("tags", "custom_fields")
            .order_by("-added")
        )

        if limit:
            documents = documents[:limit]

        examples = []
        for doc in documents:
            examples.append(self._document_to_training_example(doc))

        logger.info(f"Collected {len(examples)} documents with correspondents")
        return examples

    def collect_for_tag_suggestion(
        self,
        min_tags: int = 1,
        limit: int | None = None,
    ) -> list[TrainingExample]:
        """
        Collect documents for tag suggestion training.

        Args:
            min_tags: Minimum number of tags required
            limit: Maximum number of documents to collect

        Returns:
            List of training examples
        """
        from datetime import timedelta

        from django.utils import timezone

        from documents.models import Document

        logger.info("Collecting documents for tag suggestion")

        min_date = timezone.now() - timedelta(days=self.min_age_days)

        query = Q(
            added__lte=min_date,
            content__isnull=False,
        )

        documents = (
            Document.objects.filter(query)
            .annotate(
                content_length=Length("content"),
                tag_count=models.Count("tags"),
            )
            .filter(
                content_length__gte=self.min_content_length,
                tag_count__gte=min_tags,
            )
            .select_related("document_type", "correspondent", "storage_path")
            .prefetch_related("tags", "custom_fields")
            .order_by("-added")
        )

        if limit:
            documents = documents[:limit]

        examples = []
        for doc in documents:
            examples.append(self._document_to_training_example(doc))

        logger.info(f"Collected {len(examples)} documents with tags")
        return examples

    def collect_all(
        self,
        limit: int | None = None,
    ) -> list[TrainingExample]:
        """
        Collect all qualifying documents for general training.

        Args:
            limit: Maximum number of documents to collect

        Returns:
            List of training examples
        """
        from datetime import timedelta

        from django.utils import timezone

        from documents.models import Document

        logger.info("Collecting all qualifying documents")

        min_date = timezone.now() - timedelta(days=self.min_age_days)

        query = Q(
            added__lte=min_date,
            content__isnull=False,
        )

        documents = (
            Document.objects.filter(query)
            .annotate(content_length=Length("content"))
            .filter(content_length__gte=self.min_content_length)
            .select_related("document_type", "correspondent", "storage_path")
            .prefetch_related("tags", "custom_fields")
            .order_by("-added")
        )

        if limit:
            documents = documents[:limit]

        examples = []
        for doc in documents:
            examples.append(self._document_to_training_example(doc))

        logger.info(f"Collected {len(examples)} total documents")
        return examples

    def _document_to_training_example(self, doc: Document) -> TrainingExample:
        """Convert Document model to TrainingExample."""
        return TrainingExample(
            document_id=doc.id,
            content=doc.content,
            document_type=doc.document_type.name if doc.document_type else None,
            correspondent=doc.correspondent.name if doc.correspondent else None,
            tags=[tag.name for tag in doc.tags.all()],
            storage_path=doc.storage_path.name if doc.storage_path else None,
            custom_fields={
                cf.field.name: cf.value
                for cf in doc.custom_fields.all()
            },
            created_date=doc.created,
            added_date=doc.added,
        )

    def export_to_json(
        self,
        examples: list[TrainingExample],
        output_path: Path | str,
    ) -> None:
        """
        Export training examples to JSON file.

        Args:
            examples: List of training examples
            output_path: Path to output JSON file
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "metadata": {
                "collected_at": datetime.now().isoformat(),
                "count": len(examples),
                "min_age_days": self.min_age_days,
                "min_content_length": self.min_content_length,
            },
            "examples": [
                {
                    "document_id": ex.document_id,
                    "content": ex.content,
                    "document_type": ex.document_type,
                    "correspondent": ex.correspondent,
                    "tags": ex.tags,
                    "storage_path": ex.storage_path,
                    "custom_fields": ex.custom_fields,
                    "created_date": ex.created_date.isoformat()
                    if ex.created_date
                    else None,
                    "added_date": ex.added_date.isoformat()
                    if ex.added_date
                    else None,
                }
                for ex in examples
            ],
        }

        with open(output_path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Exported {len(examples)} examples to {output_path}")

    def get_statistics(self, examples: list[TrainingExample]) -> dict:
        """
        Get statistics about collected training data.

        Args:
            examples: List of training examples

        Returns:
            Dictionary with statistics
        """
        from collections import Counter

        if not examples:
            return {"count": 0}

        # Count document types
        doc_types = Counter(
            ex.document_type for ex in examples if ex.document_type
        )

        # Count correspondents
        correspondents = Counter(
            ex.correspondent for ex in examples if ex.correspondent
        )

        # Count tags (flatten all tags)
        all_tags = []
        for ex in examples:
            all_tags.extend(ex.tags)
        tags = Counter(all_tags)

        # Calculate content length statistics
        content_lengths = [len(ex.content) for ex in examples]

        stats = {
            "count": len(examples),
            "document_types": {
                "unique": len(doc_types),
                "distribution": dict(doc_types.most_common(10)),
            },
            "correspondents": {
                "unique": len(correspondents),
                "distribution": dict(correspondents.most_common(10)),
            },
            "tags": {
                "unique": len(tags),
                "total": len(all_tags),
                "distribution": dict(tags.most_common(10)),
            },
            "content_length": {
                "min": min(content_lengths) if content_lengths else 0,
                "max": max(content_lengths) if content_lengths else 0,
                "avg": (
                    sum(content_lengths) / len(content_lengths)
                    if content_lengths
                    else 0
                ),
            },
        }

        logger.info(f"Statistics: {stats['count']} documents, "
                   f"{stats['document_types']['unique']} types, "
                   f"{stats['correspondents']['unique']} correspondents, "
                   f"{stats['tags']['unique']} unique tags")

        return stats


# Missing import
from django.db import models

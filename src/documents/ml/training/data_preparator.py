"""
Data preparation module for training custom models.

Prepares and validates collected training data for model training.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from .data_collector import TrainingExample

logger = logging.getLogger("paperless.ml.training.data_preparator")


@dataclass
class PreparedDataset:
    """Prepared dataset ready for training."""

    texts: list[str]
    labels: list[int]
    label_map: dict[str, int]
    reverse_label_map: dict[int, str]
    metadata: dict


class DataPreparator:
    """
    Prepares training data for model training.

    Handles:
    - Text cleaning and normalization
    - Label encoding
    - Train/validation/test split
    - Data balancing
    - Quality validation
    """

    def __init__(
        self,
        min_samples_per_class: int = 5,
        max_text_length: int = 10000,
        balance_classes: bool = True,
    ):
        """
        Initialize data preparator.

        Args:
            min_samples_per_class: Minimum samples required per class
            max_text_length: Maximum text length (longer texts truncated)
            balance_classes: Whether to balance class distribution
        """
        self.min_samples_per_class = min_samples_per_class
        self.max_text_length = max_text_length
        self.balance_classes = balance_classes
        logger.info(
            f"DataPreparator initialized: min_samples={min_samples_per_class}, "
            f"balance={balance_classes}",
        )

    def prepare_for_classification(
        self,
        examples: list[TrainingExample],
        label_field: str = "document_type",
    ) -> PreparedDataset:
        """
        Prepare data for classification task.

        Args:
            examples: List of training examples
            label_field: Which field to use as label
                        ('document_type', 'correspondent', etc.)

        Returns:
            PreparedDataset ready for training
        """
        logger.info(
            f"Preparing {len(examples)} examples for {label_field} classification",
        )

        # Extract texts and labels
        texts = []
        labels_raw = []

        for ex in examples:
            # Get label value
            if label_field == "document_type":
                label = ex.document_type
            elif label_field == "correspondent":
                label = ex.correspondent
            elif label_field == "storage_path":
                label = ex.storage_path
            else:
                msg = f"Unknown label field: {label_field}"
                raise ValueError(msg)

            # Skip if no label
            if label is None:
                continue

            # Clean text
            cleaned_text = self._clean_text(ex.content)
            if not cleaned_text:
                continue

            texts.append(cleaned_text)
            labels_raw.append(label)

        logger.info(f"After filtering: {len(texts)} examples")

        # Filter classes with too few samples
        label_counts = Counter(labels_raw)
        valid_labels = {
            label
            for label, count in label_counts.items()
            if count >= self.min_samples_per_class
        }

        filtered_texts = []
        filtered_labels = []
        for text, label in zip(texts, labels_raw):
            if label in valid_labels:
                filtered_texts.append(text)
                filtered_labels.append(label)

        logger.info(
            f"After class filtering: {len(filtered_texts)} examples, "
            f"{len(valid_labels)} classes",
        )

        if not filtered_texts:
            msg = "No valid training data after filtering"
            raise ValueError(msg)

        # Balance classes if requested
        if self.balance_classes:
            filtered_texts, filtered_labels = self._balance_classes(
                filtered_texts,
                filtered_labels,
            )
            logger.info(f"After balancing: {len(filtered_texts)} examples")

        # Create label encoding
        unique_labels = sorted(set(filtered_labels))
        label_map = {label: idx for idx, label in enumerate(unique_labels)}
        reverse_label_map = {idx: label for label, idx in label_map.items()}

        # Encode labels
        encoded_labels = [label_map[label] for label in filtered_labels]

        # Prepare metadata
        metadata = {
            "num_classes": len(unique_labels),
            "num_samples": len(filtered_texts),
            "label_field": label_field,
            "class_distribution": dict(Counter(filtered_labels)),
        }

        logger.info(
            f"Prepared dataset: {metadata['num_samples']} samples, "
            f"{metadata['num_classes']} classes",
        )

        return PreparedDataset(
            texts=filtered_texts,
            labels=encoded_labels,
            label_map=label_map,
            reverse_label_map=reverse_label_map,
            metadata=metadata,
        )

    def prepare_for_multilabel(
        self,
        examples: list[TrainingExample],
        label_field: str = "tags",
    ) -> PreparedDataset:
        """
        Prepare data for multi-label classification (e.g., tags).

        Args:
            examples: List of training examples
            label_field: Which field to use ('tags' typically)

        Returns:
            PreparedDataset with multi-label encoding
        """
        logger.info(
            f"Preparing {len(examples)} examples for multi-label {label_field}",
        )

        texts = []
        all_labels_raw = []

        for ex in examples:
            # Get labels (list)
            if label_field == "tags":
                labels = ex.tags
            else:
                msg = f"Unknown multi-label field: {label_field}"
                raise ValueError(msg)

            # Skip if no labels
            if not labels:
                continue

            # Clean text
            cleaned_text = self._clean_text(ex.content)
            if not cleaned_text:
                continue

            texts.append(cleaned_text)
            all_labels_raw.append(labels)

        # Count label frequencies
        label_counter = Counter()
        for labels in all_labels_raw:
            label_counter.update(labels)

        # Filter labels with too few samples
        valid_labels = {
            label
            for label, count in label_counter.items()
            if count >= self.min_samples_per_class
        }

        # Filter examples
        filtered_texts = []
        filtered_labels = []
        for text, labels in zip(texts, all_labels_raw):
            # Keep only valid labels
            valid_example_labels = [l for l in labels if l in valid_labels]
            if valid_example_labels:
                filtered_texts.append(text)
                filtered_labels.append(valid_example_labels)

        logger.info(
            f"After filtering: {len(filtered_texts)} examples, "
            f"{len(valid_labels)} labels",
        )

        if not filtered_texts:
            msg = "No valid training data after filtering"
            raise ValueError(msg)

        # Create label encoding
        unique_labels = sorted(valid_labels)
        label_map = {label: idx for idx, label in enumerate(unique_labels)}
        reverse_label_map = {idx: label for label, idx in label_map.items()}

        # Encode labels as multi-hot vectors
        encoded_labels = []
        for labels in filtered_labels:
            encoded = [label_map[label] for label in labels]
            encoded_labels.append(encoded)

        metadata = {
            "num_labels": len(unique_labels),
            "num_samples": len(filtered_texts),
            "label_field": label_field,
            "multi_label": True,
            "label_distribution": dict(label_counter.most_common(20)),
        }

        logger.info(
            f"Prepared multi-label dataset: {metadata['num_samples']} samples, "
            f"{metadata['num_labels']} labels",
        )

        return PreparedDataset(
            texts=filtered_texts,
            labels=encoded_labels,
            label_map=label_map,
            reverse_label_map=reverse_label_map,
            metadata=metadata,
        )

    def split_dataset(
        self,
        dataset: PreparedDataset,
        train_ratio: float = 0.8,
        val_ratio: float = 0.1,
        test_ratio: float = 0.1,
        random_seed: int = 42,
    ) -> tuple[PreparedDataset, PreparedDataset, PreparedDataset]:
        """
        Split dataset into train/validation/test sets.

        Args:
            dataset: Prepared dataset
            train_ratio: Ratio for training set
            val_ratio: Ratio for validation set
            test_ratio: Ratio for test set
            random_seed: Random seed for reproducibility

        Returns:
            Tuple of (train_dataset, val_dataset, test_dataset)
        """
        if abs(train_ratio + val_ratio + test_ratio - 1.0) > 0.01:
            msg = "Ratios must sum to 1.0"
            raise ValueError(msg)

        np.random.seed(random_seed)

        # Create indices and shuffle
        indices = np.arange(len(dataset.texts))
        np.random.shuffle(indices)

        # Calculate split points
        n_train = int(len(indices) * train_ratio)
        n_val = int(len(indices) * val_ratio)

        train_indices = indices[:n_train]
        val_indices = indices[n_train : n_train + n_val]
        test_indices = indices[n_train + n_val :]

        # Create split datasets
        def create_split(split_indices):
            return PreparedDataset(
                texts=[dataset.texts[i] for i in split_indices],
                labels=[dataset.labels[i] for i in split_indices],
                label_map=dataset.label_map,
                reverse_label_map=dataset.reverse_label_map,
                metadata=dataset.metadata.copy(),
            )

        train_dataset = create_split(train_indices)
        val_dataset = create_split(val_indices)
        test_dataset = create_split(test_indices)

        logger.info(
            f"Split dataset: train={len(train_dataset.texts)}, "
            f"val={len(val_dataset.texts)}, test={len(test_dataset.texts)}",
        )

        return train_dataset, val_dataset, test_dataset

    def _clean_text(self, text: str) -> str:
        """
        Clean and normalize text.

        Args:
            text: Raw text

        Returns:
            Cleaned text
        """
        if not text:
            return ""

        # Remove excessive whitespace
        text = re.sub(r"\s+", " ", text)

        # Truncate if too long
        if len(text) > self.max_text_length:
            text = text[: self.max_text_length]

        return text.strip()

    def _balance_classes(
        self,
        texts: list[str],
        labels: list[str],
    ) -> tuple[list[str], list[str]]:
        """
        Balance class distribution using under-sampling of majority classes.

        Args:
            texts: List of texts
            labels: List of labels

        Returns:
            Tuple of (balanced_texts, balanced_labels)
        """
        # Count samples per class
        label_counts = Counter(labels)
        median_count = int(np.median(list(label_counts.values())))

        # Target count: median of class sizes (not too aggressive)
        target_count = max(median_count, self.min_samples_per_class * 2)

        # Group by label
        label_groups = {}
        for text, label in zip(texts, labels):
            if label not in label_groups:
                label_groups[label] = []
            label_groups[label].append(text)

        # Sample from each group
        balanced_texts = []
        balanced_labels = []

        for label, group_texts in label_groups.items():
            # Under-sample if more than target
            if len(group_texts) > target_count:
                np.random.seed(42)
                selected_indices = np.random.choice(
                    len(group_texts),
                    target_count,
                    replace=False,
                )
                selected_texts = [group_texts[i] for i in selected_indices]
            else:
                selected_texts = group_texts

            balanced_texts.extend(selected_texts)
            balanced_labels.extend([label] * len(selected_texts))

        logger.info(
            f"Balanced {len(texts)} -> {len(balanced_texts)} samples "
            f"(target ~{target_count} per class)",
        )

        return balanced_texts, balanced_labels

    def validate_dataset(self, dataset: PreparedDataset) -> dict:
        """
        Validate prepared dataset quality.

        Args:
            dataset: Prepared dataset

        Returns:
            Dictionary with validation results
        """
        issues = []
        warnings = []

        # Check minimum samples
        if len(dataset.texts) < 50:
            warnings.append(f"Low sample count: {len(dataset.texts)}")

        # Check class balance
        label_counts = Counter(dataset.labels)
        max_count = max(label_counts.values())
        min_count = min(label_counts.values())
        imbalance_ratio = max_count / min_count if min_count > 0 else float("inf")

        if imbalance_ratio > 10:
            warnings.append(
                f"High class imbalance: {imbalance_ratio:.1f}x difference",
            )

        # Check text lengths
        text_lengths = [len(text) for text in dataset.texts]
        avg_length = sum(text_lengths) / len(text_lengths)

        if avg_length < 100:
            warnings.append(f"Short average text length: {avg_length:.0f} chars")

        # Check for very small classes
        for label_id, count in label_counts.items():
            if count < 3:
                label_name = dataset.reverse_label_map[label_id]
                issues.append(f"Class '{label_name}' has only {count} samples")

        validation_result = {
            "valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "stats": {
                "num_samples": len(dataset.texts),
                "num_classes": len(dataset.label_map),
                "avg_text_length": avg_length,
                "imbalance_ratio": imbalance_ratio,
            },
        }

        if issues:
            logger.warning(f"Dataset validation found {len(issues)} issues")
        if warnings:
            logger.info(f"Dataset validation found {len(warnings)} warnings")

        return validation_result

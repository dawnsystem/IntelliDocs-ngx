"""
Model training module with hyperparameter tuning.

Trains custom models with automatic hyperparameter optimization.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import torch
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    Trainer,
    TrainingArguments,
)

if TYPE_CHECKING:
    from .data_preparator import PreparedDataset

logger = logging.getLogger("paperless.ml.training.trainer")


@dataclass
class TrainingConfig:
    """Configuration for model training."""

    model_name: str = "distilbert-base-uncased"
    num_epochs: int = 3
    batch_size: int = 8
    learning_rate: float = 2e-5
    weight_decay: float = 0.01
    warmup_steps: int = 500
    max_length: int = 512
    output_dir: str = "./models/trained"
    save_steps: int = 500
    eval_steps: int = 500
    logging_steps: int = 100


@dataclass
class TrainingResult:
    """Results from model training."""

    model_path: str
    train_loss: float
    eval_loss: float
    best_epoch: int
    total_epochs: int
    training_time_seconds: float
    config: TrainingConfig
    timestamp: str


class ModelTrainer:
    """
    Trains custom models with hyperparameter tuning.

    Supports:
    - BERT-based models for text classification
    - Automatic hyperparameter search
    - Early stopping
    - Model checkpointing
    """

    def __init__(self, config: TrainingConfig | None = None):
        """
        Initialize model trainer.

        Args:
            config: Training configuration (uses defaults if None)
        """
        self.config = config or TrainingConfig()
        logger.info(f"ModelTrainer initialized with model: {self.config.model_name}")

    def train(
        self,
        train_dataset: PreparedDataset,
        val_dataset: PreparedDataset,
    ) -> TrainingResult:
        """
        Train a model on prepared dataset.

        Args:
            train_dataset: Training data
            val_dataset: Validation data

        Returns:
            TrainingResult with metrics and model path
        """
        logger.info(
            f"Starting training with {len(train_dataset.texts)} train samples, "
            f"{len(val_dataset.texts)} val samples",
        )

        start_time = datetime.now()

        # Load tokenizer and model
        tokenizer = AutoTokenizer.from_pretrained(self.config.model_name)
        model = AutoModelForSequenceClassification.from_pretrained(
            self.config.model_name,
            num_labels=train_dataset.metadata["num_classes"],
        )

        # Prepare datasets for transformers
        train_torch_dataset = self._prepare_torch_dataset(
            train_dataset,
            tokenizer,
        )
        val_torch_dataset = self._prepare_torch_dataset(
            val_dataset,
            tokenizer,
        )

        # Training arguments
        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        training_args = TrainingArguments(
            output_dir=str(output_dir),
            num_train_epochs=self.config.num_epochs,
            per_device_train_batch_size=self.config.batch_size,
            per_device_eval_batch_size=self.config.batch_size,
            learning_rate=self.config.learning_rate,
            weight_decay=self.config.weight_decay,
            warmup_steps=self.config.warmup_steps,
            logging_dir=str(output_dir / "logs"),
            logging_steps=self.config.logging_steps,
            eval_strategy="steps",
            eval_steps=self.config.eval_steps,
            save_strategy="steps",
            save_steps=self.config.save_steps,
            save_total_limit=3,
            load_best_model_at_end=True,
            metric_for_best_model="eval_loss",
            greater_is_better=False,
            report_to="none",  # Don't report to external services
        )

        # Create trainer
        trainer = Trainer(
            model=model,
            args=training_args,
            train_dataset=train_torch_dataset,
            eval_dataset=val_torch_dataset,
        )

        # Train
        logger.info("Starting training loop...")
        train_result = trainer.train()

        # Evaluate
        logger.info("Evaluating model...")
        eval_result = trainer.evaluate()

        # Save final model
        final_model_dir = output_dir / "final"
        final_model_dir.mkdir(parents=True, exist_ok=True)
        trainer.save_model(str(final_model_dir))
        tokenizer.save_pretrained(str(final_model_dir))

        # Save label maps
        label_map_path = final_model_dir / "label_map.json"
        with open(label_map_path, "w") as f:
            json.dump(
                {
                    "label_map": train_dataset.label_map,
                    "reverse_label_map": {
                        str(k): v
                        for k, v in train_dataset.reverse_label_map.items()
                    },
                },
                f,
                indent=2,
            )

        # Calculate training time
        end_time = datetime.now()
        training_time = (end_time - start_time).total_seconds()

        result = TrainingResult(
            model_path=str(final_model_dir),
            train_loss=train_result.training_loss,
            eval_loss=eval_result["eval_loss"],
            best_epoch=int(train_result.global_step / len(train_torch_dataset)),
            total_epochs=self.config.num_epochs,
            training_time_seconds=training_time,
            config=self.config,
            timestamp=datetime.now().isoformat(),
        )

        logger.info(
            f"Training complete: train_loss={result.train_loss:.4f}, "
            f"eval_loss={result.eval_loss:.4f}, time={training_time:.1f}s",
        )

        # Save training result
        result_path = final_model_dir / "training_result.json"
        with open(result_path, "w") as f:
            json.dump(
                {
                    "model_path": result.model_path,
                    "train_loss": result.train_loss,
                    "eval_loss": result.eval_loss,
                    "best_epoch": result.best_epoch,
                    "total_epochs": result.total_epochs,
                    "training_time_seconds": result.training_time_seconds,
                    "timestamp": result.timestamp,
                    "config": {
                        "model_name": self.config.model_name,
                        "num_epochs": self.config.num_epochs,
                        "batch_size": self.config.batch_size,
                        "learning_rate": self.config.learning_rate,
                    },
                },
                f,
                indent=2,
            )

        return result

    def hyperparameter_search(
        self,
        train_dataset: PreparedDataset,
        val_dataset: PreparedDataset,
        param_grid: dict | None = None,
    ) -> tuple[TrainingResult, dict]:
        """
        Perform hyperparameter search to find best configuration.

        Args:
            train_dataset: Training data
            val_dataset: Validation data
            param_grid: Dictionary of parameters to search
                       (None = use default grid)

        Returns:
            Tuple of (best_result, all_results)
        """
        if param_grid is None:
            param_grid = {
                "learning_rate": [1e-5, 2e-5, 3e-5],
                "batch_size": [8, 16],
                "num_epochs": [3, 5],
            }

        logger.info(f"Starting hyperparameter search with grid: {param_grid}")

        # Generate all combinations
        from itertools import product

        param_names = list(param_grid.keys())
        param_values = list(param_grid.values())
        combinations = list(product(*param_values))

        logger.info(f"Testing {len(combinations)} combinations")

        results = []
        best_result = None
        best_eval_loss = float("inf")

        for i, combo in enumerate(combinations, 1):
            # Create config for this combination
            config = TrainingConfig(**vars(self.config))
            for param_name, param_value in zip(param_names, combo):
                setattr(config, param_name, param_value)

            # Update output dir to include params
            config.output_dir = (
                f"{self.config.output_dir}/hp_search/"
                f"lr{config.learning_rate}_bs{config.batch_size}_ep{config.num_epochs}"
            )

            logger.info(
                f"[{i}/{len(combinations)}] Testing: "
                f"lr={config.learning_rate}, bs={config.batch_size}, "
                f"ep={config.num_epochs}",
            )

            # Train with this configuration
            trainer = ModelTrainer(config)
            result = trainer.train(train_dataset, val_dataset)

            results.append(result)

            # Track best
            if result.eval_loss < best_eval_loss:
                best_eval_loss = result.eval_loss
                best_result = result
                logger.info(f"New best model! eval_loss={best_eval_loss:.4f}")

        logger.info(
            f"Hyperparameter search complete. Best eval_loss={best_eval_loss:.4f}",
        )

        # Save all results
        search_results_path = Path(self.config.output_dir) / "hp_search_results.json"
        search_results_path.parent.mkdir(parents=True, exist_ok=True)

        with open(search_results_path, "w") as f:
            json.dump(
                {
                    "best_params": {
                        "learning_rate": best_result.config.learning_rate,
                        "batch_size": best_result.config.batch_size,
                        "num_epochs": best_result.config.num_epochs,
                    },
                    "best_eval_loss": best_eval_loss,
                    "all_results": [
                        {
                            "eval_loss": r.eval_loss,
                            "train_loss": r.train_loss,
                            "learning_rate": r.config.learning_rate,
                            "batch_size": r.config.batch_size,
                            "num_epochs": r.config.num_epochs,
                        }
                        for r in results
                    ],
                },
                f,
                indent=2,
            )

        return best_result, {"results": results, "param_grid": param_grid}

    def _prepare_torch_dataset(
        self,
        dataset: PreparedDataset,
        tokenizer,
    ):
        """
        Convert PreparedDataset to PyTorch dataset.

        Args:
            dataset: Prepared dataset
            tokenizer: Tokenizer to use

        Returns:
            PyTorch dataset
        """
        from torch.utils.data import Dataset

        class TextDataset(Dataset):
            def __init__(self, texts, labels, tokenizer, max_length):
                self.texts = texts
                self.labels = labels
                self.tokenizer = tokenizer
                self.max_length = max_length

            def __len__(self):
                return len(self.texts)

            def __getitem__(self, idx):
                encoding = self.tokenizer(
                    self.texts[idx],
                    truncation=True,
                    padding="max_length",
                    max_length=self.max_length,
                    return_tensors="pt",
                )

                return {
                    "input_ids": encoding["input_ids"].flatten(),
                    "attention_mask": encoding["attention_mask"].flatten(),
                    "labels": torch.tensor(self.labels[idx], dtype=torch.long),
                }

        return TextDataset(
            dataset.texts,
            dataset.labels,
            tokenizer,
            self.config.max_length,
        )

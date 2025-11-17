"""
Base class for OCR model loaders.

This module provides a common base class for loading and managing transformer models
used in OCR operations, reducing code duplication across different OCR modules.
"""

import logging
from typing import Any, Callable, Optional, Tuple

logger = logging.getLogger("paperless.ocr.base_model_loader")


class BaseModelLoader:
    """
    Base class for OCR model loaders that use transformers.

    Provides common functionality for:
    - Lazy loading of models
    - GPU/CPU device management
    - Error handling and logging
    - Model and processor initialization

    Subclasses should call `_load_model()` with appropriate loader functions.
    """

    def __init__(
        self,
        model_name: str,
        use_gpu: bool = False,
    ):
        """
        Initialize the base model loader.

        Args:
            model_name: Name of the pretrained model (Hugging Face model ID)
            use_gpu: Whether to use GPU acceleration if available
        """
        self.model_name = model_name
        self.use_gpu = use_gpu
        self._model = None
        self._processor = None

    def _load_model(
        self,
        model_loader: Callable[[str], Any],
        processor_loader: Optional[Callable[[str], Any]] = None,
        model_type_name: str = "model",
    ) -> None:
        """
        Load the transformer model and optional processor with common logic.

        This method provides lazy loading with GPU/CPU management and error handling.

        Args:
            model_loader: Function to load the model (e.g., AutoModelForObjectDetection.from_pretrained)
            processor_loader: Optional function to load the processor (e.g., AutoImageProcessor.from_pretrained)
            model_type_name: Descriptive name for logging (e.g., "table detection", "handwriting recognition")

        Raises:
            ImportError: If required packages (transformers, torch) are not installed
        """
        if self._model is not None:
            return

        try:
            import torch

            logger.info(f"Loading {model_type_name} model: {self.model_name}")

            # Load processor if loader function provided
            if processor_loader is not None:
                self._processor = processor_loader(self.model_name)
                logger.debug(f"Processor loaded for {model_type_name}")

            # Load model
            self._model = model_loader(self.model_name)
            logger.debug(f"Model loaded for {model_type_name}")

            # Move to GPU if available and requested
            if self.use_gpu and torch.cuda.is_available():
                self._model = self._model.cuda()
                logger.info(f"Using GPU for {model_type_name}")
            else:
                if self.use_gpu:
                    logger.warning(
                        f"GPU requested for {model_type_name} but CUDA not available, using CPU"
                    )
                logger.info(f"Using CPU for {model_type_name}")

        except ImportError as e:
            logger.error(f"Failed to load {model_type_name} model: {e}")
            logger.error(
                "Please install required packages: uv pip install transformers torch pillow"
            )
            raise
        except Exception as e:
            logger.error(f"Unexpected error loading {model_type_name} model: {e}")
            raise

    def is_loaded(self) -> bool:
        """Check if the model is loaded."""
        return self._model is not None

    def unload_model(self) -> None:
        """Unload the model to free memory."""
        if self._model is not None:
            logger.info(f"Unloading model: {self.model_name}")
            del self._model
            self._model = None
        if self._processor is not None:
            del self._processor
            self._processor = None

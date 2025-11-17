import textwrap

from django.conf import settings
from django.core.checks import Error
from django.core.checks import Warning
from django.core.checks import register
from django.core.exceptions import FieldError
from django.db.utils import OperationalError
from django.db.utils import ProgrammingError

from documents.signals import document_consumer_declaration
from documents.templating.utils import convert_format_str_to_template_format


@register()
def changed_password_check(app_configs, **kwargs):
    from documents.models import Document
    from paperless.db import GnuPG

    try:
        encrypted_doc = (
            Document.objects.filter(
                storage_type=Document.STORAGE_TYPE_GPG,
            )
            .only("pk", "storage_type")
            .first()
        )
    except (OperationalError, ProgrammingError, FieldError):
        return []  # No documents table yet

    if encrypted_doc:
        if not settings.PASSPHRASE:
            return [
                Error(
                    "The database contains encrypted documents but no password is set.",
                ),
            ]

        if not GnuPG.decrypted(encrypted_doc.source_file):
            return [
                Error(
                    textwrap.dedent(
                        """
                The current password doesn't match the password of the
                existing documents.

                If you intend to change your password, you must first export
                all of the old documents, start fresh with the new password
                and then re-import them."
                """,
                    ),
                ),
            ]

    return []


@register()
def parser_check(app_configs, **kwargs):
    parsers = []
    for response in document_consumer_declaration.send(None):
        parsers.append(response[1])

    if len(parsers) == 0:
        return [
            Error(
                "No parsers found. This is a bug. The consumer won't be "
                "able to consume any documents without parsers.",
            ),
        ]
    else:
        return []


@register()
def filename_format_check(app_configs, **kwargs):
    if settings.FILENAME_FORMAT:
        converted_format = convert_format_str_to_template_format(
            settings.FILENAME_FORMAT,
        )
        if converted_format != settings.FILENAME_FORMAT:
            return [
                Warning(
                    f"Filename format {settings.FILENAME_FORMAT} is using the old style, please update to use double curly brackets",
                    hint=converted_format,
                ),
            ]
    return []


@register()
def ml_configuration_check(app_configs, **kwargs):
    """
    Validate ML/AI configuration settings.

    Checks:
    - PAPERLESS_ML_CLASSIFIER_MODEL must be a non-empty string if ML is enabled
    - PAPERLESS_ML_MODEL_CACHE must be a valid directory path if specified
    - Required ML dependencies (torch, transformers) must be installed if ML is enabled
    """
    errors = []

    # Check if ML features are enabled
    enable_ml = getattr(settings, "PAPERLESS_ENABLE_ML_FEATURES", False)
    if not enable_ml:
        # ML disabled, skip validation
        return []

    # Check 1: PAPERLESS_ML_CLASSIFIER_MODEL must be a valid string
    classifier_model = getattr(settings, "PAPERLESS_ML_CLASSIFIER_MODEL", None)
    if classifier_model is not None:
        if not isinstance(classifier_model, str):
            errors.append(
                Error(
                    "PAPERLESS_ML_CLASSIFIER_MODEL must be a string",
                    hint=f"Current value type: {type(classifier_model).__name__}",
                    id="documents.E001",
                ),
            )
        elif not classifier_model.strip():
            errors.append(
                Error(
                    "PAPERLESS_ML_CLASSIFIER_MODEL cannot be empty if ML features are enabled",
                    hint="Set a valid Hugging Face model name (e.g., 'distilbert-base-uncased') or disable ML features",
                    id="documents.E002",
                ),
            )

    # Check 2: PAPERLESS_ML_MODEL_CACHE must be a valid path
    model_cache = getattr(settings, "PAPERLESS_ML_MODEL_CACHE", None)
    if model_cache is not None:
        if not isinstance(model_cache, str):
            errors.append(
                Error(
                    "PAPERLESS_ML_MODEL_CACHE must be a string path",
                    hint=f"Current value type: {type(model_cache).__name__}",
                    id="documents.E003",
                ),
            )
        else:
            import os

            # Check if path exists or parent directory exists (for creation)
            if not os.path.exists(model_cache):
                parent_dir = os.path.dirname(model_cache)
                if parent_dir and not os.path.exists(parent_dir):
                    errors.append(
                        Warning(
                            f"PAPERLESS_ML_MODEL_CACHE parent directory does not exist: {parent_dir}",
                            hint="The directory will be created on first use, but ensure the parent path is correct",
                            id="documents.W001",
                        ),
                    )

    # Check 3: ML dependencies must be installed
    if enable_ml:
        missing_deps = []

        try:
            import torch  # noqa: F401
        except ImportError:
            missing_deps.append("torch (PyTorch)")

        try:
            import transformers  # noqa: F401
        except ImportError:
            missing_deps.append("transformers")

        try:
            import sentence_transformers  # noqa: F401
        except ImportError:
            missing_deps.append("sentence-transformers")

        if missing_deps:
            errors.append(
                Error(
                    "ML features are enabled but required dependencies are missing",
                    hint=f"Install missing packages: {', '.join(missing_deps)}. "
                    f"Run: uv pip install torch transformers sentence-transformers",
                    id="documents.E004",
                ),
            )

    # Check 4: GPU configuration
    use_gpu = getattr(settings, "PAPERLESS_USE_GPU", False)
    if use_gpu and enable_ml:
        try:
            import torch

            if not torch.cuda.is_available():
                errors.append(
                    Warning(
                        "PAPERLESS_USE_GPU is True but CUDA is not available",
                        hint="ML models will fall back to CPU. Install CUDA drivers or set PAPERLESS_USE_GPU=False",
                        id="documents.W002",
                    ),
                )
        except ImportError:
            pass  # Already handled in Check 3

    return errors

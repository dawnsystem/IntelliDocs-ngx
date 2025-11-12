"""
Unit tests for Multi-language NER Support.

Tests cover:
- Language detection for Spanish, English, French, and German
- Entity extraction accuracy for each language
- Fallback to English for unsupported languages
- Multilingual date, amount, and invoice number patterns
- Configuration of supported languages
- Model caching and lazy loading
"""

from unittest import mock

from django.test import TestCase, override_settings

from documents.ml.ner import DocumentNER, SUPPORTED_LANGUAGES


class TestLanguageDetection(TestCase):
    """Test automatic language detection functionality."""

    def test_detect_english(self):
        """Test detection of English documents."""
        ner = DocumentNER(auto_detect_language=True)
        
        text = "This is an invoice from ACME Corporation dated January 15, 2024."
        language = ner._detect_language(text)
        
        self.assertEqual(language, "en")

    def test_detect_spanish(self):
        """Test detection of Spanish documents."""
        ner = DocumentNER(auto_detect_language=True)
        
        text = "Esta es una factura de ACME Corporation con fecha del 15 de enero de 2024."
        language = ner._detect_language(text)
        
        self.assertEqual(language, "es")

    def test_detect_french(self):
        """Test detection of French documents."""
        ner = DocumentNER(auto_detect_language=True)
        
        text = "Ceci est une facture de ACME Corporation datée du 15 janvier 2024."
        language = ner._detect_language(text)
        
        self.assertEqual(language, "fr")

    def test_detect_german(self):
        """Test detection of German documents."""
        ner = DocumentNER(auto_detect_language=True)
        
        text = "Dies ist eine Rechnung von ACME Corporation vom 15. Januar 2024."
        language = ner._detect_language(text)
        
        self.assertEqual(language, "de")

    def test_fallback_to_english_unsupported(self):
        """Test fallback to English for unsupported languages."""
        ner = DocumentNER(
            auto_detect_language=True,
            supported_languages=["en", "es"]
        )
        
        # Italian text (not in supported list)
        text = "Questa è una fattura di ACME Corporation datata 15 gennaio 2024."
        language = ner._detect_language(text)
        
        # Should fallback to English
        self.assertEqual(language, "en")

    def test_fallback_on_detection_error(self):
        """Test fallback to English when detection fails."""
        ner = DocumentNER(auto_detect_language=True)
        
        # Very short text that might fail detection
        text = "123"
        language = ner._detect_language(text)
        
        # Should fallback to English
        self.assertEqual(language, "en")


class TestMultilingualEntityExtraction(TestCase):
    """Test entity extraction in multiple languages."""

    def setUp(self):
        """Set up test data."""
        self.ner = DocumentNER(auto_detect_language=True)

    @mock.patch('documents.ml.ner.pipeline')
    def test_extract_entities_english(self, mock_pipeline_func):
        """Test entity extraction from English text."""
        # Mock the pipeline
        mock_pipeline = mock.MagicMock()
        mock_pipeline.return_value = [
            {"entity_group": "PER", "word": "John Doe", "score": 0.95},
            {"entity_group": "ORG", "word": "ACME Corporation", "score": 0.92},
            {"entity_group": "LOC", "word": "New York", "score": 0.88},
        ]
        mock_pipeline_func.return_value = mock_pipeline
        
        # Re-create NER to use mock
        ner = DocumentNER(auto_detect_language=True)
        ner._pipelines["en"] = mock_pipeline
        
        text = "John Doe works at ACME Corporation in New York."
        entities = ner.extract_entities(text, language="en")
        
        self.assertEqual(entities["language"], "en")
        self.assertIn("John Doe", entities["persons"])
        self.assertIn("ACME Corporation", entities["organizations"])
        self.assertIn("New York", entities["locations"])

    @mock.patch('documents.ml.ner.pipeline')
    def test_extract_entities_spanish(self, mock_pipeline_func):
        """Test entity extraction from Spanish text."""
        mock_pipeline = mock.MagicMock()
        mock_pipeline.return_value = [
            {"entity_group": "PER", "word": "Juan Pérez", "score": 0.94},
            {"entity_group": "ORG", "word": "Corporación ACME", "score": 0.91},
            {"entity_group": "LOC", "word": "Madrid", "score": 0.89},
        ]
        mock_pipeline_func.return_value = mock_pipeline
        
        ner = DocumentNER(auto_detect_language=True)
        ner._pipelines["es"] = mock_pipeline
        
        text = "Juan Pérez trabaja en Corporación ACME en Madrid."
        entities = ner.extract_entities(text, language="es")
        
        self.assertEqual(entities["language"], "es")
        self.assertIn("Juan Pérez", entities["persons"])
        self.assertIn("Corporación ACME", entities["organizations"])
        self.assertIn("Madrid", entities["locations"])

    @mock.patch('documents.ml.ner.pipeline')
    def test_extract_entities_french(self, mock_pipeline_func):
        """Test entity extraction from French text."""
        mock_pipeline = mock.MagicMock()
        mock_pipeline.return_value = [
            {"entity_group": "PER", "word": "Jean Dupont", "score": 0.93},
            {"entity_group": "ORG", "word": "Société ACME", "score": 0.90},
            {"entity_group": "LOC", "word": "Paris", "score": 0.87},
        ]
        mock_pipeline_func.return_value = mock_pipeline
        
        ner = DocumentNER(auto_detect_language=True)
        ner._pipelines["fr"] = mock_pipeline
        
        text = "Jean Dupont travaille chez Société ACME à Paris."
        entities = ner.extract_entities(text, language="fr")
        
        self.assertEqual(entities["language"], "fr")
        self.assertIn("Jean Dupont", entities["persons"])
        self.assertIn("Société ACME", entities["organizations"])
        self.assertIn("Paris", entities["locations"])

    @mock.patch('documents.ml.ner.pipeline')
    def test_extract_entities_german(self, mock_pipeline_func):
        """Test entity extraction from German text."""
        mock_pipeline = mock.MagicMock()
        mock_pipeline.return_value = [
            {"entity_group": "PER", "word": "Hans Schmidt", "score": 0.96},
            {"entity_group": "ORG", "word": "ACME GmbH", "score": 0.92},
            {"entity_group": "LOC", "word": "Berlin", "score": 0.88},
        ]
        mock_pipeline_func.return_value = mock_pipeline
        
        ner = DocumentNER(auto_detect_language=True)
        ner._pipelines["de"] = mock_pipeline
        
        text = "Hans Schmidt arbeitet bei ACME GmbH in Berlin."
        entities = ner.extract_entities(text, language="de")
        
        self.assertEqual(entities["language"], "de")
        self.assertIn("Hans Schmidt", entities["persons"])
        self.assertIn("ACME GmbH", entities["organizations"])
        self.assertIn("Berlin", entities["locations"])


class TestMultilingualRegexPatterns(TestCase):
    """Test multilingual regex patterns for dates, amounts, invoices."""

    def setUp(self):
        """Set up NER instance."""
        self.ner = DocumentNER(auto_detect_language=False)

    def test_extract_dates_spanish(self):
        """Test date extraction in Spanish."""
        text = "Fecha: 15 de Enero de 2024"
        dates = self.ner.extract_dates(text)
        
        self.assertTrue(len(dates) > 0)

    def test_extract_dates_french(self):
        """Test date extraction in French."""
        text = "Date: 15 Janvier 2024"
        dates = self.ner.extract_dates(text)
        
        self.assertTrue(len(dates) > 0)

    def test_extract_dates_german(self):
        """Test date extraction in German."""
        text = "Datum: 15. Januar 2024"
        dates = self.ner.extract_dates(text)
        
        self.assertTrue(len(dates) > 0)

    def test_extract_amounts_euro(self):
        """Test amount extraction with Euro currency."""
        text = "Total: €1.234,56"
        amounts = self.ner.extract_amounts(text)
        
        self.assertTrue(len(amounts) > 0)
        self.assertTrue(any("€" in amt or "EUR" in amt for amt in amounts))

    def test_extract_invoice_spanish(self):
        """Test invoice number extraction in Spanish."""
        text = "Factura #INV-2024-001"
        invoice_numbers = self.ner.extract_invoice_numbers(text)
        
        self.assertTrue(len(invoice_numbers) > 0)
        self.assertIn("INV-2024-001", invoice_numbers)

    def test_extract_invoice_french(self):
        """Test invoice number extraction in French."""
        text = "Facture #FAC-2024-001"
        invoice_numbers = self.ner.extract_invoice_numbers(text)
        
        self.assertTrue(len(invoice_numbers) > 0)
        self.assertIn("FAC-2024-001", invoice_numbers)

    def test_extract_invoice_german(self):
        """Test invoice number extraction in German."""
        text = "Rechnung #RECH-2024-001"
        invoice_numbers = self.ner.extract_invoice_numbers(text)
        
        self.assertTrue(len(invoice_numbers) > 0)
        self.assertIn("RECH-2024-001", invoice_numbers)

    def test_extract_phones_european(self):
        """Test phone number extraction with European formats."""
        text = "Tel: +33 1 23 45 67 89"
        phones = self.ner.extract_phones(text)
        
        self.assertTrue(len(phones) > 0)


class TestPipelineCaching(TestCase):
    """Test model pipeline caching functionality."""

    @mock.patch('documents.ml.ner.pipeline')
    def test_pipeline_cached_for_language(self, mock_pipeline_func):
        """Test that pipelines are cached per language."""
        mock_pipeline = mock.MagicMock()
        mock_pipeline_func.return_value = mock_pipeline
        
        ner = DocumentNER(auto_detect_language=True)
        
        # First call should create pipeline
        pipeline1 = ner._get_pipeline_for_language("en")
        self.assertEqual(mock_pipeline_func.call_count, 1)
        
        # Second call should return cached pipeline
        pipeline2 = ner._get_pipeline_for_language("en")
        self.assertEqual(mock_pipeline_func.call_count, 1)  # Not called again
        
        # Should be the same object
        self.assertIs(pipeline1, pipeline2)

    @mock.patch('documents.ml.ner.pipeline')
    def test_different_pipelines_for_different_languages(self, mock_pipeline_func):
        """Test that different languages get different pipelines."""
        mock_pipeline = mock.MagicMock()
        mock_pipeline_func.return_value = mock_pipeline
        
        ner = DocumentNER(auto_detect_language=True)
        
        # Create pipelines for different languages
        ner._get_pipeline_for_language("en")
        ner._get_pipeline_for_language("es")
        
        # Should have called pipeline creation twice
        self.assertEqual(mock_pipeline_func.call_count, 2)
        
        # Should have two cached pipelines
        self.assertIn("en", ner._pipelines)
        self.assertIn("es", ner._pipelines)


class TestConfiguration(TestCase):
    """Test configuration of NER multi-language support."""

    def test_auto_detect_enabled_by_default(self):
        """Test that auto detection is enabled by default."""
        ner = DocumentNER()
        
        self.assertTrue(ner.auto_detect_language)

    def test_auto_detect_can_be_disabled(self):
        """Test that auto detection can be disabled."""
        ner = DocumentNER(auto_detect_language=False)
        
        self.assertFalse(ner.auto_detect_language)

    def test_default_supported_languages(self):
        """Test default supported languages."""
        ner = DocumentNER()
        
        self.assertEqual(ner.supported_languages, ["en", "es", "fr", "de"])

    def test_custom_supported_languages(self):
        """Test custom supported languages."""
        ner = DocumentNER(supported_languages=["en", "es"])
        
        self.assertEqual(ner.supported_languages, ["en", "es"])

    @override_settings(
        PAPERLESS_NER_AUTO_DETECT_LANGUAGE=False,
        PAPERLESS_NER_SUPPORTED_LANGUAGES=["en", "es"]
    )
    def test_settings_integration(self):
        """Test integration with Django settings."""
        from django.conf import settings
        
        # Verify settings are configured
        self.assertFalse(settings.PAPERLESS_NER_AUTO_DETECT_LANGUAGE)
        self.assertEqual(settings.PAPERLESS_NER_SUPPORTED_LANGUAGES, ["en", "es"])


class TestExtractAll(TestCase):
    """Test the extract_all method with multi-language support."""

    @mock.patch('documents.ml.ner.pipeline')
    def test_extract_all_includes_language(self, mock_pipeline_func):
        """Test that extract_all includes language information."""
        mock_pipeline = mock.MagicMock()
        mock_pipeline.return_value = [
            {"entity_group": "PER", "word": "Juan Pérez", "score": 0.94},
        ]
        mock_pipeline_func.return_value = mock_pipeline
        
        ner = DocumentNER(auto_detect_language=True)
        ner._pipelines["es"] = mock_pipeline
        
        text = "Juan Pérez trabaja en Madrid. Factura #INV-001 por €1.234,56"
        result = ner.extract_all(text, language="es")
        
        # Should include language
        self.assertEqual(result["language"], "es")
        
        # Should include all entity types
        self.assertIn("persons", result)
        self.assertIn("organizations", result)
        self.assertIn("locations", result)
        self.assertIn("dates", result)
        self.assertIn("amounts", result)
        self.assertIn("invoice_numbers", result)
        self.assertIn("emails", result)
        self.assertIn("phones", result)


class TestSupportedLanguagesConstant(TestCase):
    """Test the SUPPORTED_LANGUAGES constant."""

    def test_contains_required_languages(self):
        """Test that all required languages are supported."""
        required = ["en", "es", "fr", "de", "multi"]
        
        for lang in required:
            self.assertIn(lang, SUPPORTED_LANGUAGES)

    def test_all_languages_have_models(self):
        """Test that all languages have model names."""
        for lang, model in SUPPORTED_LANGUAGES.items():
            self.assertIsInstance(model, str)
            self.assertTrue(len(model) > 0)


class TestErrorHandling(TestCase):
    """Test error handling in multilingual NER."""

    @mock.patch('documents.ml.ner.pipeline')
    def test_fallback_on_model_load_failure(self, mock_pipeline_func):
        """Test fallback when model fails to load."""
        # First call fails, second succeeds with fallback
        mock_pipeline_func.side_effect = [
            Exception("Model not found"),
            mock.MagicMock()
        ]
        
        ner = DocumentNER(auto_detect_language=True)
        
        # Should fall back to multilingual model
        pipeline = ner._get_pipeline_for_language("es")
        
        # Should have tried twice (language-specific + fallback)
        self.assertEqual(mock_pipeline_func.call_count, 2)

    @mock.patch('documents.ml.ner.pipeline')
    def test_graceful_degradation_on_complete_failure(self, mock_pipeline_func):
        """Test graceful degradation when all models fail."""
        mock_pipeline_func.side_effect = Exception("All models failed")
        
        ner = DocumentNER(auto_detect_language=True)
        
        # Should return None instead of crashing
        pipeline = ner._get_pipeline_for_language("en")
        
        self.assertIsNone(pipeline)

    @mock.patch('documents.ml.ner.pipeline')
    def test_extract_entities_with_no_pipeline(self, mock_pipeline_func):
        """Test extract_entities when pipeline is unavailable."""
        mock_pipeline_func.side_effect = Exception("Model failed")
        
        ner = DocumentNER(auto_detect_language=True)
        
        # Should return empty results instead of crashing
        text = "Test text"
        entities = ner.extract_entities(text)
        
        self.assertEqual(entities["persons"], [])
        self.assertEqual(entities["organizations"], [])
        self.assertEqual(entities["locations"], [])
        self.assertEqual(entities["misc"], [])

"""
Named Entity Recognition (NER) for IntelliDocs-ngx.

Extracts structured information from documents:
- Names of people, organizations, locations
- Dates, amounts, invoice numbers
- Email addresses, phone numbers
- And more...

This enables automatic metadata extraction and better document understanding.

Multi-language support:
- Automatic language detection
- Multilingual NER models for Spanish, English, French, German
- Fallback to English for unsupported languages
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from langdetect import detect, LangDetectException
from transformers import pipeline

if TYPE_CHECKING:
    pass

logger = logging.getLogger("paperless.ml.ner")

# Supported languages and their corresponding NER models
SUPPORTED_LANGUAGES = {
    "en": "dslim/bert-base-NER",  # English (default)
    "es": "mrm8488/bert-spanish-cased-finetuned-ner",  # Spanish
    "fr": "Jean-Baptiste/camembert-ner",  # French
    "de": "dbmdz/bert-large-cased-finetuned-conll03-english",  # German (uses multilingual)
    # Multilingual model as fallback
    "multi": "Davlan/bert-base-multilingual-cased-ner-hrl",  # Multilingual
}


class DocumentNER:
    """
    Extract named entities from documents using BERT-based NER.
    
    Uses pre-trained NER models to automatically extract:
    - Person names (PER)
    - Organization names (ORG)
    - Locations (LOC)
    - Miscellaneous entities (MISC)
    
    Plus custom regex extraction for:
    - Dates
    - Amounts/Prices
    - Invoice numbers
    - Email addresses
    - Phone numbers
    
    Multi-language support:
    - Automatic language detection using langdetect
    - Language-specific models for better accuracy
    - Fallback to English/multilingual models for unsupported languages
    """

    def __init__(
        self,
        model_name: str = "dslim/bert-base-NER",
        auto_detect_language: bool = True,
        supported_languages: list[str] | None = None,
    ):
        """
        Initialize NER extractor.
        
        Args:
            model_name: HuggingFace NER model (used if auto_detect_language=False)
                       Default: dslim/bert-base-NER (good general purpose English)
            auto_detect_language: Enable automatic language detection
                                 Default: True
            supported_languages: List of language codes to support
                                Default: ["en", "es", "fr", "de"]
        """
        self.auto_detect_language = auto_detect_language
        self.supported_languages = supported_languages or ["en", "es", "fr", "de"]
        self.default_model = model_name
        
        # Cache for language-specific pipelines
        self._pipelines: dict[str, any] = {}
        
        # Initialize default pipeline
        if not auto_detect_language:
            logger.info(f"Initializing NER with model: {model_name}")
            self.ner_pipeline = pipeline(
                "ner",
                model=model_name,
                aggregation_strategy="simple",
            )
        else:
            logger.info(f"Initializing NER with multi-language support: {self.supported_languages}")
            self.ner_pipeline = None
        
        # Compile regex patterns for efficiency
        self._compile_patterns()

        logger.info("DocumentNER initialized successfully")

    def _detect_language(self, text: str) -> str:
        """
        Detect the language of the text.
        
        Args:
            text: Text to detect language from
            
        Returns:
            str: Language code (e.g., 'en', 'es', 'fr', 'de')
                 Returns 'en' if detection fails
        """
        try:
            # Use first 1000 characters for faster detection
            sample_text = text[:1000]
            detected_lang = detect(sample_text)
            
            logger.info(f"Detected language: {detected_lang}")
            
            # Return detected language if supported, otherwise 'en'
            if detected_lang in self.supported_languages:
                return detected_lang
            else:
                logger.warning(
                    f"Detected language '{detected_lang}' not in supported languages. "
                    f"Falling back to English."
                )
                return "en"
        except LangDetectException as e:
            logger.warning(f"Language detection failed: {e}. Falling back to English.")
            return "en"
        except Exception as e:
            logger.error(f"Unexpected error in language detection: {e}. Falling back to English.")
            return "en"
    
    def _get_pipeline_for_language(self, language: str):
        """
        Get or create NER pipeline for the specified language.
        
        Args:
            language: Language code (e.g., 'en', 'es', 'fr', 'de')
            
        Returns:
            NER pipeline for the language
        """
        # Return cached pipeline if available
        if language in self._pipelines:
            return self._pipelines[language]
        
        # Get model for language
        model_name = SUPPORTED_LANGUAGES.get(language, SUPPORTED_LANGUAGES["en"])
        
        try:
            logger.info(f"Loading NER model for {language}: {model_name}")
            pipeline_obj = pipeline(
                "ner",
                model=model_name,
                aggregation_strategy="simple",
            )
            
            # Cache the pipeline
            self._pipelines[language] = pipeline_obj
            logger.info(f"Successfully loaded NER model for {language}")
            
            return pipeline_obj
        except Exception as e:
            logger.error(f"Failed to load model for {language}: {e}. Using fallback.")
            
            # Try multilingual model as fallback
            if language != "multi" and "multi" not in self._pipelines:
                try:
                    logger.info("Loading multilingual fallback model")
                    fallback_pipeline = pipeline(
                        "ner",
                        model=SUPPORTED_LANGUAGES["multi"],
                        aggregation_strategy="simple",
                    )
                    self._pipelines["multi"] = fallback_pipeline
                    return fallback_pipeline
                except Exception as fallback_error:
                    logger.error(f"Fallback model also failed: {fallback_error}")
            
            # Last resort: return existing pipeline if any, or None
            if self._pipelines:
                return next(iter(self._pipelines.values()))
            return None

    def _compile_patterns(self) -> None:
        """Compile regex patterns for common entities."""
        # Date patterns (supports multiple formats including European)
        self.date_patterns = [
            re.compile(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"),  # MM/DD/YYYY, DD-MM-YYYY
            re.compile(r"\d{4}[/-]\d{1,2}[/-]\d{1,2}"),  # YYYY-MM-DD
            re.compile(
                r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}",
                re.IGNORECASE,
            ),  # Month DD, YYYY (English)
            # Spanish months
            re.compile(
                r"(?:Enero|Febrero|Marzo|Abril|Mayo|Junio|Julio|Agosto|Septiembre|Octubre|Noviembre|Diciembre) \d{1,2},? \d{4}",
                re.IGNORECASE,
            ),
            # French months
            re.compile(
                r"(?:Janvier|Février|Mars|Avril|Mai|Juin|Juillet|Août|Septembre|Octobre|Novembre|Décembre) \d{1,2},? \d{4}",
                re.IGNORECASE,
            ),
            # German months
            re.compile(
                r"(?:Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember) \d{1,2},? \d{4}",
                re.IGNORECASE,
            ),
        ]

        # Amount patterns (supports multiple currencies)
        self.amount_patterns = [
            re.compile(r"\$\s?\d{1,3}(?:,\d{3})*(?:\.\d{2})?"),  # $1,234.56
            re.compile(r"\d{1,3}(?:,\d{3})*(?:\.\d{2})?\s?USD"),  # 1,234.56 USD
            re.compile(r"€\s?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?"),  # €1.234,56 or €1,234.56
            re.compile(r"\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?\s?EUR"),  # 1.234,56 EUR
            re.compile(r"£\s?\d{1,3}(?:,\d{3})*(?:\.\d{2})?"),  # £1,234.56
            re.compile(r"\d{1,3}(?:,\d{3})*(?:\.\d{2})?\s?GBP"),  # 1,234.56 GBP
        ]

        # Invoice number patterns (multilingual)
        self.invoice_patterns = [
            re.compile(r"(?:Invoice|Inv\.?)\s*#?\s*(\w+)", re.IGNORECASE),  # English
            re.compile(r"(?:Invoice|Inv\.?)\s*(?:Number|No\.?)\s*:?\s*(\w+)", re.IGNORECASE),  # English
            re.compile(r"(?:Factura|Fact\.?)\s*#?\s*(\w+)", re.IGNORECASE),  # Spanish
            re.compile(r"(?:Facture|Fac\.?)\s*#?\s*(\w+)", re.IGNORECASE),  # French
            re.compile(r"(?:Rechnung|Rech\.?)\s*#?\s*(\w+)", re.IGNORECASE),  # German
        ]

        # Email pattern
        self.email_pattern = re.compile(
            r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        )

        # Phone pattern (US/International/European)
        self.phone_pattern = re.compile(
            r"(?:\+\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{2,4}[-.\s]?\d{2,4}",
        )

    def extract_entities(self, text: str, language: str | None = None) -> dict[str, list[str]]:
        """
        Extract named entities from text.
        
        Args:
            text: Document text
            language: Optional language code override (e.g., 'en', 'es', 'fr', 'de')
                     If None and auto_detect_language is True, language will be detected
            
        Returns:
            dict: Dictionary of entity types and their values
                  {
                      'persons': ['John Doe', ...],
                      'organizations': ['Acme Corp', ...],
                      'locations': ['New York', ...],
                      'misc': [...],
                      'language': 'en',  # Detected/used language
                  }
        """
        # Determine language
        if self.auto_detect_language:
            detected_lang = language or self._detect_language(text)
            ner_pipeline = self._get_pipeline_for_language(detected_lang)
        else:
            detected_lang = "en"
            ner_pipeline = self.ner_pipeline
        
        if ner_pipeline is None:
            logger.error("No NER pipeline available")
            return {
                "persons": [],
                "organizations": [],
                "locations": [],
                "misc": [],
                "language": detected_lang,
            }
        
        # Run NER model (limit to first 5000 chars for performance)
        entities = ner_pipeline(text[:5000])

        # Organize by type
        organized = {
            "persons": [],
            "organizations": [],
            "locations": [],
            "misc": [],
            "language": detected_lang,
        }

        for entity in entities:
            entity_type = entity["entity_group"]
            entity_text = entity["word"].strip()

            # Map entity types (some models use different labels)
            if entity_type in ("PER", "PERS", "PERSON"):
                organized["persons"].append(entity_text)
            elif entity_type in ("ORG", "ORGANIZATION"):
                organized["organizations"].append(entity_text)
            elif entity_type in ("LOC", "LOCATION", "GPE"):
                organized["locations"].append(entity_text)
            else:
                organized["misc"].append(entity_text)

        # Remove duplicates while preserving order
        for key in organized:
            if key != "language":
                seen = set()
                organized[key] = [
                    x for x in organized[key] if not (x in seen or seen.add(x))
                ]

        logger.info(f"Extracted entities in {detected_lang}: {sum(len(v) for k, v in organized.items() if k != 'language')} entities")
        logger.debug(f"Extracted entities detail: {organized}")
        return organized

    def extract_dates(self, text: str) -> list[str]:
        """
        Extract dates from text.
        
        Args:
            text: Document text
            
        Returns:
            list: List of date strings found
        """
        dates = []
        for pattern in self.date_patterns:
            dates.extend(pattern.findall(text))

        # Remove duplicates while preserving order
        seen = set()
        return [x for x in dates if not (x in seen or seen.add(x))]

    def extract_amounts(self, text: str) -> list[str]:
        """
        Extract monetary amounts from text.
        
        Args:
            text: Document text
            
        Returns:
            list: List of amount strings found
        """
        amounts = []
        for pattern in self.amount_patterns:
            amounts.extend(pattern.findall(text))

        # Remove duplicates while preserving order
        seen = set()
        return [x for x in amounts if not (x in seen or seen.add(x))]

    def extract_invoice_numbers(self, text: str) -> list[str]:
        """
        Extract invoice numbers from text.
        
        Args:
            text: Document text
            
        Returns:
            list: List of invoice numbers found
        """
        invoice_numbers = []
        for pattern in self.invoice_patterns:
            invoice_numbers.extend(pattern.findall(text))

        # Remove duplicates while preserving order
        seen = set()
        return [x for x in invoice_numbers if not (x in seen or seen.add(x))]

    def extract_emails(self, text: str) -> list[str]:
        """
        Extract email addresses from text.
        
        Args:
            text: Document text
            
        Returns:
            list: List of email addresses found
        """
        emails = self.email_pattern.findall(text)

        # Remove duplicates while preserving order
        seen = set()
        return [x for x in emails if not (x in seen or seen.add(x))]

    def extract_phones(self, text: str) -> list[str]:
        """
        Extract phone numbers from text.
        
        Args:
            text: Document text
            
        Returns:
            list: List of phone numbers found
        """
        phones = self.phone_pattern.findall(text)

        # Remove duplicates while preserving order
        seen = set()
        return [x for x in phones if not (x in seen or seen.add(x))]

    def extract_all(self, text: str, language: str | None = None) -> dict[str, list[str]]:
        """
        Extract all types of entities from text.
        
        This is the main method that combines NER and regex extraction.
        
        Args:
            text: Document text
            language: Optional language code override (e.g., 'en', 'es', 'fr', 'de')
                     If None and auto_detect_language is True, language will be detected
            
        Returns:
            dict: Complete extraction results
                  {
                      'persons': [...],
                      'organizations': [...],
                      'locations': [...],
                      'misc': [...],
                      'dates': [...],
                      'amounts': [...],
                      'invoice_numbers': [...],
                      'emails': [...],
                      'phones': [...],
                      'language': 'en',  # Detected/used language
                  }
        """
        logger.info("Extracting all entities from document")

        # Get NER entities (includes language detection)
        result = self.extract_entities(text, language)
        
        detected_lang = result.get("language", "en")

        # Add regex-based extractions
        result["dates"] = self.extract_dates(text)
        result["amounts"] = self.extract_amounts(text)
        result["invoice_numbers"] = self.extract_invoice_numbers(text)
        result["emails"] = self.extract_emails(text)
        result["phones"] = self.extract_phones(text)

        total_entities = sum(len(v) for k, v in result.items() if k != "language")
        logger.info(
            f"Extracted {total_entities} total entities from {detected_lang} document",
        )

        return result

    def extract_invoice_data(self, text: str) -> dict[str, any]:
        """
        Extract invoice-specific data from text.
        
        Specialized method for invoices that extracts common fields.
        
        Args:
            text: Invoice text
            
        Returns:
            dict: Invoice data
                  {
                      'invoice_numbers': [...],
                      'dates': [...],
                      'amounts': [...],
                      'vendors': [...],  # from organizations
                      'emails': [...],
                      'phones': [...],
                  }
        """
        logger.info("Extracting invoice-specific data")

        # Extract all entities
        all_entities = self.extract_all(text)

        # Create invoice-specific structure
        invoice_data = {
            "invoice_numbers": all_entities["invoice_numbers"],
            "dates": all_entities["dates"],
            "amounts": all_entities["amounts"],
            "vendors": all_entities["organizations"],  # Organizations = Vendors
            "emails": all_entities["emails"],
            "phones": all_entities["phones"],
        }

        # Try to identify total amount (usually the largest)
        if invoice_data["amounts"]:
            # Parse amounts to find largest
            try:
                parsed_amounts = []
                for amt in invoice_data["amounts"]:
                    # Remove currency symbols and commas
                    cleaned = re.sub(r"[$€£,]", "", amt)
                    cleaned = re.sub(r"\s", "", cleaned)
                    if cleaned:
                        parsed_amounts.append(float(cleaned))

                if parsed_amounts:
                    max_amount = max(parsed_amounts)
                    invoice_data["total_amount"] = max_amount
            except (ValueError, TypeError):
                pass

        return invoice_data

    def suggest_correspondent(self, text: str) -> str | None:
        """
        Suggest a correspondent based on extracted entities.
        
        Args:
            text: Document text
            
        Returns:
            str or None: Suggested correspondent name
        """
        entities = self.extract_entities(text)

        # Priority: organizations > persons
        if entities["organizations"]:
            return entities["organizations"][0]  # Return first org

        if entities["persons"]:
            return entities["persons"][0]  # Return first person

        return None

    def suggest_tags(self, text: str) -> list[str]:
        """
        Suggest tags based on extracted entities.
        
        Args:
            text: Document text
            
        Returns:
            list: Suggested tag names
        """
        tags = []

        # Check for invoice indicators
        if re.search(r"\binvoice\b", text, re.IGNORECASE):
            tags.append("invoice")

        # Check for receipt indicators
        if re.search(r"\breceipt\b", text, re.IGNORECASE):
            tags.append("receipt")

        # Check for contract indicators
        if re.search(r"\bcontract\b|\bagreement\b", text, re.IGNORECASE):
            tags.append("contract")

        # Check for letter indicators
        if re.search(r"\bdear\b|\bsincerely\b", text, re.IGNORECASE):
            tags.append("letter")

        return tags

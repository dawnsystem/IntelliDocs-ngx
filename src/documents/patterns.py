"""
Centralized regex patterns for document processing.

This module contains all reusable regex patterns used across the application
to avoid duplication and ensure consistency.

Patterns are organized by category:
- Date patterns
- Amount/currency patterns
- Contact information patterns (email, phone)
- Document type patterns
- Invoice-specific patterns
"""

from __future__ import annotations

import re

# ============================================================================
# DATE PATTERNS
# ============================================================================

# Matches dates in various formats: MM/DD/YYYY, DD-MM-YYYY
DATE_SLASH_PATTERN = re.compile(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}")

# Matches ISO format dates: YYYY-MM-DD
DATE_ISO_PATTERN = re.compile(r"\d{4}[/-]\d{1,2}[/-]\d{1,2}")

# Matches written dates: January 15, 2024
DATE_WRITTEN_PATTERN = re.compile(
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}",
    re.IGNORECASE,
)

# Comprehensive date regex from parsers.py
DATE_REGEX = re.compile(
    r"(\b|(?!=([_-])))(\d{1,2})[\.\/-](\d{1,2})[\.\/-](\d{4}|\d{2})(\b|(?=([_-])))|"
    r"(\b)(\d{4})[\.\/-](\d{1,2})[\.\/-](\d{1,2})(\b)",
)

# All date patterns grouped for convenience
ALL_DATE_PATTERNS = [
    DATE_SLASH_PATTERN,
    DATE_ISO_PATTERN,
    DATE_WRITTEN_PATTERN,
]

# ============================================================================
# AMOUNT / CURRENCY PATTERNS
# ============================================================================

# Matches US dollar amounts: $1,234.56
AMOUNT_USD_PATTERN = re.compile(r"\$\s?\d{1,3}(?:,\d{3})*(?:\.\d{2})?")

# Matches USD suffix: 1,234.56 USD
AMOUNT_USD_SUFFIX_PATTERN = re.compile(r"\d{1,3}(?:,\d{3})*(?:\.\d{2})?\s?USD")

# Matches Euro amounts: €1,234.56
AMOUNT_EUR_PATTERN = re.compile(r"€\s?\d{1,3}(?:,\d{3})*(?:\.\d{2})?")

# Matches British Pound amounts: £1,234.56
AMOUNT_GBP_PATTERN = re.compile(r"£\s?\d{1,3}(?:,\d{3})*(?:\.\d{2})?")

# All amount patterns grouped
ALL_AMOUNT_PATTERNS = [
    AMOUNT_USD_PATTERN,
    AMOUNT_USD_SUFFIX_PATTERN,
    AMOUNT_EUR_PATTERN,
    AMOUNT_GBP_PATTERN,
]

# ============================================================================
# INVOICE PATTERNS
# ============================================================================

# Matches invoice numbers: Invoice #ABC123, Inv. 12345
INVOICE_NUMBER_SIMPLE_PATTERN = re.compile(
    r"(?:Invoice|Inv\.?)\s*#?\s*(\w+)",
    re.IGNORECASE,
)

# Matches invoice numbers with "Number" or "No.": Invoice Number: 12345
INVOICE_NUMBER_FULL_PATTERN = re.compile(
    r"(?:Invoice|Inv\.?)\s*(?:Number|No\.?)\s*:?\s*(\w+)",
    re.IGNORECASE,
)

# All invoice patterns grouped
ALL_INVOICE_PATTERNS = [
    INVOICE_NUMBER_SIMPLE_PATTERN,
    INVOICE_NUMBER_FULL_PATTERN,
]

# ============================================================================
# CONTACT INFORMATION PATTERNS
# ============================================================================

# Matches email addresses
EMAIL_PATTERN = re.compile(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
)

# Matches phone numbers (US and international)
PHONE_PATTERN = re.compile(
    r"(?:\+\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}",
)

# ============================================================================
# DOCUMENT TYPE CLASSIFICATION PATTERNS
# ============================================================================

# Matches invoice-related keywords
INVOICE_KEYWORD_PATTERN = re.compile(r"\binvoice\b", re.IGNORECASE)

# Matches receipt-related keywords
RECEIPT_KEYWORD_PATTERN = re.compile(r"\breceipt\b", re.IGNORECASE)

# Matches contract/agreement-related keywords
CONTRACT_KEYWORD_PATTERN = re.compile(
    r"\bcontract\b|\bagreement\b",
    re.IGNORECASE,
)

# Matches letter-related keywords
LETTER_KEYWORD_PATTERN = re.compile(
    r"\bdear\b|\bsincerely\b",
    re.IGNORECASE,
)

# ============================================================================
# SEARCH AND MATCHING PATTERNS
# ============================================================================

# Matches quoted terms and individual words for search parsing
SEARCH_TERMS_PATTERN = re.compile(r'"([^"]+)"|(\S+)')

# Matches whitespace for normalization
WHITESPACE_PATTERN = re.compile(r"\s+")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def extract_dates(text: str) -> list[str]:
    """
    Extract all dates from text using all date patterns.

    Args:
        text: Text to search for dates

    Returns:
        list: List of unique date strings found
    """
    dates = []
    for pattern in ALL_DATE_PATTERNS:
        dates.extend(pattern.findall(text))

    # Remove duplicates while preserving order
    seen = set()
    return [x for x in dates if not (x in seen or seen.add(x))]


def extract_amounts(text: str) -> list[str]:
    """
    Extract all monetary amounts from text.

    Args:
        text: Text to search for amounts

    Returns:
        list: List of unique amount strings found
    """
    amounts = []
    for pattern in ALL_AMOUNT_PATTERNS:
        amounts.extend(pattern.findall(text))

    # Remove duplicates while preserving order
    seen = set()
    return [x for x in amounts if not (x in seen or seen.add(x))]


def extract_invoice_numbers(text: str) -> list[str]:
    """
    Extract invoice numbers from text.

    Args:
        text: Text to search for invoice numbers

    Returns:
        list: List of unique invoice numbers found
    """
    invoice_numbers = []
    for pattern in ALL_INVOICE_PATTERNS:
        invoice_numbers.extend(pattern.findall(text))

    # Remove duplicates while preserving order
    seen = set()
    return [x for x in invoice_numbers if not (x in seen or seen.add(x))]


def extract_emails(text: str) -> list[str]:
    """
    Extract email addresses from text.

    Args:
        text: Text to search for email addresses

    Returns:
        list: List of unique email addresses found
    """
    emails = EMAIL_PATTERN.findall(text)

    # Remove duplicates while preserving order
    seen = set()
    return [x for x in emails if not (x in seen or seen.add(x))]


def extract_phones(text: str) -> list[str]:
    """
    Extract phone numbers from text.

    Args:
        text: Text to search for phone numbers

    Returns:
        list: List of unique phone numbers found
    """
    phones = PHONE_PATTERN.findall(text)

    # Remove duplicates while preserving order
    seen = set()
    return [x for x in phones if not (x in seen or seen.add(x))]


def parse_search_terms(query: str) -> list[str]:
    """
    Parse search query into terms, respecting quoted phrases.

    Args:
        query: Search query string

    Returns:
        list: List of search terms (quoted phrases as single terms)

    Example:
        >>> parse_search_terms('some "random words" with+quotes')
        ['some', 'random words', 'with+quotes']
    """
    findterms = SEARCH_TERMS_PATTERN.findall
    normspace = WHITESPACE_PATTERN.sub
    return [
        normspace(" ", (t[0] or t[1]).strip())
        for t in findterms(query)
    ]

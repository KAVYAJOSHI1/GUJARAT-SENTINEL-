import re
import logging

logger = logging.getLogger("PlateNormalizer")

# Indian State Codes mapping
INDIAN_STATES = {
    "AN", "AP", "AR", "AS", "BR", "CG", "CH", "DD", "DL", "DN",
    "GA", "GJ", "HR", "HP", "JH", "JK", "KA", "KL", "LA", "LD",
    "MH", "ML", "MN", "MP", "MZ", "NL", "OD", "OR", "PB", "PY",
    "RJ", "SK", "TN", "TR", "TS", "UK", "UP", "WB"
}

# Character replacement maps
LETTER_TO_DIGIT = {
    'O': '0', 'Q': '0', 'D': '0',
    'I': '1', 'L': '1', 'T': '1',
    'Z': '2',
    'E': '3',
    'A': '4',
    'S': '5',
    'G': '6',
    'T': '7',
    'B': '8',
    'P': '9'
}

DIGIT_TO_LETTER = {
    '0': 'O',
    '1': 'I',
    '2': 'Z',
    '3': 'E',
    '4': 'A',
    '5': 'S',
    '6': 'G',
    '7': 'T',
    '8': 'B',
    '9': 'P'
}

class PlateNormalizer:
    """
    Plate Normalization Engine for Indian license plates.
    Strips noise, normalizes text, and corrects OCR character confusion based on positional rules.
    """

    def __init__(self):
        # Regex pattern matching standard Indian vehicle registration numbers
        # e.g., GJ01AB1234, MH12DE5678, DL3C9999
        self.plate_pattern = re.compile(r'^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{1,4}$')

    def normalize(self, raw_text: str) -> str:
        """
        Clean and normalize raw OCR text string.

        :param raw_text: Raw string returned from OCR engine (e.g. "GJ-01 AB 1234", "G.J.01.AB.1234")
        :return: Cleaned alphanumeric license plate string (e.g. "GJ01AB1234")
        """
        if not raw_text:
            return "UNKNOWN"

        # 1. Uppercase & strip non-alphanumeric characters (spaces, hyphens, dots, special chars)
        clean = re.sub(r'[^A-Z0-9]', '', raw_text.upper())

        if len(clean) < 4:
            return clean if clean else "UNKNOWN"

        # 2. Positional character correction for standard 10-character Indian plate format (e.g. GJ01AB1234)
        chars = list(clean)
        n = len(chars)

        if n >= 8:
            # First 2 characters must be State letters (e.g., 'GJ')
            for i in range(2):
                if chars[i].isdigit() and chars[i] in DIGIT_TO_LETTER:
                    chars[i] = DIGIT_TO_LETTER[chars[i]]

            # Position 2 & 3 (index 2, 3) must be District digits (e.g., '01')
            for i in range(2, min(4, n)):
                if chars[i].isalpha() and chars[i] in LETTER_TO_DIGIT:
                    chars[i] = LETTER_TO_DIGIT[chars[i]]

            # Last 4 characters (or from n-4 to n) must be number digits (e.g., '1234')
            start_num_idx = max(4, n - 4)
            for i in range(start_num_idx, n):
                if chars[i].isalpha() and chars[i] in LETTER_TO_DIGIT:
                    chars[i] = LETTER_TO_DIGIT[chars[i]]

            # Middle series characters (between district code and last 4 numbers) must be letters
            for i in range(4, start_num_idx):
                if chars[i].isdigit() and chars[i] in DIGIT_TO_LETTER:
                    chars[i] = DIGIT_TO_LETTER[chars[i]]

        normalized = "".join(chars)
        return normalized

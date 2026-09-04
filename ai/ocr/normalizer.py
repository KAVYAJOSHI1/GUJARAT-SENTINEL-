import logging
from typing import List, Optional

from ai.ocr.plate_format import (
    INDIAN_STATES,
    clean,
    correct_by_position,
    expected_classes,
    format_score,
    is_valid,
)

logger = logging.getLogger("PlateNormalizer")

# Kept as module-level names for backwards compatibility with older imports.
LETTER_TO_DIGIT = {
    "O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "T": "7",
    "Z": "2", "E": "3", "A": "4", "S": "5", "G": "6", "B": "8", "P": "9",
}
DIGIT_TO_LETTER = {
    "0": "O", "1": "I", "2": "Z", "3": "E", "4": "A",
    "5": "S", "6": "G", "7": "T", "8": "B", "9": "P",
}


class PlateNormalizer:
    """
    Plate normalisation for Indian vehicle registrations.

    ``normalize()`` strips noise, uppercases, and applies **position-aware,
    class-checked** OCR-confusion correction (O<->0, I<->1, S<->5, B<->8, ...)
    ONLY where the Indian-plate format expects the other character class and
    the correction does not reduce format validity. A character that already
    matches its expected class is never rewritten -- valid letters stay letters.

    See :mod:`ai.ocr.plate_format` for the format model.
    """

    def __init__(self):
        self.states = INDIAN_STATES

    def normalize(
        self,
        raw_text: str,
        per_char_conf: Optional[List[float]] = None,
        conf_threshold: float = 0.85,
    ) -> str:
        if not raw_text:
            return "UNKNOWN"

        c = clean(raw_text)
        if len(c) < 4:
            return c if c else "UNKNOWN"

        return correct_by_position(c, per_char_conf, conf_threshold)

    # -- helpers used by the OCR engine / consensus scoring -------------- #
    def format_score(self, plate: str) -> float:
        return format_score(plate)

    def is_valid(self, plate: str):
        return is_valid(plate)

    def expected_classes(self, plate: str):
        return expected_classes(plate)

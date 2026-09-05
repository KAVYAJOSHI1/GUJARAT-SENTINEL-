"""
Indian vehicle registration-plate format model.

Standard modern format:      SS  DD  L{1,3}  NNNN
  SS   two-letter state / UT code           (GJ, MH, DL, ...)
  DD   one/two-digit RTO district code       (1, 01, 18, ...)
  L..  one to three letter series            (A, AB, TC, ...)
  NNNN one to four-digit serial number       (1, 45, 0450, 1234)

Also recognised:
  * old / short series with no letter block   SS DD NNNN
  * BH (Bharat) series                        NN BH NNNN LL   (e.g. 22BH1234AA)

This module gives, for any candidate string:
  * ``expected_classes(plate)``  -> per-character class: 'A' | 'N'
  * ``is_valid(plate)``          -> (bool, format_score 0.0-1.0)
  * ``correct_by_position(...)`` -> confidence-gated, class-aware O<->0 style fixes

Character corrections are applied ONLY where the position's expected class
disagrees with the character's class *and* (no per-char confidence supplied, or
that confidence is below a threshold) *and* a sensible swap exists. A character
that already matches its expected class is never touched, so valid letters are
not corrupted into digits (or vice-versa).
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

INDIAN_STATES = frozenset({
    "AN", "AP", "AR", "AS", "BR", "CG", "CH", "DD", "DL", "DN",
    "GA", "GJ", "HR", "HP", "JH", "JK", "KA", "KL", "LA", "LD",
    "MH", "ML", "MN", "MP", "MZ", "NL", "OD", "OR", "PB", "PY",
    "RJ", "SK", "TN", "TR", "TS", "UK", "UA", "UP", "WB", "BH",
})

# OCR confusions, split by the direction of the fix.
DIGIT_IF_ALPHA_EXPECTED_NUM = {
    "O": "0", "Q": "0", "D": "0",
    "I": "1", "L": "1",
    "Z": "2",
    "E": "3",
    "A": "4",
    "S": "5",
    "G": "6",
    "T": "7",
    "B": "8",
    "P": "9", "R": "9",
}
ALPHA_IF_DIGIT_EXPECTED_ALPHA = {
    "0": "O",
    "1": "I",
    "2": "Z",
    "4": "A",
    "5": "S",
    "6": "G",
    "8": "B",
}

_ALNUM_RE = re.compile(r"[^A-Z0-9]")
_STD_RE = re.compile(r"^([A-Z]{2})(\d{1,2})([A-Z]{1,3})(\d{1,4})$")
_SHORT_RE = re.compile(r"^([A-Z]{2})(\d{1,2})(\d{1,4})$")
_BH_RE = re.compile(r"^(\d{2})(BH)(\d{1,4})([A-Z]{1,2})$")


def clean(raw: Optional[str]) -> str:
    return _ALNUM_RE.sub("", (raw or "").upper())


def _std_layout(n: int) -> Optional[List[str]]:
    """Per-char class for a standard SS DD L.. NNNN string of length n.

    Assumes 2 state + 2 district + 4 number, letters fill the middle. Falls
    back to 2+1 district if that is the only way to leave room for a letter.
    """
    if n < 5 or n > 11:
        return None
    # try district=2 then district=1
    for dd in (2, 1):
        letters = n - 4 - 2 - dd
        if 1 <= letters <= 3:
            return ["A", "A"] + ["N"] * dd + ["A"] * letters + ["N"] * 4
    # short number (<4): keep 2+2 district, 1-3 letters, remainder number
    for dd in (2, 1):
        for nn in (3, 2, 1):
            letters = n - nn - 2 - dd
            if 1 <= letters <= 3:
                return ["A", "A"] + ["N"] * dd + ["A"] * letters + ["N"] * nn
    return None


def expected_classes(plate: str) -> List[str]:
    """Best-fit per-character expected class ('A' or 'N'). '' entries mean 'unknown'."""
    p = clean(plate)
    n = len(p)
    if n == 0:
        return []
    if _BH_RE.match(p):
        return ["N", "N", "A", "A"] + ["N"] * (n - 6) + ["A"] * 2
    layout = _std_layout(n)
    if layout:
        return layout
    if _SHORT_RE.match(p) or n <= 6:
        return ["A", "A"] + ["N"] * (n - 2)
    return ["?"] * n


def is_valid(plate: str) -> Tuple[bool, float]:
    """Return (strictly_valid, format_score in [0,1])."""
    p = clean(plate)
    if not p:
        return False, 0.0
    m = _STD_RE.match(p)
    if m:
        state_ok = m.group(1) in INDIAN_STATES
        return (state_ok, 1.0 if state_ok else 0.75)
    if _BH_RE.match(p):
        return True, 0.9
    if _SHORT_RE.match(p):
        state_ok = _SHORT_RE.match(p).group(1) in INDIAN_STATES
        return (state_ok, 0.85 if state_ok else 0.6)
    # partial credit: right length + starts with 2 letters + ends with digits
    score = 0.0
    if 6 <= len(p) <= 11:
        score += 0.2
    if p[:2].isalpha():
        score += 0.2
        if p[:2] in INDIAN_STATES:
            score += 0.15
    if p[-1:].isdigit():
        score += 0.15
    return False, round(min(score, 0.7), 3)


def format_score(plate: str) -> float:
    return is_valid(plate)[1]


# A genuine plate misread is a small number of character confusions. The more
# position-swaps it takes to force a string into plate shape, the more likely
# the string is NOT a misread plate at all (a dictionary word, a timestamp
# overlay, a partial/garbage OCR box) and "correcting" it would be
# fabricating a plate from nothing:
#   * up to _CORR_SOFT swaps           -> accepted if they don't lower the
#                                         format score (the original rule)
#   * _CORR_SOFT+1 .. _CORR_HARD swaps -> accepted ONLY if the result
#                                         STRICTLY validates (real state code
#                                         + exact standard/short/BH layout) --
#                                         a real multi-error plate still
#                                         lands here, random text almost never
#                                         does
#   * more than _CORR_HARD swaps       -> never; leave it to cross-frame
#                                         consensus, don't single-frame rewrite
_CORR_SOFT = 1
_CORR_HARD = 3


def correct_by_position(
    plate: str,
    per_char_conf: Optional[List[float]] = None,
    conf_threshold: float = 0.85,
) -> str:
    """Class-aware, confidence-gated character correction.

    A character is swapped only when: its class != the expected class for that
    position, a swap mapping exists, and (no confidence array is given, or the
    character's confidence is below ``conf_threshold``).

    Bounded: at most ``_MAX_POSITION_CORRECTIONS`` characters are ever
    rewritten -- if more than that would need swapping, the original cleaned
    string is returned untouched rather than fabricated into plate shape.
    """
    p = clean(plate)
    if len(p) < 5:
        return p
    exp = expected_classes(p)
    if len(exp) != len(p):
        return p

    out = list(p)
    corrections = 0
    for i, (ch, want) in enumerate(zip(out, exp)):
        if want not in ("A", "N"):
            continue
        conf = per_char_conf[i] if (per_char_conf and i < len(per_char_conf)) else None
        if conf is not None and conf >= conf_threshold:
            continue  # OCR was confident -> trust it
        if want == "N" and ch.isalpha() and ch in DIGIT_IF_ALPHA_EXPECTED_NUM:
            out[i] = DIGIT_IF_ALPHA_EXPECTED_NUM[ch]
            corrections += 1
        elif want == "A" and ch.isdigit() and ch in ALPHA_IF_DIGIT_EXPECTED_ALPHA:
            out[i] = ALPHA_IF_DIGIT_EXPECTED_ALPHA[ch]
            corrections += 1

    if corrections == 0:
        return p
    corrected = "".join(out)

    if corrections <= _CORR_SOFT:
        # original rule: accept as long as it did not make the string less valid
        if format_score(corrected) + 1e-9 >= format_score(p):
            return corrected
        return p
    if corrections <= _CORR_HARD and is_valid(corrected)[0]:
        # several disagreements, but the result is a strictly valid plate
        # (real state + exact layout) -- a genuine multi-error read
        return corrected
    return p  # too many disagreements / not strictly valid -> don't fabricate

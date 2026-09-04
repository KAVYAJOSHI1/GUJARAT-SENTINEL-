import os
import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("OCREngine")

# Crops smaller than this are never worth an OCR call.
_MIN_H, _MIN_W = 12, 24


class OCREngine:
    """
    License-plate OCR with two interchangeable backends:

      * ``easyocr``   -- default. Stable across environments, ships a small
                         CPU model, no fragile paddlepaddle runtime.
      * ``paddleocr`` -- optional. Enable with ``OCR_ENGINE=paddleocr`` (or
                         ``OCR_ENGINE=auto`` to keep it only as a fallback).
                         Result parsing supports both the 2.x ``.ocr()`` list
                         format and the 3.x ``.predict()`` dict format.

    Backends are initialised lazily on the first :meth:`extract_text` call so
    constructing an ``OCREngine`` (and therefore an ``AIPipeline``) stays cheap.

    If the active backend raises at *inference* time it is permanently
    disabled for this instance and the other backend is tried -- this is the
    behaviour the old implementation was missing (it only fell back when
    PaddleOCR failed to *import*, never when it crashed mid-inference, which
    is exactly what PaddleOCR 3.7 + paddle 3.3 does on CPU).

    Return contract is unchanged: ``{"raw_text": str, "confidence": float}``,
    with ``{"raw_text": "UNKNOWN", "confidence": 0.0}`` when nothing readable
    is produced. Character/normalisation cleanup stays in
    :class:`ai.ocr.normalizer.PlateNormalizer`.
    """

    def __init__(
        self,
        lang: str = "en",
        use_angle_cls: bool = False,
        engine: Optional[str] = None,
    ):
        self.lang = lang
        self.use_angle_cls = use_angle_cls
        # "easyocr" (default) | "paddleocr" | "auto"
        self.preferred = (engine or os.getenv("OCR_ENGINE", "easyocr")).strip().lower()
        if self.preferred not in ("easyocr", "paddleocr", "auto"):
            logger.warning("Unknown OCR_ENGINE=%r, falling back to 'easyocr'.", self.preferred)
            self.preferred = "easyocr"

        self._easy = None
        self._paddle = None
        self._easy_disabled = False
        self._paddle_disabled = False
        self._initialised = False
        self.active_engine: str = "uninitialised"

    # ------------------------------------------------------------------ #
    #  lazy backend initialisation                                        #
    # ------------------------------------------------------------------ #
    def _init_easy(self) -> None:
        if self._easy is not None or self._easy_disabled:
            return
        try:
            import easyocr  # noqa: PLC0415 -- optional heavy dep, import on demand

            logger.info("Initialising EasyOCR (lang=%s, cpu)...", self.lang)
            try:
                self._easy = easyocr.Reader([self.lang], gpu=False, verbose=False)
            except TypeError:  # very old easyocr without verbose kwarg
                self._easy = easyocr.Reader([self.lang], gpu=False)
            logger.info("EasyOCR ready.")
        except Exception as exc:  # noqa: BLE001 -- any failure => backend unavailable
            self._easy_disabled = True
            logger.warning("EasyOCR unavailable (%s).", exc)

    def _init_paddle(self) -> None:
        if self._paddle is not None or self._paddle_disabled:
            return
        try:
            from paddleocr import PaddleOCR  # noqa: PLC0415

            logger.info("Initialising PaddleOCR (lang=%s)...", self.lang)
            try:
                self._paddle = PaddleOCR(
                    lang=self.lang, use_angle_cls=self.use_angle_cls, show_log=False
                )
            except TypeError:
                # PaddleOCR 3.x dropped use_angle_cls / show_log kwargs.
                self._paddle = PaddleOCR(lang=self.lang)
            logger.info("PaddleOCR ready.")
        except Exception as exc:  # noqa: BLE001
            self._paddle_disabled = True
            logger.warning("PaddleOCR unavailable (%s).", exc)

    def _ensure_init(self) -> None:
        if self._initialised:
            return
        self._initialised = True
        if self.preferred == "paddleocr":
            self._init_paddle()
            self._init_easy()          # always keep EasyOCR as the fallback
        elif self.preferred == "auto":
            self._init_easy()
            self._init_paddle()
        else:                          # "easyocr"
            self._init_easy()
        self._recompute_active()

    def _recompute_active(self) -> None:
        if self.preferred == "paddleocr" and self._paddle is not None:
            self.active_engine = "paddleocr"
        elif self._easy is not None:
            self.active_engine = "easyocr"
        elif self._paddle is not None:
            self.active_engine = "paddleocr"
        else:
            self.active_engine = "none"

    # ------------------------------------------------------------------ #
    #  result parsing (tolerant to library version differences)           #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _parse_easy(results: Any) -> Tuple[List[str], List[float]]:
        parts: List[str] = []
        confs: List[float] = []
        for item in results or []:
            # EasyOCR returns (bbox, text, confidence)
            if isinstance(item, (list, tuple)) and len(item) >= 3:
                parts.append(str(item[1]))
                try:
                    confs.append(float(item[2]))
                except (TypeError, ValueError):
                    confs.append(0.0)
        return parts, confs

    @staticmethod
    def _parse_paddle(results: Any) -> Tuple[List[str], List[float]]:
        parts: List[str] = []
        confs: List[float] = []
        if not results:
            return parts, confs

        # PaddleOCR 3.x: predict() -> list[OCRResult(dict-like)] with rec_texts/rec_scores
        head = results[0] if isinstance(results, (list, tuple)) and results else results
        if isinstance(head, dict):
            texts = head.get("rec_texts") or head.get("texts") or []
            scores = head.get("rec_scores") or head.get("scores") or []
            for i, text in enumerate(texts):
                parts.append(str(text))
                try:
                    confs.append(float(scores[i]))
                except (TypeError, ValueError, IndexError):
                    confs.append(0.0)
            return parts, confs

        # PaddleOCR 2.x: ocr() -> [ [ [bbox, (text, conf)], ... ] ]
        block = results[0] if isinstance(results, (list, tuple)) else results
        for line in block or []:
            if line and len(line) >= 2 and line[1] is not None:
                try:
                    parts.append(str(line[1][0]))
                    confs.append(float(line[1][1]))
                except (TypeError, ValueError, IndexError):
                    continue
        return parts, confs

    def _run_paddle(self, image: np.ndarray) -> Tuple[List[str], List[float]]:
        try:
            res = self._paddle.predict(image)          # 3.x
        except (AttributeError, TypeError):
            res = self._paddle.ocr(image)               # 2.x
        return self._parse_paddle(res)

    def _run_easy(self, image: np.ndarray) -> Tuple[List[str], List[float]]:
        return self._parse_easy(self._easy.readtext(image))

    # ------------------------------------------------------------------ #
    #  public API                                                         #
    # ------------------------------------------------------------------ #
    def extract_best(
        self,
        images: List[np.ndarray],
        normalizer: Any = None,
    ) -> Dict[str, Any]:
        """Run OCR on several preprocessing variants and return the best read.

        Scoring per variant:  ``ocr_conf * (0.4 + 0.6 * format_score(normalised))``
        so a well-formed Indian plate at medium confidence beats a garbage
        string at high confidence. Empty ``images`` (quality gate failed) ->
        ``UNKNOWN``.
        """
        if not images:
            return {"raw_text": "UNKNOWN", "confidence": 0.0, "variant": -1, "format_score": 0.0}

        best = {"raw_text": "UNKNOWN", "confidence": 0.0, "variant": -1, "format_score": 0.0}
        best_score = -1.0
        for idx, img in enumerate(images):
            res = self.extract_text(img)
            raw = res.get("raw_text", "UNKNOWN")
            conf = float(res.get("confidence", 0.0))
            if raw == "UNKNOWN":
                continue
            fmt = 0.0
            if normalizer is not None:
                try:
                    fmt = float(normalizer.format_score(normalizer.normalize(raw)))
                except Exception:  # noqa: BLE001
                    fmt = 0.0
            score = conf * (0.4 + 0.6 * fmt)
            if score > best_score:
                best_score = score
                best = {"raw_text": raw, "confidence": round(conf, 4),
                        "variant": idx, "format_score": round(fmt, 3)}
        return best

    def extract_text(self, image: np.ndarray) -> Dict[str, Any]:
        """
        Run OCR on a (preprocessed) license-plate crop.

        :param image: BGR / grayscale numpy array
        :return: ``{"raw_text": str, "confidence": float}`` -- ``raw_text`` is
                 ``"UNKNOWN"`` (confidence 0.0) when no readable text is found.
        """
        if image is None or getattr(image, "size", 0) == 0:
            return {"raw_text": "UNKNOWN", "confidence": 0.0}
        if len(getattr(image, "shape", ())) < 2:
            return {"raw_text": "UNKNOWN", "confidence": 0.0}

        h, w = image.shape[:2]
        if h < _MIN_H or w < _MIN_W:
            return {"raw_text": "UNKNOWN", "confidence": 0.0}

        self._ensure_init()

        # backend attempt order -- primary first, other as runtime fallback
        order = ["paddleocr", "easyocr"] if self.preferred == "paddleocr" else ["easyocr", "paddleocr"]

        for backend in order:
            if backend == "easyocr":
                if self._easy is None:
                    continue
                try:
                    parts, confs = self._run_easy(image)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("EasyOCR inference failed (%s); disabling EasyOCR backend.", exc)
                    self._easy = None
                    self._easy_disabled = True
                    self._recompute_active()
                    continue
            else:
                if self._paddle is None:
                    continue
                try:
                    parts, confs = self._run_paddle(image)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("PaddleOCR inference failed (%s); disabling PaddleOCR backend.", exc)
                    self._paddle = None
                    self._paddle_disabled = True
                    self._recompute_active()
                    continue

            raw = " ".join(p for p in parts if p).strip()
            if raw:
                conf = round(sum(confs) / len(confs), 4) if confs else 0.0
                return {"raw_text": raw, "confidence": float(conf)}

        return {"raw_text": "UNKNOWN", "confidence": 0.0}

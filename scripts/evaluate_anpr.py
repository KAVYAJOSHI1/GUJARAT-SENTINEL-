#!/usr/bin/env python3
"""
ANPR / OCR evaluation utility.

Runs the real pipeline stages (plate localisation -> quality gate ->
multi-variant preprocessing -> OCR -> normalisation -> Indian-format check)
against a labelled dataset and reports:

  * plate-localisation success rate
  * OCR-produced-a-string rate
  * exact plate accuracy
  * character-level accuracy
  * UNKNOWN rate
  * mean OCR latency

Datasets:
  --dataset PATH   a directory of images whose file name is the ground-truth
                   plate ("GJ18TC0450.jpg"), OR a JSON list
                   [{"image": "...", "plate": "GJ18TC0450"}, ...]

  (no --dataset)   a SYNTHETIC set is generated on the fly. Its numbers
                   describe OCR on rendered fonts, NOT real CCTV -- they are
                   clearly labelled and must not be quoted as real accuracy.

Usage:
  .venv/bin/python scripts/evaluate_anpr.py
  .venv/bin/python scripts/evaluate_anpr.py --dataset data/anpr_samples
"""
import argparse
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from ai.anpr.plate_locator import PlateLocator  # noqa: E402
from ai.anpr.preprocess import ImagePreprocessor  # noqa: E402
from ai.ocr.normalizer import PlateNormalizer  # noqa: E402
from ai.ocr.ocr_engine import OCREngine  # noqa: E402


def _char_accuracy(pred: str, truth: str) -> float:
    if not truth:
        return 0.0
    n = max(len(pred), len(truth))
    same = sum(1 for i in range(min(len(pred), len(truth))) if pred[i] == truth[i])
    return same / n


def _render_plate(text, w=560, h=150):
    img = np.full((h, w, 3), 255, np.uint8)
    cv2.rectangle(img, (4, 4), (w - 5, h - 5), (0, 0, 0), 4)
    f = cv2.FONT_HERSHEY_SIMPLEX
    (tw, th), _ = cv2.getTextSize(text, f, 2.6, 6)
    cv2.putText(img, text, ((w - tw) // 2, (h + th) // 2), f, 2.6, (0, 0, 0), 6, cv2.LINE_AA)
    return img


def _synthetic_dataset(n=24):
    states = ["GJ", "MH", "DL", "KA", "RJ", "TN", "UP", "HR"]
    rng = np.random.default_rng(7)
    out = []
    for i in range(n):
        s = states[i % len(states)]
        d = f"{rng.integers(1, 40):02d}"
        letters = "".join(chr(65 + int(x)) for x in rng.integers(0, 26, size=rng.integers(1, 4)))
        num = f"{rng.integers(1, 10000):04d}"
        plate = f"{s}{d}{letters}{num}"
        img = _render_plate(plate)
        # drop it into a scene so the locator has real work to do
        scene = np.full((360, 640, 3), 90, np.uint8)
        scene[:] = rng.integers(40, 130, size=3)
        ph, pw = 90, 336
        pr = cv2.resize(img, (pw, ph))
        y, x = 180, 150
        scene[y:y + ph, x:x + pw] = pr
        out.append((scene, plate, [x, y, x + pw, y + ph]))
    return out


def _load_dataset(path):
    items = []
    if os.path.isdir(path):
        for fn in sorted(os.listdir(path)):
            if fn.lower().endswith((".jpg", ".jpeg", ".png")):
                plate = os.path.splitext(fn)[0].upper()
                img = cv2.imread(os.path.join(path, fn))
                if img is not None:
                    items.append((img, plate, None))
    else:
        with open(path) as f:
            for row in json.load(f):
                img = cv2.imread(row["image"])
                if img is not None:
                    items.append((img, row["plate"].upper(), row.get("bbox")))
    return items


def evaluate(items, real: bool):
    loc = PlateLocator()
    pre = ImagePreprocessor()
    eng = OCREngine()
    nz = PlateNormalizer()

    total = len(items)
    localised = ocr_produced = exact = unknown = 0
    char_accs, latencies = [], []

    for img, truth, bbox in items:
        crop = img[bbox[1]:bbox[3], bbox[0]:bbox[2]] if bbox else img
        lr = loc.locate_plate(crop)
        plate_crop = lr["plate_crop"]
        if plate_crop is not None and plate_crop.size and lr["confidence"] > 0.0:
            localised += 1

        variants = pre.variants(plate_crop)
        t0 = time.time()
        res = eng.extract_best(variants, nz) if variants else {"raw_text": "UNKNOWN", "confidence": 0.0}
        latencies.append((time.time() - t0) * 1000.0)

        pred = nz.normalize(res["raw_text"])
        if pred == "UNKNOWN":
            unknown += 1
        else:
            ocr_produced += 1
            if pred == truth:
                exact += 1
            char_accs.append(_char_accuracy(pred, truth))

    def pct(x):
        return round(100.0 * x / total, 1) if total else 0.0

    print("=" * 66)
    print(" ANPR / OCR EVALUATION  —  " + ("REAL CCTV SAMPLES" if real else "SYNTHETIC (rendered fonts)"))
    print("=" * 66)
    if not real:
        print(" NOTE: synthetic rendered plates are OUT OF DISTRIBUTION for the")
        print("       OCR model. These numbers characterise the pipeline wiring,")
        print("       NOT real Sentinel/CCTV ANPR accuracy. Do not quote as real.")
        print("-" * 66)
    print(f" samples ............... {total}")
    print(f" plate localised ....... {localised}/{total}  ({pct(localised)}%)")
    print(f" OCR produced a plate .. {ocr_produced}/{total}  ({pct(ocr_produced)}%)")
    print(f" exact plate accuracy .. {exact}/{total}  ({pct(exact)}%)")
    print(f" character accuracy .... {round(100 * statistics.mean(char_accs), 1) if char_accs else 0.0}%")
    print(f" UNKNOWN rate .......... {unknown}/{total}  ({pct(unknown)}%)")
    print(f" mean OCR latency ...... {round(statistics.mean(latencies), 1) if latencies else 0.0} ms")
    print("=" * 66)
    return {"total": total, "exact": exact, "unknown": unknown}


def main():
    ap = argparse.ArgumentParser(description="ANPR / OCR evaluation")
    ap.add_argument("--dataset", help="image dir (plate=filename) or JSON manifest")
    ap.add_argument("--n", type=int, default=24, help="synthetic sample count")
    args = ap.parse_args()

    if args.dataset:
        items = _load_dataset(args.dataset)
        if not items:
            print(f"no usable samples in {args.dataset}")
            sys.exit(2)
        evaluate(items, real=True)
    else:
        print("no --dataset given -> generating a SYNTHETIC evaluation set\n")
        evaluate(_synthetic_dataset(args.n), real=False)


if __name__ == "__main__":
    main()

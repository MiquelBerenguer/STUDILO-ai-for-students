"""Local OCR (RapidOCR / PaddleOCR models on ONNX) with image preprocessing and quality metrics."""

from __future__ import annotations

import io
import logging
import threading
from dataclasses import asdict, dataclass

import cv2
import numpy as np
from PIL import Image, ImageOps

log = logging.getLogger("studilo.ocr")

try:  # HEIC support for iPhone photos
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:  # pragma: no cover - dependency is declared; guard keeps import errors explicit
    log.warning("pillow-heif not installed: HEIC uploads will fail")

MATH_CHARS = set("=+−×÷^_∫∑∏√≈≠≤≥∂∆Δ∇πθαβγλμσωΩ∞±→⇒·′∈∀∃")


@dataclass
class OcrResult:
    text: str
    mean_confidence: float
    low_conf_ratio: float
    lines: int
    math_density: float
    equation_line_ratio: float
    ink_ratio: float
    ink_outside_text_ratio: float
    deskew_angle: float

    def metrics(self) -> dict[str, float | int]:
        d = asdict(self)
        d.pop("text")
        return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in d.items()}


def load_image(data: bytes) -> np.ndarray:
    """Decode any supported image (incl. HEIC), honour EXIF orientation, return BGR ndarray."""
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img).convert("RGB")
    return cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)


def encode_png(img: np.ndarray, max_side: int = 2000) -> bytes:
    h, w = img.shape[:2]
    scale = min(1.0, max_side / max(h, w))
    if scale < 1.0:
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise ValueError("could not encode image")
    return buf.tobytes()


def preprocess(img: np.ndarray) -> tuple[np.ndarray, float]:
    """Grayscale → downscale → deskew → CLAHE contrast. Returns (BGR image, deskew angle)."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    h, w = gray.shape
    scale = min(1.0, 2400 / max(h, w))
    if scale < 1.0:
        gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    angle = _skew_angle(gray)
    if 0.5 <= abs(angle) <= 15:
        hh, ww = gray.shape
        m = cv2.getRotationMatrix2D((ww / 2, hh / 2), angle, 1.0)
        gray = cv2.warpAffine(gray, m, (ww, hh), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR), angle


def _skew_angle(gray: np.ndarray) -> float:
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    coords = np.column_stack(np.where(bw > 0))
    if len(coords) < 500:
        return 0.0
    angle = float(cv2.minAreaRect(coords[:, ::-1].astype(np.float32))[-1])
    return ((angle + 45) % 90) - 45  # OpenCV versions disagree on the range; normalise to [-45, 45)


_engine = None
_engine_lock = threading.Lock()


def _get_engine():  # type: ignore[no-untyped-def]  # RapidOCR has no type stubs
    global _engine
    with _engine_lock:
        if _engine is None:
            from rapidocr_onnxruntime import RapidOCR

            _engine = RapidOCR()
    return _engine


def run_ocr(img: np.ndarray) -> OcrResult:
    processed, angle = preprocess(img)
    result, _ = _get_engine()(processed)
    items = [(np.array(box, dtype=np.float32), str(txt), float(score)) for box, txt, score in (result or [])]
    gray = cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY)
    _, ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    ink_total = int((ink > 0).sum())
    ink_ratio = ink_total / ink.size
    mask = np.zeros_like(ink)
    for box, _, _ in items:
        cv2.fillPoly(mask, [box.astype(np.int32)], 255)
    ink_outside = int(((ink > 0) & (mask == 0)).sum())
    ink_outside_ratio = ink_outside / ink_total if ink_total else 0.0

    if not items:
        return OcrResult("", 0.0, 1.0, 0, 0.0, 0.0, ink_ratio, ink_outside_ratio, angle)
    total_len = sum(max(1, len(t)) for _, t, _ in items)
    mean_conf = sum(s * max(1, len(t)) for _, t, s in items) / total_len
    low_conf = sum(1 for _, _, s in items if s < 0.7) / len(items)
    text = _assemble(items)
    nonspace = [c for c in text if not c.isspace()]
    math_density = sum(1 for c in nonspace if c in MATH_CHARS) / max(1, len(nonspace))
    eq_lines = sum(1 for _, t, _ in items if "=" in t or sum(t.count(c) for c in MATH_CHARS) >= 2)
    return OcrResult(text, mean_conf, low_conf, len(items), math_density, eq_lines / len(items),
                     ink_ratio, ink_outside_ratio, angle)


def _assemble(items: list[tuple[np.ndarray, str, float]]) -> str:
    """Order boxes top-to-bottom, left-to-right; blank line on large vertical gaps (paragraphs)."""
    rows = sorted(items, key=lambda it: (float(it[0][:, 1].min()), float(it[0][:, 0].min())))
    heights = [float(b[:, 1].max() - b[:, 1].min()) for b, _, _ in rows]
    med_h = float(np.median(heights)) if heights else 10.0
    lines: list[list[tuple[float, str]]] = []
    last_top: float | None = None
    last_bottom = 0.0
    out: list[str] = []
    for (box, txt, _), _h in zip(rows, heights, strict=True):
        top, bottom, left = float(box[:, 1].min()), float(box[:, 1].max()), float(box[:, 0].min())
        if last_top is not None and abs(top - last_top) < med_h * 0.5:
            lines[-1].append((left, txt))
        else:
            if lines and top - last_bottom > med_h * 1.2:
                lines.append([])  # paragraph break marker
            lines.append([(left, txt)])
            last_top = top
        last_bottom = max(last_bottom, bottom)
    for line in lines:
        out.append(" ".join(t for _, t in sorted(line)) if line else "")
    return "\n".join(out).strip()

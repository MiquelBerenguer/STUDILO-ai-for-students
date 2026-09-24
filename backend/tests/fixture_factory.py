"""Deterministic generators for ingestion fixtures (no binary blobs to maintain)."""

from __future__ import annotations

import io

import cv2
import numpy as np
import pymupdf
from PIL import Image, ImageDraw, ImageFont

PROSE = [
    "First law of thermodynamics",
    "The first law states that energy is conserved in a closed system.",
    "Heat added to the system equals the change in internal energy",
    "plus the work done by the system on its surroundings.",
    "We studied closed systems and the sign convention for heat and work.",
    "The professor solved an example with a piston and a gas at constant pressure.",
]
EQUATIONS = ["dU = dQ - dW", "W = ∫ p dV = p (V2 - V1)", "Q = m c ΔT", "η = 1 - T_c / T_h",
             "s2 - s1 = c_p ln(T2/T1) - R ln(p2/p1)", "Δh = q - w"]


def render_lines(lines: list[str], size: int = 34, w: int = 1600, h: int = 1100) -> Image.Image:
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=size)
    y = 60
    for line in lines:
        d.text((60, y), line, fill="black", font=font)
        y += int(size * 1.6)
    return img


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def text_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    body = ("# Primera llei de la termodinàmica\n\n" + " ".join(PROSE) + "\n\n"
            "La energía interna de un sistema cerrado cambia cuando el sistema intercambia calor o trabajo "
            "con su entorno. En clase vimos el convenio de signos y un ejemplo con un pistón.")
    page.insert_textbox(pymupdf.Rect(50, 50, 550, 800), body, fontsize=11)
    return doc.tobytes()


def garbled_pdf() -> bytes:
    """Correct glyphs on the page, but a garbage text layer (like a broken font encoding / bad OCR layer)."""
    doc = pymupdf.open()
    page = doc.new_page(width=800, height=550)
    page.insert_image(page.rect, stream=_png(render_lines(PROSE)))
    gibberish = " ".join("xqzv kjhw pqlm trbn wqzx vbnq" for _ in range(20))
    page.insert_textbox(pymupdf.Rect(20, 20, 780, 530), gibberish, fontsize=9, render_mode=3)  # invisible text
    return doc.tobytes()


def scanned_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=800, height=550)
    page.insert_image(page.rect, stream=_png(render_lines(PROSE)))
    return doc.tobytes()


def handwriting_photo() -> bytes:
    """Blurry, noisy, rotated, low-contrast phone photo: local OCR confidence drops → vision escalation."""
    img = cv2.cvtColor(np.array(render_lines(PROSE, size=30)), cv2.COLOR_RGB2BGR)
    rng = np.random.default_rng(0)
    img = cv2.GaussianBlur(img, (0, 0), 2.2)
    img = np.clip(img * 0.6 + 80 + rng.normal(0, 45, img.shape), 0, 255).astype(np.uint8)
    h, w = img.shape[:2]
    img = cv2.warpAffine(img, cv2.getRotationMatrix2D((w / 2, h / 2), 4, 1), (w, h), borderValue=(200, 200, 200))
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    assert ok
    return buf.tobytes()


def equation_page() -> bytes:
    return _png(render_lines(EQUATIONS))


def clean_photo() -> bytes:
    return _png(render_lines(PROSE))

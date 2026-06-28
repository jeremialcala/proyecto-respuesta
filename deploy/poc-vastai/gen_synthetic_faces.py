#!/usr/bin/env python3
"""Generador de caras SINTÉTICAS (sin PII) para el PoC del plano de inferencia (ADR-0019 §6).

Dibuja rostros esquemáticos reproducibles (semilla fija) para alimentar el harness sin usar datos
reales. Cada imagen lleva un rostro frontal simple (óvalo + ojos + nariz + boca) con jitter de posición,
tamaño y color sobre un fondo con ruido suave.

IMPORTANTE — representatividad: SCRFD (el detector de InsightFace) puede o no detectar estos rostros
dibujados. Sirven para medir **cold-start, transporte y el camino de detección**. Para números
representativos de la **etapa de embedding**, usa rostros sintéticos foto-realistas (GAN, p. ej.
"thispersondoesnotexist") o datos **consentidos** — nunca PII real (ADR-0019 §5/§6). El harness reporta
la tasa de detección (`faces>0`) para que veas cuántos se detectaron.

Uso:
    pip install -r requirements.txt
    python gen_synthetic_faces.py --count 200 --size 640 --out ./synthetic
"""
from __future__ import annotations

import argparse
import os
import random


def _draw_face(size: int, rng: random.Random):
    from PIL import Image, ImageDraw  # dependencia del PoC (requirements.txt)

    # Fondo con ruido suave.
    bg = (rng.randint(40, 90), rng.randint(40, 90), rng.randint(40, 90))
    img = Image.new("RGB", (size, size), bg)
    px = img.load()
    for _ in range(size * size // 8):
        x, y = rng.randrange(size), rng.randrange(size)
        v = rng.randint(0, 60)
        px[x, y] = (min(255, bg[0] + v), min(255, bg[1] + v), min(255, bg[2] + v))

    d = ImageDraw.Draw(img)
    # Cara: óvalo centrado con jitter.
    fw = rng.randint(int(size * 0.35), int(size * 0.55))
    fh = int(fw * rng.uniform(1.15, 1.35))
    cx = size // 2 + rng.randint(-size // 12, size // 12)
    cy = size // 2 + rng.randint(-size // 12, size // 12)
    skin = (rng.randint(150, 230), rng.randint(120, 190), rng.randint(100, 160))
    x1, y1, x2, y2 = cx - fw // 2, cy - fh // 2, cx + fw // 2, cy + fh // 2
    d.ellipse([x1, y1, x2, y2], fill=skin, outline=(0, 0, 0))

    # Ojos.
    eye_y = cy - fh // 8
    eye_dx = fw // 4
    er = max(3, fw // 14)
    for sx in (-1, 1):
        ex = cx + sx * eye_dx
        d.ellipse([ex - er, eye_y - er, ex + er, eye_y + er], fill=(255, 255, 255), outline=(0, 0, 0))
        pr = max(1, er // 2)
        d.ellipse([ex - pr, eye_y - pr, ex + pr, eye_y + pr], fill=(20, 20, 20))
    # Nariz.
    d.line([cx, eye_y + er, cx, cy + fh // 10], fill=(0, 0, 0), width=max(1, fw // 30))
    # Boca.
    mw = fw // 3
    my = cy + fh // 5
    d.arc([cx - mw, my - mw // 2, cx + mw, my + mw // 2], start=10, end=170, fill=(120, 40, 40),
          width=max(2, fw // 25))
    return img


def main() -> None:
    ap = argparse.ArgumentParser(description="Genera caras sintéticas (sin PII) para el PoC ADR-0019.")
    ap.add_argument("--count", type=int, default=200, help="número de imágenes")
    ap.add_argument("--size", type=int, default=640, help="lado en píxeles (cuadrada)")
    ap.add_argument("--out", default="./synthetic", help="directorio de salida")
    ap.add_argument("--seed", type=int, default=1234, help="semilla (reproducible)")
    ap.add_argument("--quality", type=int, default=85, help="calidad JPEG")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    rng = random.Random(args.seed)
    for i in range(args.count):
        img = _draw_face(args.size, rng)
        img.save(os.path.join(args.out, f"synthetic_{i:05d}.jpg"), "JPEG", quality=args.quality)
    print(f"generadas {args.count} caras sintéticas en {args.out} ({args.size}x{args.size})")


if __name__ == "__main__":
    main()

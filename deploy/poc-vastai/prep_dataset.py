#!/usr/bin/env python3
"""Prepara un dataset de rostros para la corrida REAL del PoC (ADR-0019).

Fuentes soportadas:
  - `fairface` : HuggingFaceM4/FairFace vía `datasets` (streaming; descarga solo --max). Rostros REALES.
  - `ffhq`     : mirror FFHQ en HF (merkol/ffhq-256) vía `datasets` (streaming). Rostros REALES.
  - `dir`      : un directorio local de imágenes (p. ej. un subconjunto de FFHQ ya descargado). REALES.
  - `gan`      : caras GAN SINTÉTICAS desde un dir local (alineado con ADR-0019 §6, sin PII real).

Todas las imágenes se **redimensionan** (lado máximo `--size`) y se reexportan a JPEG → minimiza el
egress hacia el nodo de inferencia (ADR-0019 §4: enviar el mínimo). El harness luego apunta a `--out`.

> Aviso (ADR-0019 §5/§6): `fairface`/`dir`(FFHQ) son **biometría real de personas reales**. Úsalas solo
> para el PoC técnico con el egress condicionado a tu validación legal. `gan` evita ese riesgo.

Uso:
    pip install -r requirements-prep.txt
    python prep_dataset.py --source fairface --max 500 --size 512 --out ./faces-fairface
    python prep_dataset.py --source dir --src /ruta/ffhq-subset --max 500 --size 512 --out ./faces-ffhq
"""
from __future__ import annotations

import argparse
import os


def _save_resized(img, size: int, path: str, quality: int = 90) -> None:
    from PIL import Image
    img = img.convert("RGB")
    w, h = img.size
    if max(w, h) > size:
        if w >= h:
            img = img.resize((size, int(h * size / w)), Image.LANCZOS)
        else:
            img = img.resize((int(w * size / h), size), Image.LANCZOS)
    img.save(path, "JPEG", quality=quality)


def _from_fairface(out: str, size: int, max_n: int) -> int:
    from datasets import load_dataset
    # streaming → no baja el dataset completo; "1.25" = recorte con padding (rostro completo).
    ds = load_dataset("HuggingFaceM4/FairFace", "1.25", split="train", streaming=True)
    n = 0
    for ex in ds:
        if n >= max_n:
            break
        _save_resized(ex["image"], size, os.path.join(out, f"fairface_{n:05d}.jpg"))
        n += 1
    return n


def _from_ffhq(out: str, size: int, max_n: int) -> int:
    from datasets import load_dataset
    # streaming → no baja el dataset completo. merkol/ffhq-256: FFHQ real (256px), columna `image`.
    ds = load_dataset("merkol/ffhq-256", split="train", streaming=True)
    n = 0
    for ex in ds:
        if n >= max_n:
            break
        _save_resized(ex["image"], size, os.path.join(out, f"ffhq_{n:05d}.jpg"))
        n += 1
    return n


def _from_dir(src: str, out: str, size: int, max_n: int, prefix: str) -> int:
    from PIL import Image
    exts = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
    files = sorted(f for f in os.listdir(src) if f.lower().endswith(exts))[:max_n]
    n = 0
    for f in files:
        try:
            with Image.open(os.path.join(src, f)) as img:
                _save_resized(img, size, os.path.join(out, f"{prefix}_{n:05d}.jpg"))
            n += 1
        except Exception as e:  # imagen corrupta → se omite
            print(f"  omitida {f}: {e}")
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description="Prepara rostros para el PoC real ADR-0019.")
    ap.add_argument("--source", choices=["fairface", "ffhq", "dir", "gan"], required=True)
    ap.add_argument("--src", help="directorio de origen (para --source dir|gan, p. ej. FFHQ descargado)")
    ap.add_argument("--max", type=int, default=500, help="número máximo de imágenes")
    ap.add_argument("--size", type=int, default=512, help="lado máximo en píxeles (minimiza egress)")
    ap.add_argument("--out", required=True, help="directorio de salida (apúntalo en el harness)")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    if args.source == "fairface":
        print("AVISO: FairFace son ROSTROS REALES (ADR-0019 §6). Egress real requiere sign-off legal.")
        n = _from_fairface(args.out, args.size, args.max)
    elif args.source == "ffhq":
        print("AVISO: FFHQ son ROSTROS REALES (ADR-0019 §6). Egress real requiere sign-off legal.")
        n = _from_ffhq(args.out, args.size, args.max)
    elif args.source == "dir":
        if not args.src:
            raise SystemExit("--src es obligatorio para --source dir (p. ej. subconjunto FFHQ)")
        print("AVISO: imágenes reales (FFHQ/otras). Egress real requiere sign-off legal (ADR-0019 §6).")
        n = _from_dir(args.src, args.out, args.size, args.max, "img")
    else:  # gan
        if not args.src:
            raise SystemExit("--src es obligatorio para --source gan (dir con caras GAN sintéticas)")
        n = _from_dir(args.src, args.out, args.size, args.max, "gan")

    print(f"preparadas {n} imágenes en {args.out} (lado máx {args.size}px)")


if __name__ == "__main__":
    main()

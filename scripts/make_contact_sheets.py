#!/usr/bin/env python3
"""Extract Release archives, de-duplicate images, and generate indexed contact sheets."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError

ROOT = Path.cwd()
ARCHIVES = ROOT / "archives"
EXTRACTED = ROOT / "extracted"
OUTPUT = ROOT / "output"
SHEETS = OUTPUT / "contact_sheets"
EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
COLUMNS = 6
ROWS = 8
PER_PAGE = COLUMNS * ROWS
CELL_W = 220
CELL_H = 192
IMAGE_W = 204
IMAGE_H = 151


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def get_font(size: int):
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ):
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def sources():
    all_files = sorted(p for p in ARCHIVES.iterdir() if p.is_file())
    items = []
    for p in all_files:
        low = p.name.lower()
        if low.endswith(".zip") or low.endswith(".7z") or low.endswith(".7z.001"):
            items.append(p)
    if not items:
        raise SystemExit(
            "No supported ZIP or 7z archives found. "
            "Attach *.zip or *.7z or ALL parts of *.7z.001, *.7z.002, ... "
            "to a GitHub Release."
        )
    return items


def extract_all():
    EXTRACTED.mkdir(parents=True, exist_ok=True)
    for i, src in enumerate(sources(), 1):
        destination = EXTRACTED / f"archive_{i:03d}"
        destination.mkdir(parents=True, exist_ok=True)
        print(f"Extracting {src.name} -> {destination}", flush=True)
        # 7z handles ordinary ZIPs and split 7z volumes, including .7z.001.
        # Only open the first volume; the subsequent numbered parts must be
        # present alongside it in the archives directory.
        subprocess.run(
            ["7z", "x", "-y", "-bd", f"-o{destination}", str(src)],
            check=True,
        )


def find_images():
    images = sorted(
        (p for p in EXTRACTED.rglob("*")
         if p.is_file() and p.suffix.lower() in EXTENSIONS),
        key=lambda p: p.as_posix().casefold(),
    )
    print(f"Found {len(images)} candidate image files", flush=True)
    return images


def make_inventory(images):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    unique = {}
    duplicate_count = 0
    bad = []
    records = []
    for n, p in enumerate(images, 1):
        if n % 500 == 0:
            print(f"Indexed {n}/{len(images)} files", flush=True)
        digest = sha256(p)
        if digest in unique:
            duplicate_count += 1
            continue
        unique[digest] = True
        try:
            with Image.open(p) as im:
                im.verify()
            with Image.open(p) as im:
                width, height = im.size
        except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
            bad.append({"path": str(p.relative_to(EXTRACTED)), "error": str(exc)})
            continue
        records.append({
            "index": len(records) + 1,
            "source_path": str(p.relative_to(EXTRACTED)),
            "width": width,
            "height": height,
            "sha256": digest,
            "path": p,
        })
    print(
        f"{len(records)} valid unique images, "
        f"{duplicate_count} exact duplicates, {len(bad)} unreadable images",
        flush=True,
    )
    return records, duplicate_count, bad


def render_sheet(batch, sheet_number, total_sheets, font, small_font):
    background = Image.new("RGB", (COLUMNS * CELL_W, ROWS * CELL_H + 44), "#f3f4f6")
    draw = ImageDraw.Draw(background)
    draw.text((12, 9), f"CG contact sheet {sheet_number}/{total_sheets} | " 
              f"image IDs {batch[0]['index']}-{batch[-1]['index']}", 
              font=font, fill="#111827")
    for i, record in enumerate(batch):
        x = (i % COLUMNS) * CELL_W
        y = (i // COLUMNS) * CELL_H + 44
        draw.rectangle((x + 3, y + 3, x + CELL_W - 3, y + CELL_H - 4),
                       fill="white", outline="#d1d5db")
        try:
            with Image.open(record["path"]) as im:
                im.seek(0)
                im = ImageOps.exif_transpose(im)
                if im.mode not in ("RGB", "RGBA"):
                    im = im.convert("RGB")
                im.thumbnail((IMAGE_W, IMAGE_H))
                if im.mode == "RGBA":
                    bg = Image.new("RGB", im.size, "white")
                    bg.paste(im, mask=im.getchannel("A"))
                    im = bg
                dx = x + (CELL_W - im.width) // 2
                dy = y + 8 + (IMAGE_H - im.height) // 2
                background.paste(im, (dx, dy))
        except Exception as exc:
            draw.text((x + 10, y + 45), f"Image error: {str(exc)[:20]}",
                      font=small_font, fill="red")
        filename = Path(record["source_path"]).name
        if len(filename) > 27:
            filename = filename[:24] + "..."
        draw.text((x + 8, y + 163), f"#{record['index']:05d}  {filename}",
                  font=small_font, fill="#111827")
        draw.text((x + 8, y + 178),
                  f"{record['width']} x {record['height']}",
                  font=small_font, fill="#4b5563")
    SHEETS.mkdir(parents=True, exist_ok=True)
    out = SHEETS / f"sheet_{sheet_number:04d}.jpg"
    background.save(out, "JPEG", quality=83, optimize=True)


def main():
    extract_all()
    images = find_images()
    records, duplicates, bad = make_inventory(images)
    if not records:
        raise SystemExit("No valid images found in the extracted archives.")

    SHEETS.mkdir(parents=True, exist_ok=True)
    total_sheets = math.ceil(len(records) / PER_PAGE)
    font, small_font = get_font(21), get_font(11)
    for sheet_number in range(1, total_sheets + 1):
        a = (sheet_number - 1) * PER_PAGE
        render_sheet(records[a:a + PER_PAGE], sheet_number,
                     total_sheets, font, small_font)
        if sheet_number % 20 == 0 or sheet_number == total_sheets:
            print(f"Rendered contact sheet {sheet_number}/{total_sheets}", flush=True)

    with (OUTPUT / "image_index.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f, fieldnames=["index", "source_path", "width", "height", "sha256",
                            "contact_sheet"])
        writer.writeheader()
        for r in records:
            writer.writerow({
                k: r[k] for k in ("index", "source_path", "width", "height", "sha256")
            } | {"contact_sheet": f"sheet_{math.ceil(r['index']/PER_PAGE):04d}.jpg"})

    (OUTPUT / "summary.json").write_text(
        json.dumps({
            "total_candidates": len(images),
            "unique_valid_images": len(records),
            "exact_duplicates": duplicates,
            "unreadable": bad,
            "images_per_sheet": PER_PAGE,
            "contact_sheets": total_sheets,
        }, indent=2), encoding="utf-8",
    )
    (OUTPUT / "README.txt").write_text(
        "Image IDs on contact sheets correspond to image_index.csv rows.\n"
        "Each record lists the source filename, pixel dimensions and SHA-256.\n"
        "Only contact sheets and metadata are included in this artifact.\n",
        encoding="utf-8",
    )
    print("DONE", flush=True)


if __name__ == "__main__":
    main()

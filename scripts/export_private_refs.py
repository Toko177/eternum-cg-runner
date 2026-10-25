#!/usr/bin/env python3
# 2026-10-25: include additional bios-matched private reference candidates (v2).
"""Private-only full-resolution exports and labeled bios contact sheets.

This source runs in a public code-only runner. All source bytes are fetched
from the private release, and outputs are written solely to private-results,
which is a clone of the user's verified PRIVATE repository.
"""
from __future__ import annotations

import csv
import hashlib
import io
import shutil
import subprocess
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path.cwd()
ARCHIVES = ROOT / "archives"
EXTRACTED = ROOT / "extracted" / "archive_001"
PRIVATE = ROOT / "private-results"
OUTPUT = PRIVATE / "generated" / "cgv1"
BIOS = PRIVATE / "generated" / "cgv2"
ALLOWED = {"Annie", "Luna", "Nova", "Alexandra", "Dalia", "Penelope", "Nancy", "Calypso"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def digest_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_csv(path: Path):
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def extract_sources():
    EXTRACTED.mkdir(parents=True, exist_ok=True)
    source = ARCHIVES / "images.7z.001"
    assert source.is_file(), "Missing split archive start"
    # Silence 7z filenames: public runner output must not disclose CG filenames.
    with subprocess.DEVNULL if False else open("/dev/null", "wb") as sink:
        subprocess.run(
            ["7z", "x", "-y", "-bd", "-o" + str(EXTRACTED), str(source)],
            check=True, stdout=sink, stderr=sink,
        )


def export_originals():
    inv = {int(row["index"]): row for row in read_csv(OUTPUT / "image_index.csv")}
    requested = read_csv(OUTPUT / "EXPORT_REQUEST.csv")
    if not requested:
        raise RuntimeError("Empty private export request")
    result = []
    for selection in requested:
        key = int(selection["image_id"])
        char = selection["character"]
        if char not in ALLOWED:
            raise RuntimeError("Unknown requested character")
        row = inv.get(key)
        if row is None:
            raise RuntimeError("Requested ID absent from inventory")
        # The existing inventory uses archive_001/... as a source-relative path.
        path = (ROOT / "extracted" / row["source_path"]).resolve()
        if not path.is_relative_to(EXTRACTED.resolve()) or not path.is_file():
            raise RuntimeError("Missing/unsafe original path for selected ID")
        if digest_file(path) != row["sha256"]:
            raise RuntimeError("Source image hash mismatch (aborting)")
        ext = path.suffix.lower()
        if ext not in IMAGE_EXT:
            raise RuntimeError("Unexpected original image extension")
        dest_rel = Path("generated/cgv1/selected_originals") / char / ("cg_" + str(key).zfill(5) + ext)
        dest = PRIVATE / dest_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
        result.append({
            "image_id": key, "character": char,
            "original_source_path": row["source_path"], "private_output_path": dest_rel.as_posix(),
            "width": row["width"], "height": row["height"], "sha256": row["sha256"],
            "identity_status": selection["identity_status"],
            "source_priority": selection["source_priority"],
            "review_note": selection["review_note"],
        })
    with (OUTPUT / "selection_export_index.csv").open("w", newline="", encoding="utf-8") as f:
        fields = list(result[0])
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(result)
    print("Original-resolution assets verified and saved to PRIVATE clone:", len(result))


def font(size):
    for name in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                 "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"):
        if Path(name).exists():
            return ImageFont.truetype(name, size)
    return ImageFont.load_default()


def export_bios():
    zip_path = ARCHIVES / "bios.zip"
    BIOS.mkdir(parents=True, exist_ok=True)
    preview_dir = BIOS / "bios_previews"
    preview_dir.mkdir(exist_ok=True)
    entries = []
    with zipfile.ZipFile(zip_path) as z:
        infos = sorted(
            (i for i in z.infolist() if not i.is_dir() and Path(i.filename).suffix.lower() in IMAGE_EXT),
            key=lambda v: v.filename.casefold(),
        )
        if len(infos) > 200:
            raise RuntimeError("Unexpectedly many biography pictures; refusing unbounded export")
        for info in infos:
            data = z.read(info)
            with Image.open(io.BytesIO(data)) as original:
                image = ImageOps.exif_transpose(original)
                width, height = image.size
                image.thumbnail((1200, 1200))
                preview_name = "bio_" + str(len(entries) + 1).zfill(4) + ".jpg"
                image.convert("RGB").save(preview_dir / preview_name, quality=88, optimize=True)
            entries.append({
                "original_zip_path": info.filename,
                "preview_path": ("generated/cgv2/bios_previews/" + preview_name),
                "original_width": width,
                "original_height": height,
            })
    if not entries:
        raise RuntimeError("No recognizable images in bios.zip")
    with (BIOS / "bios_index.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(entries[0]))
        writer.writeheader()
        writer.writerows(entries)

    cell_w, cell_h, cols, per_sheet = 235, 210, 5, 25
    font_small = font(12)
    for start in range(0, len(entries), per_sheet):
        batch = entries[start:start + per_sheet]
        rows = (len(batch) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * cell_w, rows * cell_h + 45), "white")
        pen = ImageDraw.Draw(sheet)
        pen.text((12, 12), "PRIVATE character bios - page " +
                 str(start // per_sheet + 1), font=font(19), fill="black")
        for i, record in enumerate(batch):
            x = (i % cols) * cell_w
            y = (i // cols) * cell_h + 45
            with Image.open(PRIVATE / record["preview_path"]) as p:
                p.thumbnail((223, 169))
                sheet.paste(p, (x + (cell_w - p.width) // 2, y + 3))
            pen.text((x + 4, y + 174),
                     Path(record["original_zip_path"]).name[:31],
                     font=font_small, fill="black")
            pen.text((x + 4, y + 189),
                     "bio #" + str(start + i + 1).zfill(4),
                     font=font_small, fill="black")
        sheet.save(BIOS / ("bios_contact_sheet_" + str(start // per_sheet + 1).zfill(4) + ".jpg"),
                   "JPEG", quality=88, optimize=True)
    print("PRIVATE character bios preview count:", len(entries))


def main():
    assert (PRIVATE / ".git").exists(), "Private repository clone required"
    assert (ARCHIVES / "bios.zip").is_file(), "Missing private bios.zip"
    extract_sources()
    export_originals()
    export_bios()
    print("SUCCESS: all output paths reside inside private-results/")


if __name__ == "__main__":
    main()

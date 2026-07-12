"""ImageChecker — deterministic image integrity checks.

Four checks (no LLM, no GPU):
  1. Perceptual hash duplicate detection (imagehash pHash)
  2. Error Level Analysis (JPEG re-save comparison)
  3. EXIF metadata anomaly detection
  4. DPI / resolution quality check

Dependencies: Pillow, imagehash
"""

from __future__ import annotations

import io
import logging
from itertools import combinations

import imagehash
from app.engines.integrity.finding_models import (
    DuplicateMatch,
    ELAResult,
    ImageFinding,
    ImageInput,
)
from PIL import Image
from PIL.ExifTags import Base as ExifBase

logger = logging.getLogger(__name__)

# Max images for pairwise duplicate comparison (O(n²) guard)
_MAX_PAIRWISE = 100

# Known image editing software keywords
_EDITING_SOFTWARE = frozenset({
    "photoshop", "gimp", "affinity photo", "paint.net", "pixlr",
    "lightroom", "capture one", "darktable", "rawtherapee",
})


class ImageChecker:
    """Deterministic image integrity checker.

    All methods are synchronous and require no LLM or network calls.
    """

    DUPLICATE_THRESHOLD: int = 10  # Hamming distance ≤ threshold = near-duplicate
    ELA_QUALITY: int = 95  # JPEG re-save quality for ELA
    ELA_SUSPICIOUS_THRESHOLD: int = 40  # Pixel diff above this is suspicious
    ELA_REGION_RATIO_THRESHOLD: float = 0.01  # 1% of pixels must be suspicious
    MIN_DPI: int = 150  # Minimum DPI for publication quality

    # --- Public API ---

    def check_all(self, images: list[ImageInput]) -> list[ImageFinding]:
        """Run all 4 checks on a list of images. Entry point for agent and W7."""
        findings: list[ImageFinding] = []

        if not images:
            return findings

        # 1. Duplicate detection (pairwise)
        findings.extend(self.check_duplicates(images))

        # 2-4. Per-image checks
        for img in images:
            try:
                pil_image = Image.open(io.BytesIO(img.image_bytes))
            except Exception as e:
                logger.debug("Cannot open image %s: %s", img.filename, e)
                continue

            ela_finding = self.check_ela(img, pil_image)
            if ela_finding:
                findings.append(ela_finding)

            meta_finding = self.check_metadata(img, pil_image)
            if meta_finding:
                findings.append(meta_finding)

            res_finding = self.check_resolution(img, pil_image)
            if res_finding:
                findings.append(res_finding)

        return findings

    def check_duplicates(self, images: list[ImageInput]) -> list[ImageFinding]:
        """Detect near-duplicate image panels via perceptual hashing (pHash).

        Compares all pairs using Hamming distance on 64-bit pHash fingerprints.
        Capped at _MAX_PAIRWISE images to avoid O(n²) blowup.
        """
        if len(images) < 2:
            return []

        # Compute hashes
        hashes: list[tuple[ImageInput, imagehash.ImageHash]] = []
        for img in images[:_MAX_PAIRWISE]:
            try:
                pil_image = Image.open(io.BytesIO(img.image_bytes))
                h = imagehash.phash(pil_image)
                hashes.append((img, h))
            except Exception as e:
                logger.debug("Cannot hash image %s: %s", img.filename, e)
                continue

        if len(hashes) < 2:
            return []

        # Pairwise comparison
        findings: list[ImageFinding] = []
        seen_pairs: set[tuple[str, str]] = set()

        for (img_a, hash_a), (img_b, hash_b) in combinations(hashes, 2):
            distance = hash_a - hash_b  # Hamming distance
            if distance <= self.DUPLICATE_THRESHOLD:
                pair_key = tuple(sorted([img_a.label or img_a.filename, img_b.label or img_b.filename]))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                similarity = 1.0 - (distance / 64.0)
                label_a = img_a.label or img_a.filename or "image_A"
                label_b = img_b.label or img_b.filename or "image_B"

                findings.append(ImageFinding(
                    category="duplicate_image",
                    severity="error" if distance == 0 else "warning",
                    title=f"Near-duplicate images: {label_a} / {label_b}",
                    description=(
                        f"Images '{label_a}' and '{label_b}' are perceptually "
                        f"{'identical' if distance == 0 else 'near-identical'} "
                        f"(Hamming distance: {distance}/64, similarity: {similarity:.1%})."
                    ),
                    suggestion="Verify these images are not unintentionally duplicated panels.",
                    confidence=similarity,
                    checker="image_checker:duplicates",
                    filename=img_a.filename,
                    duplicate_match=DuplicateMatch(
                        image_a_label=label_a,
                        image_b_label=label_b,
                        hamming_distance=distance,
                        similarity=similarity,
                    ),
                ))

        return findings

    def check_ela(
        self,
        img: ImageInput,
        pil_image: Image.Image | None = None,
    ) -> ImageFinding | None:
        """Error Level Analysis: re-save JPEG at 95%, compare pixel diffs.

        Only meaningful for JPEG images. Returns None for non-JPEG or clean images.
        """
        if pil_image is None:
            try:
                pil_image = Image.open(io.BytesIO(img.image_bytes))
            except Exception:
                return None

        # ELA only works on JPEG
        fmt = pil_image.format
        if fmt not in ("JPEG", "MPO"):
            return None

        try:
            # Convert to RGB if needed (handles CMYK, palette, etc.)
            rgb = pil_image.convert("RGB")

            # Re-save at target quality
            buffer = io.BytesIO()
            rgb.save(buffer, format="JPEG", quality=self.ELA_QUALITY)
            buffer.seek(0)
            resaved = Image.open(buffer).convert("RGB")

            # Compute pixel-wise absolute difference
            import numpy as np

            orig_arr = np.array(rgb, dtype=np.float32)
            resaved_arr = np.array(resaved, dtype=np.float32)
            diff = np.abs(orig_arr - resaved_arr)

            # Scale to maximize visibility
            max_val = diff.max()
            mean_val = diff.mean()

            if max_val == 0:
                return None  # Perfectly re-compressed, no anomaly

            # Count suspicious pixels (any channel above threshold)
            suspicious_pixels = np.any(diff > self.ELA_SUSPICIOUS_THRESHOLD, axis=2)
            suspicious_ratio = suspicious_pixels.sum() / suspicious_pixels.size

            is_suspicious = suspicious_ratio > self.ELA_REGION_RATIO_THRESHOLD

            if not is_suspicious:
                return None

            label = img.label or img.filename or "image"
            return ImageFinding(
                category="image_manipulation",
                severity="warning",
                title=f"ELA anomaly in {label}",
                description=(
                    f"Error Level Analysis found {suspicious_ratio:.1%} of pixels with "
                    f"above-threshold differences (max={max_val:.1f}, mean={mean_val:.1f}). "
                    f"This may indicate image editing or splicing."
                ),
                suggestion="Review the flagged image for potential manipulation.",
                confidence=min(0.5 + suspicious_ratio * 5, 0.95),
                checker="image_checker:ela",
                filename=img.filename,
                ela_result=ELAResult(
                    max_ela_value=float(max_val),
                    mean_ela_value=float(mean_val),
                    suspicious_region_ratio=float(suspicious_ratio),
                    is_suspicious=True,
                ),
            )
        except Exception as e:
            logger.debug("ELA check failed for %s: %s", img.filename, e)
            return None

    def check_metadata(
        self,
        img: ImageInput,
        pil_image: Image.Image | None = None,
    ) -> ImageFinding | None:
        """EXIF metadata analysis: detect editing software and inconsistencies.

        Flags images with known photo-editing software in the Software tag.
        """
        if pil_image is None:
            try:
                pil_image = Image.open(io.BytesIO(img.image_bytes))
            except Exception:
                return None

        try:
            exif_data = pil_image.getexif()
        except Exception:
            return None

        if not exif_data:
            # Completely stripped EXIF — soft info signal
            return ImageFinding(
                category="image_metadata_anomaly",
                severity="info",
                title=f"No EXIF metadata: {img.label or img.filename or 'image'}",
                description="This image has no EXIF metadata. This is common for web images and journal figures.",
                suggestion="No action needed unless metadata provenance is important.",
                confidence=0.3,
                checker="image_checker:metadata",
                filename=img.filename,
            )

        # Check for editing software
        software_tag = exif_data.get(ExifBase.Software, "")
        if isinstance(software_tag, bytes):
            software_tag = software_tag.decode("utf-8", errors="ignore")

        if software_tag:
            software_lower = software_tag.lower()
            for editor in _EDITING_SOFTWARE:
                if editor in software_lower:
                    label = img.label or img.filename or "image"
                    return ImageFinding(
                        category="image_metadata_anomaly",
                        severity="warning",
                        title=f"Editing software detected: {label}",
                        description=(
                            f"EXIF Software tag indicates '{software_tag}'. "
                            f"This image may have been processed with photo editing software."
                        ),
                        suggestion="Verify that any image editing was limited to acceptable adjustments.",
                        confidence=0.7,
                        checker="image_checker:metadata",
                        filename=img.filename,
                        metadata={"software": software_tag},
                    )

        return None

    def check_resolution(
        self,
        img: ImageInput,
        pil_image: Image.Image | None = None,
    ) -> ImageFinding | None:
        """Check DPI and resolution for publication quality.

        Flags images below MIN_DPI. Returns None if DPI info is unavailable or adequate.
        """
        if pil_image is None:
            try:
                pil_image = Image.open(io.BytesIO(img.image_bytes))
            except Exception:
                return None

        # Try to get DPI from image info
        dpi = pil_image.info.get("dpi")
        if dpi is None:
            # Try EXIF
            try:
                exif = pil_image.getexif()
                x_res = exif.get(ExifBase.XResolution)
                y_res = exif.get(ExifBase.YResolution)
                if x_res and y_res:
                    # IFDRational or float
                    dpi = (float(x_res), float(y_res))
            except Exception:
                pass

        if dpi is None:
            return None  # No DPI info, don't flag

        # dpi is typically a tuple (x_dpi, y_dpi)
        min_dpi_val = min(float(dpi[0]), float(dpi[1])) if isinstance(dpi, (tuple, list)) else float(dpi)

        if min_dpi_val >= self.MIN_DPI:
            return None

        label = img.label or img.filename or "image"
        return ImageFinding(
            category="image_quality_issue",
            severity="warning",
            title=f"Low resolution: {label}",
            description=(
                f"Image DPI is {min_dpi_val:.0f}, below the recommended minimum of "
                f"{self.MIN_DPI} DPI for publication-quality figures."
            ),
            suggestion=f"Consider using a higher-resolution version (≥{self.MIN_DPI} DPI).",
            confidence=0.8,
            checker="image_checker:resolution",
            filename=img.filename,
            metadata={"dpi": min_dpi_val},
        )

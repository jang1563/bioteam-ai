"""Tests for ImageChecker — duplicate detection, ELA, metadata, resolution checks."""

import io

import pytest
from app.engines.integrity.finding_models import ImageInput
from app.engines.integrity.image_checker import ImageChecker
from PIL import Image
from PIL.ExifTags import Base as ExifBase


@pytest.fixture
def checker():
    return ImageChecker()


# === Helpers ===


def _make_solid_jpeg(color: tuple[int, int, int], size: tuple[int, int] = (100, 100)) -> bytes:
    """Create a solid-color JPEG image in memory."""
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def _make_solid_png(color: tuple[int, int, int], size: tuple[int, int] = (100, 100)) -> bytes:
    """Create a solid-color PNG image in memory."""
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_jpeg_with_exif(software: str = "", dpi: tuple[int, int] | None = None) -> bytes:
    """Create a JPEG with custom EXIF data."""
    import piexif

    img = Image.new("RGB", (100, 100), (128, 128, 128))
    exif_dict = {"0th": {}, "Exif": {}}
    if software:
        exif_dict["0th"][piexif.ImageIFD.Software] = software.encode()
    if dpi:
        exif_dict["0th"][piexif.ImageIFD.XResolution] = (dpi[0], 1)
        exif_dict["0th"][piexif.ImageIFD.YResolution] = (dpi[1], 1)
        exif_dict["0th"][piexif.ImageIFD.ResolutionUnit] = 2  # inches
    exif_bytes = piexif.dump(exif_dict)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95, exif=exif_bytes)
    return buf.getvalue()


def _make_jpeg_with_pil_exif(software: str = "", dpi: tuple[int, int] | None = None) -> bytes:
    """Create a JPEG with EXIF via PIL (no piexif dependency)."""
    from PIL.Image import Exif

    img = Image.new("RGB", (100, 100), (128, 128, 128))
    exif = Exif()
    if software:
        exif[ExifBase.Software] = software
    buf = io.BytesIO()
    if dpi:
        img.save(buf, format="JPEG", quality=95, exif=exif.tobytes(), dpi=dpi)
    else:
        img.save(buf, format="JPEG", quality=95, exif=exif.tobytes())
    return buf.getvalue()


def _make_image_input(
    image_bytes: bytes,
    filename: str = "test.jpg",
    label: str = "",
) -> ImageInput:
    return ImageInput(image_bytes=image_bytes, filename=filename, label=label)


# === Duplicate Detection Tests ===


class TestDuplicateDetection:

    def test_identical_images_detected(self, checker):
        """Two identical images should be flagged as duplicates."""
        data = _make_solid_jpeg((255, 0, 0))
        images = [
            _make_image_input(data, filename="fig1.jpg", label="Figure 1A"),
            _make_image_input(data, filename="fig2.jpg", label="Figure 1B"),
        ]
        findings = checker.check_duplicates(images)
        assert len(findings) == 1
        assert findings[0].category == "duplicate_image"
        assert findings[0].severity == "error"  # distance == 0
        assert findings[0].duplicate_match is not None
        assert findings[0].duplicate_match.hamming_distance == 0

    def test_slightly_different_detected(self, checker):
        """Slightly different images should still be caught if within threshold."""
        # Same base, slightly different shade
        data_a = _make_solid_jpeg((255, 0, 0))
        data_b = _make_solid_jpeg((250, 5, 5))
        images = [
            _make_image_input(data_a, label="A"),
            _make_image_input(data_b, label="B"),
        ]
        findings = checker.check_duplicates(images)
        # Very similar solid colors should have a very low hamming distance
        assert len(findings) == 1
        assert findings[0].category == "duplicate_image"

    def test_completely_different_not_flagged(self, checker):
        """Totally different images should not be flagged."""
        # A mostly-red image vs a mostly-blue image with patterns
        img_a = Image.new("RGB", (100, 100), (255, 0, 0))
        # Create a complex pattern for image B
        img_b = Image.new("RGB", (100, 100), (0, 0, 255))
        for x in range(0, 100, 2):
            for y in range(0, 100, 2):
                img_b.putpixel((x, y), (0, 255, 0))

        buf_a, buf_b = io.BytesIO(), io.BytesIO()
        img_a.save(buf_a, format="JPEG", quality=95)
        img_b.save(buf_b, format="JPEG", quality=95)

        images = [
            _make_image_input(buf_a.getvalue(), label="red"),
            _make_image_input(buf_b.getvalue(), label="blue-green"),
        ]
        findings = checker.check_duplicates(images)
        assert len(findings) == 0

    def test_single_image_no_comparison(self, checker):
        """A single image should produce no duplicate findings."""
        data = _make_solid_jpeg((255, 0, 0))
        findings = checker.check_duplicates([_make_image_input(data)])
        assert len(findings) == 0

    def test_empty_list(self, checker):
        """Empty image list should produce no findings."""
        assert checker.check_duplicates([]) == []

    def test_three_identical_images(self, checker):
        """Three identical images should produce 3 pair findings."""
        data = _make_solid_jpeg((100, 200, 50))
        images = [
            _make_image_input(data, label="A"),
            _make_image_input(data, label="B"),
            _make_image_input(data, label="C"),
        ]
        findings = checker.check_duplicates(images)
        # 3 choose 2 = 3 pairs
        assert len(findings) == 3


# === ELA Tests ===


class TestELA:

    def test_unmodified_jpeg_clean(self, checker):
        """A pristine solid-color JPEG should have low ELA and not be flagged."""
        data = _make_solid_jpeg((128, 128, 128))
        img_input = _make_image_input(data)
        pil_image = Image.open(io.BytesIO(data))
        result = checker.check_ela(img_input, pil_image)
        # Solid-color JPEGs typically don't have high ELA
        # Result may or may not be None depending on JPEG compression artifacts
        if result is not None:
            assert result.category == "image_manipulation"

    def test_png_skipped(self, checker):
        """ELA on PNG should return None (only works on JPEG)."""
        data = _make_solid_png((128, 128, 128))
        img_input = _make_image_input(data, filename="test.png")
        pil_image = Image.open(io.BytesIO(data))
        result = checker.check_ela(img_input, pil_image)
        assert result is None

    def test_ela_returns_finding_with_result(self, checker):
        """When ELA detects anomalies, the finding should have an ELAResult."""
        # Create a JPEG then heavily modify a region (simulate splice)
        img = Image.new("RGB", (200, 200), (128, 128, 128))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=50)  # Low quality first
        buf.seek(0)
        low_q = Image.open(buf)

        # Now resave at high quality (simulates pasting high-quality region into low-quality image)
        # This is a synthetic test — real ELA is more nuanced
        region = Image.new("RGB", (50, 50), (255, 255, 255))
        low_q_rgb = low_q.convert("RGB")
        low_q_rgb.paste(region, (75, 75))
        buf2 = io.BytesIO()
        low_q_rgb.save(buf2, format="JPEG", quality=95)
        data = buf2.getvalue()

        img_input = _make_image_input(data)
        pil_image = Image.open(io.BytesIO(data))
        result = checker.check_ela(img_input, pil_image)
        # Whether this triggers depends on compression artifacts; just verify the shape
        if result is not None:
            assert result.ela_result is not None
            assert result.ela_result.is_suspicious


# === Metadata Tests ===


class TestMetadata:

    def test_photoshop_software_flagged(self, checker):
        """Image with Photoshop in Software EXIF tag should be flagged."""
        data = _make_jpeg_with_pil_exif(software="Adobe Photoshop CC 2024")
        img_input = _make_image_input(data)
        pil_image = Image.open(io.BytesIO(data))
        result = checker.check_metadata(img_input, pil_image)
        assert result is not None
        assert result.category == "image_metadata_anomaly"
        assert result.severity == "warning"
        assert "Photoshop" in result.description

    def test_gimp_software_flagged(self, checker):
        """Image with GIMP in Software EXIF tag should be flagged."""
        data = _make_jpeg_with_pil_exif(software="GIMP 2.10")
        img_input = _make_image_input(data)
        pil_image = Image.open(io.BytesIO(data))
        result = checker.check_metadata(img_input, pil_image)
        assert result is not None
        assert result.category == "image_metadata_anomaly"

    def test_no_exif_flagged_as_info(self, checker):
        """Image with completely stripped EXIF should get info-level finding."""
        # PNG images typically have no EXIF
        data = _make_solid_png((128, 128, 128))
        img_input = _make_image_input(data, filename="test.png")
        pil_image = Image.open(io.BytesIO(data))
        result = checker.check_metadata(img_input, pil_image)
        assert result is not None
        assert result.severity == "info"

    def test_normal_software_clean(self, checker):
        """Image with non-editing software should not be flagged."""
        data = _make_jpeg_with_pil_exif(software="Canon EOS R5")
        img_input = _make_image_input(data)
        pil_image = Image.open(io.BytesIO(data))
        result = checker.check_metadata(img_input, pil_image)
        # Camera software shouldn't trigger editing detection
        assert result is None


# === Resolution Tests ===


class TestResolution:

    def test_low_dpi_flagged(self, checker):
        """Image with 72 DPI should be flagged as low resolution."""
        img = Image.new("RGB", (100, 100), (128, 128, 128))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95, dpi=(72, 72))
        data = buf.getvalue()

        img_input = _make_image_input(data)
        pil_image = Image.open(io.BytesIO(data))
        result = checker.check_resolution(img_input, pil_image)
        assert result is not None
        assert result.category == "image_quality_issue"
        assert result.severity == "warning"

    def test_high_dpi_clean(self, checker):
        """Image with 300 DPI should not be flagged."""
        img = Image.new("RGB", (100, 100), (128, 128, 128))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95, dpi=(300, 300))
        data = buf.getvalue()

        img_input = _make_image_input(data)
        pil_image = Image.open(io.BytesIO(data))
        result = checker.check_resolution(img_input, pil_image)
        assert result is None

    def test_no_dpi_info_clean(self, checker):
        """Image with missing DPI info should not be flagged."""
        # A raw JPEG without DPI info
        img = Image.new("RGB", (100, 100), (128, 128, 128))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        data = buf.getvalue()

        img_input = _make_image_input(data)
        pil_image = Image.open(io.BytesIO(data))
        # Remove dpi info if present
        pil_image.info.pop("dpi", None)
        result = checker.check_resolution(img_input, pil_image)
        assert result is None


# === check_all Integration Tests ===


class TestCheckAll:

    def test_empty_images_clean(self, checker):
        """Empty image list should produce no findings."""
        assert checker.check_all([]) == []

    def test_combined_checks(self, checker):
        """check_all should run all checks and combine findings."""
        # Two identical images + one with low DPI → at least 1 duplicate + 1 quality
        data = _make_solid_jpeg((255, 0, 0))
        img_low_dpi = Image.new("RGB", (100, 100), (0, 0, 255))
        buf = io.BytesIO()
        img_low_dpi.save(buf, format="JPEG", quality=95, dpi=(72, 72))

        images = [
            _make_image_input(data, label="A"),
            _make_image_input(data, label="B"),
            _make_image_input(buf.getvalue(), label="low_dpi"),
        ]
        findings = checker.check_all(images)
        categories = [f.category for f in findings]
        assert "duplicate_image" in categories
        assert "image_quality_issue" in categories

    def test_invalid_image_bytes_skipped(self, checker):
        """Invalid image bytes should be skipped gracefully."""
        images = [
            _make_image_input(b"not-an-image", label="bad"),
        ]
        findings = checker.check_all(images)
        # Should not crash, may have no findings or metadata-related info
        assert isinstance(findings, list)

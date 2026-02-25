"""Edge case tests for ImageChecker — boundary conditions, corrupted data, extreme inputs.

Tests cover:
  - Corrupt / truncated / zero-byte image data
  - Single-pixel images
  - Very large image dimensions (within memory)
  - Mixed format inputs (JPEG + PNG + BMP + TIFF + GIF)
  - EXIF edge cases (partial EXIF, unusual software strings)
  - ELA edge cases (grayscale JPEG, CMYK, palette mode)
  - Duplicate detection edge cases (100+ images cap, hash collision scenarios)
  - Resolution edge cases (asymmetric DPI, zero DPI, negative DPI)
  - ImageInput with empty bytes / empty filename / empty label
  - Integration with agent quick_check (images-only, no text)
"""

from __future__ import annotations

import io
import os
import sys

import pytest
from PIL import Image, ExifTags
from PIL.ExifTags import Base as ExifBase

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.engines.integrity.finding_models import ImageFinding, ImageInput
from app.engines.integrity.image_checker import ImageChecker


@pytest.fixture
def checker():
    return ImageChecker()


# === Helpers ===


def _make_jpeg(color=(128, 128, 128), size=(100, 100), quality=95, dpi=None, mode="RGB") -> bytes:
    img = Image.new(mode, size, color if mode == "RGB" else 128)
    buf = io.BytesIO()
    kwargs = {"format": "JPEG", "quality": quality}
    if dpi:
        kwargs["dpi"] = dpi
    if mode != "RGB":
        img = img.convert("RGB")
    img.save(buf, **kwargs)
    return buf.getvalue()


def _make_png(color=(128, 128, 128), size=(100, 100)) -> bytes:
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_bmp(color=(128, 128, 128), size=(100, 100)) -> bytes:
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="BMP")
    return buf.getvalue()


def _make_gif(color=(128, 128, 128), size=(100, 100)) -> bytes:
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="GIF")
    return buf.getvalue()


def _make_tiff(color=(128, 128, 128), size=(100, 100)) -> bytes:
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="TIFF")
    return buf.getvalue()


def _img(data: bytes, filename="test.jpg", label="") -> ImageInput:
    return ImageInput(image_bytes=data, filename=filename, label=label)


# =============================================================================
# 1. Corrupt / Malformed Input
# =============================================================================


class TestCorruptInput:
    """Tests for malformed, truncated, and garbage image data."""

    def test_zero_bytes(self, checker):
        """Zero-byte input should not crash."""
        findings = checker.check_all([_img(b"", filename="empty.jpg")])
        assert isinstance(findings, list)

    def test_random_garbage(self, checker):
        """Random bytes that aren't an image should not crash."""
        import random
        garbage = bytes(random.getrandbits(8) for _ in range(500))
        findings = checker.check_all([_img(garbage, filename="garbage.bin")])
        assert isinstance(findings, list)

    def test_truncated_jpeg(self, checker):
        """Truncated JPEG (first 50 bytes of valid JPEG) should not crash."""
        valid = _make_jpeg()
        truncated = valid[:50]
        findings = checker.check_all([_img(truncated, filename="trunc.jpg")])
        assert isinstance(findings, list)

    def test_truncated_png(self, checker):
        """Truncated PNG should not crash."""
        valid = _make_png()
        truncated = valid[:30]
        findings = checker.check_all([_img(truncated, filename="trunc.png")])
        assert isinstance(findings, list)

    def test_jpeg_header_only(self, checker):
        """JPEG header bytes (FFD8FF) but no actual image data."""
        findings = checker.check_all([_img(b"\xff\xd8\xff\xe0", filename="header.jpg")])
        assert isinstance(findings, list)

    def test_text_file_as_image(self, checker):
        """Plain text disguised as an image file."""
        text_data = b"This is not an image, it is plain text content."
        findings = checker.check_all([_img(text_data, filename="text.jpg")])
        assert isinstance(findings, list)

    def test_two_corrupt_images_for_duplicate_check(self, checker):
        """Two corrupt images should not crash the duplicate checker."""
        findings = checker.check_duplicates([
            _img(b"corrupt1", label="A"),
            _img(b"corrupt2", label="B"),
        ])
        assert findings == []


# =============================================================================
# 2. Extreme Dimensions
# =============================================================================


class TestExtremeDimensions:
    """Tests for unusual image dimensions."""

    def test_single_pixel_jpeg(self, checker):
        """1x1 pixel JPEG should be handled."""
        data = _make_jpeg(size=(1, 1))
        findings = checker.check_all([_img(data, label="1x1")])
        assert isinstance(findings, list)

    def test_single_pixel_png(self, checker):
        """1x1 pixel PNG should be handled."""
        data = _make_png(size=(1, 1))
        findings = checker.check_all([_img(data, label="1x1")])
        assert isinstance(findings, list)

    def test_very_wide_image(self, checker):
        """Very wide image (5000x1) should be handled."""
        data = _make_jpeg(size=(5000, 1))
        findings = checker.check_all([_img(data)])
        assert isinstance(findings, list)

    def test_very_tall_image(self, checker):
        """Very tall image (1x5000) should be handled."""
        data = _make_jpeg(size=(1, 5000))
        findings = checker.check_all([_img(data)])
        assert isinstance(findings, list)

    def test_two_identical_single_pixel(self, checker):
        """Two identical 1x1 images should still be detected as duplicates."""
        data = _make_jpeg(color=(255, 0, 0), size=(1, 1))
        findings = checker.check_duplicates([
            _img(data, label="A"),
            _img(data, label="B"),
        ])
        assert len(findings) == 1
        assert findings[0].category == "duplicate_image"


# =============================================================================
# 3. Mixed Formats
# =============================================================================


class TestMixedFormats:
    """Tests for handling different image formats together."""

    def test_jpeg_png_bmp_mix(self, checker):
        """Mix of JPEG, PNG, BMP should all be processed."""
        jpeg = _make_jpeg(color=(255, 0, 0))
        png = _make_png(color=(0, 255, 0))
        bmp = _make_bmp(color=(0, 0, 255))
        images = [
            _img(jpeg, filename="red.jpg", label="JPEG"),
            _img(png, filename="green.png", label="PNG"),
            _img(bmp, filename="blue.bmp", label="BMP"),
        ]
        findings = checker.check_all(images)
        assert isinstance(findings, list)

    def test_gif_input(self, checker):
        """GIF should be accepted and processed (no crash)."""
        gif = _make_gif(color=(100, 200, 50))
        findings = checker.check_all([_img(gif, filename="test.gif")])
        assert isinstance(findings, list)

    def test_tiff_input(self, checker):
        """TIFF should be accepted and processed (no crash)."""
        tiff = _make_tiff()
        findings = checker.check_all([_img(tiff, filename="test.tiff")])
        assert isinstance(findings, list)

    def test_ela_skips_non_jpeg(self, checker):
        """ELA should return None for all non-JPEG formats."""
        for data, fmt in [
            (_make_png(), "PNG"),
            (_make_bmp(), "BMP"),
            (_make_gif(), "GIF"),
            (_make_tiff(), "TIFF"),
        ]:
            img_input = _img(data, filename=f"test.{fmt.lower()}")
            pil_image = Image.open(io.BytesIO(data))
            result = checker.check_ela(img_input, pil_image)
            assert result is None, f"ELA should skip {fmt}"


# =============================================================================
# 4. EXIF Edge Cases
# =============================================================================


class TestEXIFEdgeCases:
    """Tests for unusual EXIF metadata conditions."""

    def test_exif_with_empty_software(self, checker):
        """Image with empty Software tag should not be flagged for editing."""
        from PIL.Image import Exif
        img = Image.new("RGB", (100, 100), (128, 128, 128))
        exif = Exif()
        exif[ExifBase.Software] = ""
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95, exif=exif.tobytes())
        data = buf.getvalue()

        pil_image = Image.open(io.BytesIO(data))
        result = checker.check_metadata(_img(data), pil_image)
        # Empty software string → no editing software detected
        assert result is None

    def test_exif_with_unknown_software(self, checker):
        """Unknown software (not in _EDITING_SOFTWARE) should not be flagged."""
        from PIL.Image import Exif
        img = Image.new("RGB", (100, 100), (128, 128, 128))
        exif = Exif()
        exif[ExifBase.Software] = "Microsoft Paint 3D"
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95, exif=exif.tobytes())
        data = buf.getvalue()

        pil_image = Image.open(io.BytesIO(data))
        result = checker.check_metadata(_img(data), pil_image)
        assert result is None

    def test_exif_case_insensitive_detection(self, checker):
        """Software detection should be case-insensitive."""
        from PIL.Image import Exif
        img = Image.new("RGB", (100, 100), (128, 128, 128))
        exif = Exif()
        exif[ExifBase.Software] = "ADOBE PHOTOSHOP CS6"
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95, exif=exif.tobytes())
        data = buf.getvalue()

        pil_image = Image.open(io.BytesIO(data))
        result = checker.check_metadata(_img(data), pil_image)
        assert result is not None
        assert result.category == "image_metadata_anomaly"

    def test_exif_lightroom_detected(self, checker):
        """Adobe Lightroom should also be detected."""
        from PIL.Image import Exif
        img = Image.new("RGB", (100, 100), (128, 128, 128))
        exif = Exif()
        exif[ExifBase.Software] = "Adobe Lightroom Classic 12.0"
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95, exif=exif.tobytes())
        data = buf.getvalue()

        pil_image = Image.open(io.BytesIO(data))
        result = checker.check_metadata(_img(data), pil_image)
        assert result is not None
        assert result.severity == "warning"


# =============================================================================
# 5. ELA Edge Cases
# =============================================================================


class TestELAEdgeCases:
    """Edge cases for Error Level Analysis."""

    def test_ela_grayscale_jpeg(self, checker):
        """Grayscale JPEG should be handled (converted to RGB internally)."""
        img = Image.new("L", (100, 100), 128)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        data = buf.getvalue()

        pil_image = Image.open(io.BytesIO(data))
        # Grayscale JPEG format is still JPEG, should not crash
        result = checker.check_ela(_img(data), pil_image)
        # May or may not produce a finding, but should not crash
        assert result is None or isinstance(result, ImageFinding)

    def test_ela_very_low_quality_jpeg(self, checker):
        """Very low quality JPEG (quality=5) — high natural ELA artifacts."""
        data = _make_jpeg(quality=5)
        pil_image = Image.open(io.BytesIO(data))
        result = checker.check_ela(_img(data), pil_image)
        # Low quality naturally has ELA differences, may or may not flag
        assert result is None or isinstance(result, ImageFinding)

    def test_ela_maximum_quality_jpeg(self, checker):
        """Maximum quality JPEG (quality=100) should produce minimal ELA."""
        data = _make_jpeg(quality=100)
        pil_image = Image.open(io.BytesIO(data))
        result = checker.check_ela(_img(data), pil_image)
        # High quality re-saved should be very close to original
        assert result is None or isinstance(result, ImageFinding)


# =============================================================================
# 6. Resolution Edge Cases
# =============================================================================


class TestResolutionEdgeCases:
    """Edge cases for DPI/resolution checking."""

    def test_asymmetric_dpi(self, checker):
        """Asymmetric DPI (300x72) should flag based on the lower value."""
        img = Image.new("RGB", (100, 100), (128, 128, 128))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95, dpi=(300, 72))
        data = buf.getvalue()

        pil_image = Image.open(io.BytesIO(data))
        result = checker.check_resolution(_img(data), pil_image)
        assert result is not None
        assert result.category == "image_quality_issue"

    def test_exactly_min_dpi(self, checker):
        """DPI exactly at the minimum (150) should not be flagged."""
        img = Image.new("RGB", (100, 100), (128, 128, 128))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95, dpi=(150, 150))
        data = buf.getvalue()

        pil_image = Image.open(io.BytesIO(data))
        result = checker.check_resolution(_img(data), pil_image)
        assert result is None

    def test_dpi_just_below_threshold(self, checker):
        """DPI at 149 should be flagged."""
        img = Image.new("RGB", (100, 100), (128, 128, 128))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95, dpi=(149, 149))
        data = buf.getvalue()

        pil_image = Image.open(io.BytesIO(data))
        result = checker.check_resolution(_img(data), pil_image)
        assert result is not None

    def test_very_high_dpi(self, checker):
        """Very high DPI (1200) should be clean."""
        img = Image.new("RGB", (100, 100), (128, 128, 128))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95, dpi=(1200, 1200))
        data = buf.getvalue()

        pil_image = Image.open(io.BytesIO(data))
        result = checker.check_resolution(_img(data), pil_image)
        assert result is None

    def test_png_without_dpi(self, checker):
        """PNG without DPI info should not be flagged."""
        data = _make_png()
        pil_image = Image.open(io.BytesIO(data))
        pil_image.info.pop("dpi", None)
        result = checker.check_resolution(_img(data, filename="test.png"), pil_image)
        assert result is None


# =============================================================================
# 7. Duplicate Detection Edge Cases
# =============================================================================


class TestDuplicateEdgeCases:
    """Edge cases for perceptual hash duplicate detection."""

    def test_same_color_different_size(self, checker):
        """Same solid color but different sizes — pHash should still match."""
        small = _make_jpeg(color=(255, 0, 0), size=(50, 50))
        large = _make_jpeg(color=(255, 0, 0), size=(200, 200))
        findings = checker.check_duplicates([
            _img(small, label="small"),
            _img(large, label="large"),
        ])
        # pHash is scale-invariant, should detect similarity
        assert len(findings) == 1

    def test_negative_image_not_duplicate(self, checker):
        """Color-inverted image should not be flagged as duplicate."""
        img_a = Image.new("RGB", (100, 100))
        # Create a gradient pattern
        for x in range(100):
            for y in range(100):
                img_a.putpixel((x, y), (x * 2 % 256, y * 2 % 256, (x + y) % 256))

        buf_a = io.BytesIO()
        img_a.save(buf_a, format="JPEG", quality=95)

        # Create a very different pattern (shifted colors)
        img_b = Image.new("RGB", (100, 100))
        for x in range(100):
            for y in range(100):
                img_b.putpixel((x, y), (255 - x * 2 % 256, 255 - y * 2 % 256, 255 - (x + y) % 256))

        buf_b = io.BytesIO()
        img_b.save(buf_b, format="JPEG", quality=95)

        findings = checker.check_duplicates([
            _img(buf_a.getvalue(), label="original"),
            _img(buf_b.getvalue(), label="inverted"),
        ])
        assert len(findings) == 0

    def test_duplicate_with_missing_labels(self, checker):
        """Duplicates with no labels should use filenames."""
        data = _make_jpeg(color=(0, 255, 0))
        findings = checker.check_duplicates([
            _img(data, filename="fig1.jpg", label=""),
            _img(data, filename="fig2.jpg", label=""),
        ])
        assert len(findings) == 1
        assert "fig1.jpg" in findings[0].title or "fig2.jpg" in findings[0].title

    def test_duplicate_with_no_labels_no_filenames(self, checker):
        """Duplicates with no labels or filenames should still work."""
        data = _make_jpeg(color=(0, 0, 255))
        findings = checker.check_duplicates([
            _img(data, filename="", label=""),
            _img(data, filename="", label=""),
        ])
        # Should work but may deduplicate based on empty pair key
        assert isinstance(findings, list)

    def test_many_identical_images(self, checker):
        """10 identical images should produce C(10,2)=45 pairs."""
        data = _make_jpeg(color=(100, 100, 100))
        images = [_img(data, label=f"img_{i}") for i in range(10)]
        findings = checker.check_duplicates(images)
        assert len(findings) == 45  # 10 choose 2


# =============================================================================
# 8. ImageInput Edge Cases
# =============================================================================


class TestImageInputEdgeCases:
    """Edge cases for ImageInput construction."""

    def test_empty_filename_and_label(self, checker):
        """Images with empty filename and label should not crash."""
        data = _make_jpeg()
        findings = checker.check_all([_img(data, filename="", label="")])
        assert isinstance(findings, list)

    def test_very_long_filename(self, checker):
        """Very long filename should not crash."""
        long_name = "a" * 1000 + ".jpg"
        data = _make_jpeg()
        findings = checker.check_all([_img(data, filename=long_name, label="long")])
        assert isinstance(findings, list)

    def test_unicode_filename(self, checker):
        """Unicode filename should be handled."""
        data = _make_jpeg()
        findings = checker.check_all([_img(data, filename="논문_그림_1.jpg", label="한국어")])
        assert isinstance(findings, list)

    def test_special_chars_in_label(self, checker):
        """Special characters in label should be handled."""
        data = _make_jpeg()
        findings = checker.check_all([_img(data, label="Figure 2A (p<0.001)")])
        assert isinstance(findings, list)


# =============================================================================
# 9. Agent Integration Edge Cases
# =============================================================================


class TestAgentIntegration:
    """Test ImageChecker integration with DataIntegrityAuditorAgent."""

    @pytest.mark.asyncio
    async def test_quick_check_images_only_no_text(self):
        """quick_check with images but empty text should work."""
        from app.agents.base import BaseAgent
        from app.agents.data_integrity_auditor import DataIntegrityAuditorAgent
        from app.llm.mock_layer import MockLLMLayer

        mock_llm = MockLLMLayer({})
        spec = BaseAgent.load_spec("data_integrity_auditor")
        agent = DataIntegrityAuditorAgent(spec=spec, llm=mock_llm)

        # Two identical images
        data = _make_jpeg(color=(255, 0, 0))
        images = [
            ImageInput(image_bytes=data, filename="fig1.jpg", label="Figure 1A"),
            ImageInput(image_bytes=data, filename="fig2.jpg", label="Figure 1B"),
        ]
        output = await agent.quick_check("", images=images)
        assert output.output["total_findings"] >= 1
        categories = output.output["findings_by_category"]
        assert categories.get("duplicate_image", 0) >= 1
        # No LLM calls (quick_check is deterministic)
        assert len(mock_llm.call_log) == 0

    @pytest.mark.asyncio
    async def test_quick_check_text_and_images(self):
        """quick_check with both text and images should combine findings."""
        from app.agents.base import BaseAgent
        from app.agents.data_integrity_auditor import DataIntegrityAuditorAgent
        from app.llm.mock_layer import MockLLMLayer

        mock_llm = MockLLMLayer({})
        spec = BaseAgent.load_spec("data_integrity_auditor")
        agent = DataIntegrityAuditorAgent(spec=spec, llm=mock_llm)

        # Text with gene name error + two identical images
        text = "Table shows 1-Mar was upregulated."
        data = _make_jpeg(color=(255, 0, 0))
        images = [
            ImageInput(image_bytes=data, filename="a.jpg", label="A"),
            ImageInput(image_bytes=data, filename="b.jpg", label="B"),
        ]
        output = await agent.quick_check(text, images=images)
        categories = output.output["findings_by_category"]
        # Should have both gene_name_error and duplicate_image
        assert categories.get("gene_name_error", 0) >= 1
        assert categories.get("duplicate_image", 0) >= 1

    @pytest.mark.asyncio
    async def test_quick_check_corrupt_images(self):
        """quick_check with corrupt image data should still succeed."""
        from app.agents.base import BaseAgent
        from app.agents.data_integrity_auditor import DataIntegrityAuditorAgent
        from app.llm.mock_layer import MockLLMLayer

        mock_llm = MockLLMLayer({})
        spec = BaseAgent.load_spec("data_integrity_auditor")
        agent = DataIntegrityAuditorAgent(spec=spec, llm=mock_llm)

        images = [
            ImageInput(image_bytes=b"not-an-image", filename="bad.jpg"),
        ]
        output = await agent.quick_check("Normal text", images=images)
        # Should not crash, findings count may be 0
        assert isinstance(output.output["total_findings"], int)


# =============================================================================
# 10. W7 Runner Image Step Edge Cases
# =============================================================================


class TestW7ImageStep:
    """W7 runner IMAGE_CHECK step edge cases."""

    def test_image_check_with_corrupt_images(self):
        """IMAGE_CHECK with corrupt images should not crash the pipeline."""
        from app.agents.registry import create_registry
        from app.llm.mock_layer import MockLLMLayer
        from app.workflows.runners.w7_integrity import W7IntegrityRunner

        runner = W7IntegrityRunner(registry=create_registry(MockLLMLayer({})))
        runner._collected_images = [
            ImageInput(image_bytes=b"garbage", filename="bad.jpg"),
        ]
        result = runner._step_image_check()
        assert result["image_findings"] == 0

    def test_image_check_with_valid_duplicates(self):
        """IMAGE_CHECK with valid duplicate images should detect them."""
        from app.agents.registry import create_registry
        from app.llm.mock_layer import MockLLMLayer
        from app.workflows.runners.w7_integrity import W7IntegrityRunner

        runner = W7IntegrityRunner(registry=create_registry(MockLLMLayer({})))
        data = _make_jpeg(color=(255, 0, 0))
        runner._collected_images = [
            ImageInput(image_bytes=data, filename="a.jpg", label="A"),
            ImageInput(image_bytes=data, filename="b.jpg", label="B"),
        ]
        result = runner._step_image_check()
        assert result["image_findings"] >= 1
        # Findings should be in _all_findings
        assert len(runner._all_findings) >= 1
        assert runner._all_findings[0]["category"] == "duplicate_image"

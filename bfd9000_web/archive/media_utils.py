"""Utilities for media processing and transformations."""

from __future__ import annotations

import logging
import shutil
import subprocess  # noqa: S404
import uuid
from io import BytesIO
from typing import IO, TYPE_CHECKING, TypedDict

import magic
from BFD9000.conf import settings
from mime_enum import MimeType
from PIL import Image, TiffImagePlugin
from pydicom.uid import (
    generate_uid as pydicom_generate_uid,
)

from archive.constants import RASTER_MIMES

if TYPE_CHECKING:
    from collections.abc import Iterable

    from archive.storage.django import ByteFile


logger = logging.getLogger(__name__)


def generate_dicom_uid(root: str) -> str:
    """Generate a DICOM-compliant UID using pydicom

    Ensures the root ends with a '.' as required by pydicom.

    Args:
        root: a root string

    Returns:
        DICOM-compliant UID

    """
    prefix: str = root if root.endswith(".") else f"{root}."
    if pydicom_generate_uid is not None:
        return str(pydicom_generate_uid(prefix=prefix))

    # Fallback: keep UID numeric with dots and cap to 64 chars.
    suffix = str(uuid.uuid4().int)
    max_suffix_length = max(1, 64 - len(prefix))
    return f"{prefix}{suffix[:max_suffix_length]}"


def get_bits_per_sample(img: Image.Image) -> int | None:
    """Best-effort extraction of TIFF bits-per-sample.

    Args:
        img: The TIFF image to extract from

    Returns:
        Optionaly, the number of bits per sample, if found

    """
    tag_v2: TiffImagePlugin.ImageFileDirectory_v2 | None = getattr(img, "tag_v2", None)
    if tag_v2 is None:
        return None
    # Type can be found from:
    # tags = TiffTags.TAGS_V2[TiffImagePlugin.BITSPERSAMPLE]
    # TiffTags.TYPES.get(tags.type) => short => int => int | tuple[int]
    bits: tuple[int, ...] | int | None = tag_v2.get(TiffImagePlugin.BITSPERSAMPLE)
    if bits is None:
        return None
    if isinstance(bits, tuple):
        return int(max(bits))
    return int(bits)


def resize_image_for_preview(img: Image.Image, max_dim: int = 1024) -> Image.Image:
    """Resize while preserving aspect ratio for display/preview.

    Args:
        img: The image to scale
        max_dim: The target dimension of the longer edge

    Returns:
        The scaled image

    """
    width, height = img.size
    largest = max(width, height)
    if largest <= max_dim:
        return img
    scale = max_dim / float(largest)
    new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    # Prefer NEAREST for 16-bit, else high-quality LANCZOS
    resample = (
        Image.Resampling.NEAREST
        if img.mode.startswith("I;16")
        else Image.Resampling.LANCZOS
    )
    return img.resize(new_size, resample)


class TransformOp(TypedDict):
    """Instructions for an operation upon an image"""

    rotation: int
    flip: bool


def apply_transform_ops(img: Image.Image, ops: Iterable[TransformOp]) -> Image.Image:
    """Apply ordered rotate/flip operations (e.g., for Record preview).

    Args:
        img: The input image to transform
        ops: The iterator of operations to apply

    Returns:
        The transformed image

    """
    transformed = img.copy()
    for op in ops:
        if op["rotation"]:
            transformed = transformed.rotate(-op["rotation"], expand=True)
        if op["flip"]:
            transformed = transformed.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    return transformed


def convert_tiff_to_png_bytes(upload: ByteFile | IO[bytes]) -> bytes:
    """Convert TIFF to PNG, preserving 16-bit grayscale if needed.

    Args:
        upload: The uploaded file to process

    Returns:
        PNG bytes for the image

    """
    with Image.open(upload) as img:
        bits_per_sample = get_bits_per_sample(img)
        high_bit_gray = bits_per_sample in {12, 16} or img.mode in {
            "I;16",
            "I;16L",
            "I;16B",
        }
        if high_bit_gray:
            gray = img
            if (
                gray.mode == "I;16B"
                or gray.mode not in {"I;16", "I;16L", "I"}
                # TODO: update why this is specifically 12, maybe make a const
                or (bits_per_sample == 12 and gray.mode != "I")  # noqa: PLR2004
            ):
                gray = gray.convert("I")
            png_image = gray.convert("I;16")
            png_image = resize_image_for_preview(png_image)
        else:
            png_image = resize_image_for_preview(img.convert("RGB"))
        buf = BytesIO()
        png_image.save(buf, format="PNG", optimize=True)
        return buf.getvalue()


def generate_stl_thumbnail(
    stl_file: BytesIO, width: int = 300, height: int = 300
) -> bytes | None:
    """Executes the Rust WGPU CLI engine completely using in-memory pipelines.

    Args:
        stl_file: The input file to generate a thumbnail for
        width: Number of horizontal pixels
        height: Number of vertical pixels

    Returns:
        A Django File object for the png generated

    """
    _ = stl_file.seek(0)
    input_bytes = stl_file.read()
    bin = shutil.which("stl-thumb")

    if not bin:
        logger.error("stl-thumb not found")
        return None

    try:
        process = subprocess.run(  # noqa: S603
            [
                bin,
                "--width",
                str(width),
                "--height",
                str(height),
                "--format",
                "webp",
            ],
            input=input_bytes,
            capture_output=True,
            check=True,
            timeout=5,  # Safe termination safety rail
        )

        # process.stdout contains the pure raw PNG binary data block
        return process.stdout

    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print(
            f"Rust render engine error output channel: {
                getattr(e, 'stderr', b'').decode()
            }"
        )
        return None


def generate_thumbnail_webp_bytes(
    fileobj: ByteFile,
    filename: str,
    transform_ops: Iterable[TransformOp] | None = None,
) -> bytes | None:
    """Unified thumbnail generator with transform_ops and TIFF PNG workflow.

    - For TIFF: converts to PNG bytes, reloads PNG as PIL, then continues.
    - For PNG/JPEG: loads via PIL.
    - For 3D/file types (stl, ply, obj): renders a thumbnail with bfd9000_thumb.

    Args:
        fileobj: The image file to generate a thumbnail for
        filename: The name of the image
        transform_ops: Iterable of transformation to apply to the image

    Returns:
        Bytes for JPEG thumbnail, or None (3D or unsupported)

    """
    file_size = getattr(fileobj, "size", None)
    # Check if an explicit size is exposed to optimize memory allocation
    if file_size and file_size > 0:
        raw_buffer = bytearray(file_size)  # pyright: ignore[reportAny]
        fileobj.readinto(raw_buffer)  # pyright: ignore[reportAny]
        mem_file = BytesIO(raw_buffer)
    else:
        mem_file = BytesIO(fileobj.read())  # pyright: ignore[reportAny]

    sample_bytes = mem_file.getvalue()[:4096]
    try:
        # Identify the true underlying mime type via header bytes
        mime_type = magic.from_buffer(sample_bytes, mime=True)
    except Exception:
        logger.error("Libmagic failed to inspect bytes for %s", filename, exc_info=True)
        return None

    if mime_type not in RASTER_MIMES:
        bytes = generate_stl_thumbnail(mem_file)
        if not bytes:
            return None
        img = Image.open(BytesIO(bytes))
        return _render_thumbnail_from_raster(img)

    img: Image.Image
    try:
        if mime_type in {MimeType.IMAGE_TIFF}:
            png_bytes = convert_tiff_to_png_bytes(mem_file)
            img = Image.open(BytesIO(png_bytes))
        else:
            img = Image.open(mem_file)

    except Exception:
        logger.warning(
            "Failed to open or parse image file: %s", filename, exc_info=True
        )
        return None

    if transform_ops:
        img = apply_transform_ops(img, transform_ops)

    try:
        return _render_thumbnail_from_raster(img)
    except Exception:
        logger.warning("Thumbnail rendering failed for %s", filename, exc_info=True)

    return None


def _render_thumbnail_from_raster(img: Image.Image) -> bytes | None:
    """Create WebP thumbnail bytes with project thumbnail compression policy.

    Target: 300x300 px, ~20KB, hard 100KB limit (from settings)

    Args:
        img: Input image

    Returns:
        Thumbnail as bytes if successful

    """
    max_width: int = int(getattr(settings, "THUMBNAIL_MAX_WIDTH", 300))
    max_height: int = int(getattr(settings, "THUMBNAIL_MAX_HEIGHT", 300))
    target_bytes: int = int(getattr(settings, "THUMBNAIL_TARGET_BYTES", 20 * 1024))
    hard_max_bytes: int = int(getattr(settings, "THUMBNAIL_HARD_MAX_BYTES", 100 * 1024))
    default_quality: int = int(getattr(settings, "THUMBNAIL_DEFAULT_QUALITY", 75))
    min_quality: int = int(getattr(settings, "THUMBNAIL_MIN_QUALITY", 40))

    processed: Image.Image = img.copy()

    if processed.mode in {"I", "I;16", "I;16B", "I;16L"}:
        # Convert to float, then grayscale
        processed = processed.convert("F")
        processed = processed.point(lambda x: x / 256)
        processed = processed.convert("L")
    elif processed.mode not in {"RGB", "RGBA"}:
        processed = processed.convert("RGBA")

    processed.thumbnail((max_width, max_height))

    quality = default_quality
    best_fit: bytes | None = None

    while quality >= min_quality:
        out = BytesIO()
        # Save explicitly as WEBP. Quality ranges from 0-100 (lossy mode)
        processed.save(out, format="WEBP", quality=quality)
        payload = out.getvalue()

        if len(payload) <= target_bytes:
            return payload
        if len(payload) <= hard_max_bytes:
            best_fit = payload

        quality -= 5

    return best_fit

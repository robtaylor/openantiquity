"""`clean_image`: only real, modest images get through, and nothing but their pixels survives."""

from __future__ import annotations

import io
import struct
import threading
import time
import zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from PIL import ExifTags, Image, PngImagePlugin

from fieldclub.errors import AppError
from fieldclub.services import media
from tests.helpers import run_fresh
from tests.media.support import GPS, phone_photo
from tests.moderation.support import jpeg, png


def reopen(data: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(data))
    image.load()
    return image


def test_the_photo_has_a_position_before_it_is_cleaned() -> None:
    raw = phone_photo()
    original = reopen(raw)
    assert original.getexif().get_ifd(ExifTags.IFD.GPSInfo)
    assert b"Silbury" in raw
    assert b"GPSLatitude" in raw


def test_cleaning_removes_every_bit_of_metadata() -> None:
    cleaned = media.clean_image(phone_photo())
    assert cleaned.content_type == "image/jpeg"
    image = reopen(cleaned.data)
    assert dict(image.getexif()) == {}
    assert image.getexif().get_ifd(ExifTags.IFD.GPSInfo) == {}
    assert set(image.info) <= {
        "jfif",
        "jfif_version",
        "jfif_unit",
        "jfif_density",
        "dpi",
        "progressive",
        "progression",
    }
    for marker in (b"Exif", b"GPS", b"Silbury", b"PhoneMaker", b"xmpmeta", b"2026:11:09"):
        assert marker not in cleaned.data, marker


def test_the_orientation_is_applied_before_it_is_dropped() -> None:
    # Orientation 6 means the camera was turned: the picture is shown rotated a quarter turn.
    cleaned = media.clean_image(phone_photo(orientation=6, width=40, height=20))
    assert (cleaned.width, cleaned.height) == (20, 40)
    assert reopen(cleaned.data).size == (20, 40)


def test_a_png_with_text_and_transparency_stays_a_png_without_the_text() -> None:
    info = PngImagePlugin.PngInfo()
    info.add_text("Location", "51.4157 N, 1.8575 W")
    raw = png(mode="RGBA", pnginfo=info)
    assert b"51.4157" in raw
    cleaned = media.clean_image(raw)
    assert cleaned.content_type == "image/png"
    assert b"51.4157" not in cleaned.data
    assert reopen(cleaned.data).mode == "RGBA"
    assert not {"Location", "exif", "icc_profile", "XML:com.adobe.xmp"} & set(reopen(cleaned.data).info)


def test_webp_is_read_and_stored_as_jpeg() -> None:
    out = io.BytesIO()
    Image.new("RGB", (16, 16), (1, 2, 3)).save(out, "WEBP")
    assert media.clean_image(out.getvalue()).content_type == "image/jpeg"


def test_a_big_photo_is_scaled_down() -> None:
    cleaned = media.clean_image(jpeg(media.MAX_SIDE + 500, 100))
    assert max(cleaned.width, cleaned.height) == media.MAX_SIDE


def _png_claiming(width: int, height: int) -> bytes:
    """A tiny PNG whose header claims `width` by `height`, which is what a decompression bomb is."""
    raw = bytearray(png(1, 1))
    ihdr = struct.pack(">II", width, height) + bytes(raw[24:29])
    raw[16:29] = ihdr
    raw[29:33] = struct.pack(">I", zlib.crc32(b"IHDR" + ihdr))
    return bytes(raw)


HOSTILE = {
    "a script named as a photo": (b"<script>alert(document.cookie)</script>", "not_an_image"),
    "an html page": (b"<!doctype html><html><body onload=alert(1)></body></html>", "not_an_image"),
    "an svg with a script": (
        b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
        "not_an_image",
    ),
    "nothing": (b"", "not_an_image"),
    "a truncated jpeg": (jpeg(400, 300)[:600], "not_an_image"),
    "a truncated png": (png(200, 200)[:-40], "not_an_image"),
    "a gif": (b"GIF89a\x01\x00\x01\x00\x00\x00\x00;", "not_an_image"),
    "a bomb past pillow's limit": (_png_claiming(30_000, 30_000), "image_too_many_pixels"),
    "a bomb under pillow's limit but over ours": (_png_claiming(8_000, 8_000), "image_too_many_pixels"),
    "too many bytes": (b"\xff\xd8" + b"\x00" * (media.MAX_UPLOAD_BYTES + 1), "image_too_large"),
}


@pytest.mark.parametrize("name", list(HOSTILE))
def test_hostile_uploads_are_refused(name: str) -> None:
    raw, code = HOSTILE[name]
    with pytest.raises(AppError) as caught:
        media.clean_image(raw)
    assert caught.value.code == code, name


def test_an_animation_is_refused() -> None:
    out = io.BytesIO()
    frames = [Image.new("RGB", (8, 8), (i * 40, 0, 0)) for i in range(3)]
    frames[0].save(out, "WEBP", save_all=True, append_images=frames[1:])
    with pytest.raises(AppError) as caught:
        media.clean_image(out.getvalue())
    assert caught.value.code == "unsupported_image"


def _multi_picture(*, orientation: int = 1) -> bytes:
    """A multi-picture JPEG with a position in it, as many phone cameras write."""
    exif = Image.Exif()
    exif[ExifTags.Base.Orientation] = orientation
    exif[ExifTags.IFD.GPSInfo] = GPS
    out = io.BytesIO()
    first, preview = Image.new("RGB", (40, 20), (200, 10, 10)), Image.new("RGB", (40, 20), (10, 200, 10))
    first.save(out, "MPO", save_all=True, append_images=[preview], exif=exif.tobytes())
    return out.getvalue()


def test_a_multi_picture_jpeg_is_read_as_its_first_picture_without_its_position() -> None:
    raw = _multi_picture(orientation=6)
    original = Image.open(io.BytesIO(raw))
    assert (original.format, getattr(original, "n_frames", 1)) == ("MPO", 2)
    assert original.getexif().get_ifd(ExifTags.IFD.GPSInfo)
    cleaned = media.clean_image(raw)
    assert cleaned.content_type == "image/jpeg"
    image = reopen(cleaned.data)
    assert image.format == "JPEG"
    assert image.size == (20, 40)
    assert image.getexif().get_ifd(ExifTags.IFD.GPSInfo) == {}
    assert b"Exif" not in cleaned.data
    pixel = image.getpixel((10, 20))
    assert isinstance(pixel, tuple)
    assert pixel[0] > 150 > pixel[1], "the first picture, not the preview"


def test_a_huge_picture_in_a_tiny_file_is_refused() -> None:
    # Flat colour compresses to almost nothing, which is what makes a cheap bomb.
    side = media.MAX_SIDE + 1000
    raw = png(side, side)
    assert len(raw) < side * side * media.MIN_BYTES_PER_PIXEL
    with pytest.raises(AppError) as caught:
        media.clean_image(raw)
    assert caught.value.code == "image_too_many_pixels"
    # The same picture at MAX_SIDE squared is fine, however small its file.
    assert media.clean_image(png(media.MAX_SIDE, media.MAX_SIDE)).width == media.MAX_SIDE


def _noisy_jpeg(width: int, height: int) -> bytes:
    """A JPEG with enough detail to be the size of a real photo."""
    noise = Image.effect_noise((width // 10, height // 10), 60).convert("RGB")
    out = io.BytesIO()
    noise.resize((width, height)).save(out, "JPEG", quality=80)
    return out.getvalue()


def test_a_big_jpeg_is_decoded_at_a_fraction_of_its_size() -> None:
    raw = _noisy_jpeg(6400, 4800)
    assert media._open(raw).size == (3200, 2400)
    cleaned = media.clean_image(raw)
    assert (cleaned.width, cleaned.height) == (3200, 2400)


def test_a_48_megapixel_photo_is_cleaned_in_modest_memory(tmp_path: Path) -> None:
    # Before decoding was bounded this took over 400 MB on top of what the process held.
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(_noisy_jpeg(8000, 6000))
    run_fresh(
        "import pathlib, resource, sys\n"
        "from fieldclub.services import media\n"
        f"raw = pathlib.Path({str(photo)!r}).read_bytes()\n"
        "unit = 1 if sys.platform == 'darwin' else 1024\n"
        "before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * unit\n"
        "cleaned = media.clean_image(raw)\n"
        "grew = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * unit - before\n"
        "assert (cleaned.width, cleaned.height) == (4000, 3000), (cleaned.width, cleaned.height)\n"
        "assert grew < 250 * 1024 * 1024, f'grew by {grew / 2**20:.0f} MB'\n"
    )


def test_only_so_many_uploads_are_decoded_at_once(monkeypatch: pytest.MonkeyPatch) -> None:
    lock = threading.Lock()
    running, most = 0, 0

    def slow_clean(raw: bytes) -> str:
        nonlocal running, most
        with lock:
            running += 1
            most = max(most, running)
        time.sleep(0.05)
        with lock:
            running -= 1
        return "cleaned"

    monkeypatch.setattr(media, "_clean", slow_clean)
    with ThreadPoolExecutor(max_workers=media.DECODE_SLOTS + 3) as pool:
        results = list(pool.map(media.clean_image, [b"x"] * (media.DECODE_SLOTS + 3)))
    assert results == ["cleaned"] * (media.DECODE_SLOTS + 3)
    assert most == media.DECODE_SLOTS


def test_an_upload_that_waits_too_long_for_its_turn_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(media, "DECODE_WAIT_SECONDS", 0.01)
    held = [media._decode_slots.acquire(timeout=1) for _ in range(media.DECODE_SLOTS)]
    assert all(held)
    try:
        with pytest.raises(media.UploadsBusyError) as caught:
            media.clean_image(jpeg())
        assert (caught.value.status_code, caught.value.code) == (503, "uploads_busy")
    finally:
        for _ in held:
            media._decode_slots.release()
    assert media.clean_image(jpeg()).content_type == "image/jpeg"

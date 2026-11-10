"""Photos for the media tests. Import as `from tests.media.support import ...`."""

from __future__ import annotations

from PIL import ExifTags, Image

from tests.moderation.support import jpeg

# Silbury Hill, as a phone would write it into a photo.
GPS = {
    ExifTags.GPS.GPSLatitudeRef: "N",
    ExifTags.GPS.GPSLatitude: (51.0, 24.0, 56.6),
    ExifTags.GPS.GPSLongitudeRef: "W",
    ExifTags.GPS.GPSLongitude: (1.0, 51.0, 26.9),
}


def phone_photo(*, orientation: int = 1, width: int = 40, height: int = 20) -> bytes:
    exif = Image.Exif()
    exif[ExifTags.Base.Make] = "PhoneMaker"
    exif[ExifTags.Base.Model] = "Phone 12"
    exif[ExifTags.Base.Orientation] = orientation
    exif[ExifTags.Base.DateTime] = "2026:11:09 14:03:11"
    exif[ExifTags.IFD.GPSInfo] = GPS
    xmp = b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><exif:GPSLatitude>51,24.94N</exif:GPSLatitude></x:xmpmeta>'
    return jpeg(width, height, exif=exif.tobytes(), comment=b"Shot at Silbury Hill", xmp=xmp)

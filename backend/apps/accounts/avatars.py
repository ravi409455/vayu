"""Profile pictures: whatever the person uploads becomes one small square JPEG with no metadata.

The checks look at the file's real content, never its name: size first (before decoding
anything), then a full decode, only JPEG / PNG / WebP, a pixel limit against decompression bombs.
Rotation from the camera is applied, the picture is cropped to a square from the centre, shrunk to
256 px and saved again, which drops every piece of metadata (location included)."""
import io

from PIL import Image, ImageOps, UnidentifiedImageError

from apps.core.errors import CodedError

MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 40_000_000          # about a 6000 x 6000 photo; more is refused
SIZE = 256
ALLOWED = {"JPEG", "PNG", "WEBP"}


def _bad(code: str, message: str, status: int = 400) -> CodedError:
    return CodedError(code, message, status)


def process(data: bytes) -> bytes:
    """The stored picture for an uploaded file, or a CodedError saying what is wrong."""
    if not data:
        raise _bad("INVALID_IMAGE", "Choose a picture to upload.")
    if len(data) > MAX_BYTES:
        raise _bad("IMAGE_TOO_LARGE", "The picture must be 5 MB or smaller.", 413)
    previous = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS              # beyond this Pillow refuses to decode
    try:
        with Image.open(io.BytesIO(data)) as probe:
            if probe.format not in ALLOWED:
                raise _bad("INVALID_IMAGE", "Use a JPEG, PNG or WebP picture.")
            if probe.width * probe.height > MAX_PIXELS:
                raise _bad("IMAGE_TOO_LARGE", "That picture has too many pixels.", 413)
            probe.verify()
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            picture = ImageOps.exif_transpose(image) or image
            picture = picture.convert("RGB")
    except Image.DecompressionBombError:
        raise _bad("IMAGE_TOO_LARGE", "That picture has too many pixels.", 413) from None
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise _bad("INVALID_IMAGE", "That file is not a usable picture.") from None
    finally:
        Image.MAX_IMAGE_PIXELS = previous
    side = min(picture.size)
    left, top = (picture.width - side) // 2, (picture.height - side) // 2
    square = picture.crop((left, top, left + side, top + side)).resize(
        (SIZE, SIZE), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    square.save(out, "JPEG", quality=85)            # a fresh file: no EXIF, no GPS
    return out.getvalue()

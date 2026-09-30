"""Animations as GIF files, with a see-through background, via Pillow.

GIF knows one fully transparent palette entry and nothing half see-through,
so pixels more than half transparent become background and all others solid.
All frames share one palette of at most 255 colours - plenty for pixel art,
which keeps its colours exactly.
"""

import io

import pygame

try:
    from PIL import Image
    PIL_ERROR = ''
except ImportError:
    PIL_ERROR = 'Pillow is missing - pip install -r build_tools/requirements.txt'

GIF_FRAME_MS = 140       # like the preview in the tool
GIF_SCALE = 1            # the sprites are large already; whole numbers keep pixel art crisp
ALPHA_CUTOFF = 128       # at least this opaque counts as solid
TRANSPARENT_INDEX = 255


def to_image(surface):
    return Image.frombytes('RGBA', surface.get_size(), pygame.image.tobytes(surface, 'RGBA'))


def gif_bytes(frames, frame_ms=GIF_FRAME_MS, scale=GIF_SCALE):
    """An endlessly looping GIF of pygame surfaces of one size.

    Raises:
        RuntimeError: If Pillow is not installed.
    """
    if PIL_ERROR:
        raise RuntimeError(PIL_ERROR)
    images = [to_image(f) for f in frames]
    if scale != 1:
        images = [im.resize((im.width * scale, im.height * scale), Image.NEAREST) for im in images]

    # One palette for all frames, from the colours of every frame side by side
    strip = Image.new('RGB', (sum(im.width for im in images), max(im.height for im in images)))
    x = 0
    for im in images:
        strip.paste(im.convert('RGB'), (x, 0))
        x += im.width
    palette = strip.quantize(colors=TRANSPARENT_INDEX, method=Image.Quantize.MAXCOVERAGE)

    frames_p = []
    for im in images:
        indexed = im.convert('RGB').quantize(palette=palette, dither=Image.Dither.NONE)
        see_through = im.getchannel('A').point(lambda a: 255 if a < ALPHA_CUTOFF else 0)
        indexed.paste(TRANSPARENT_INDEX, mask=see_through)
        frames_p.append(indexed)

    buffer = io.BytesIO()
    frames_p[0].save(buffer, 'GIF', save_all=True, append_images=frames_p[1:], duration=frame_ms,
                     loop=0, transparency=TRANSPARENT_INDEX, disposal=2, optimize=False)
    return buffer.getvalue()

"""Animations as MP4 videos, via PyAV, for programs that mangle GIFs (WhatsApp).

H.264 in yuv420p is what every phone and chat program plays. A video knows
nothing see-through, so the frames sit on a plain background. The walk is
repeated until the video lasts VIDEO_MIN_SECONDS, since a chat plays a video
once rather than looping it, and scaled up by whole numbers so the pixel art
stays crisp and is not tiny on a phone.
"""

import math
from fractions import Fraction

import pygame

from gif_export import GIF_FRAME_MS

try:
    import av
    AV_ERROR = ''
except ImportError:
    AV_ERROR = 'PyAV is missing - pip install -r build_tools/requirements.txt'

VIDEO_BACKGROUND = (255, 255, 255)
VIDEO_MIN_SECONDS = 4
VIDEO_MIN_HEIGHT = 480    # scaled up by whole numbers until at least this tall
VIDEO_CRF = 18            # x264 quality: lower is better, 18 is close to lossless to the eye


def write_video(frames, path, frame_ms=GIF_FRAME_MS):
    """Save pygame surfaces of one size as an MP4 at path, played at frame_ms per frame.

    Raises:
        RuntimeError: If PyAV is not installed.
    """
    if AV_ERROR:
        raise RuntimeError(AV_ERROR)
    width, height = frames[0].get_size()
    scale = max(1, math.ceil(VIDEO_MIN_HEIGHT / height))
    # yuv420p needs even sides
    size = ((width * scale + 1) // 2 * 2, (height * scale + 1) // 2 * 2)
    repeats = max(1, math.ceil(VIDEO_MIN_SECONDS * 1000 / (frame_ms * len(frames))))

    images = []
    for frame in frames:
        canvas = pygame.Surface(size)
        canvas.fill(VIDEO_BACKGROUND)
        big = pygame.transform.scale(frame, (width * scale, height * scale))
        canvas.blit(big, (0, 0))
        images.append(pygame.image.tobytes(canvas, 'RGB'))

    with av.open(str(path), 'w', format='mp4', options={'movflags': '+faststart'}) as container:
        stream = container.add_stream('libx264', rate=Fraction(1000, frame_ms))
        stream.width, stream.height = size
        stream.pix_fmt = 'yuv420p'
        stream.options = {'crf': str(VIDEO_CRF), 'preset': 'slow'}
        for _ in range(repeats):
            for rgb in images:
                image = av.VideoFrame(size[0], size[1], 'rgb24')
                image.planes[0].update(_padded_rows(rgb, size[0] * 3, image.planes[0].line_size))
                container.mux(stream.encode(image.reformat(format='yuv420p')))
        container.mux(stream.encode())


def _padded_rows(rgb, row_bytes, line_size):
    """Packed RGB rows stretched to the plane's line size, which may be padded."""
    if row_bytes == line_size:
        return rgb
    padding = bytes(line_size - row_bytes)
    return b''.join(rgb[i:i + row_bytes] + padding for i in range(0, len(rgb), row_bytes))

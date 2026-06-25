import pygame

# Corner size in pixels of the source frame image used for 9-slice scaling.
# The source image is 200x155. 30px covers the ornate corner decorations
# without eating into the stretchable edge or center regions.
FRAME_CORNER = 30


def scale_9slice(image: pygame.Surface, size: tuple, corner: int = FRAME_CORNER) -> pygame.Surface:
    """Return a new Surface with *image* scaled to *size* using 9-slice logic.

    Corners are copied at original size; edges are stretched in one axis only;
    the centre is stretched in both axes. This keeps corner ornaments sharp.
    """
    iw, ih = image.get_size()
    w, h = size
    c = corner

    result = pygame.Surface((w, h), pygame.SRCALPHA)

    # source regions
    src_tl = pygame.Rect(0,      0,      c,       c)
    src_tc = pygame.Rect(c,      0,      iw-2*c,  c)
    src_tr = pygame.Rect(iw-c,   0,      c,       c)
    src_ml = pygame.Rect(0,      c,      c,       ih-2*c)
    src_mc = pygame.Rect(c,      c,      iw-2*c,  ih-2*c)
    src_mr = pygame.Rect(iw-c,   c,      c,       ih-2*c)
    src_bl = pygame.Rect(0,      ih-c,   c,       c)
    src_bc = pygame.Rect(c,      ih-c,   iw-2*c,  c)
    src_br = pygame.Rect(iw-c,   ih-c,   c,       c)

    pieces = [
        (src_tl, (0,       0),       (c,     c)),
        (src_tc, (c,       0),       (w-2*c, c)),
        (src_tr, (w-c,     0),       (c,     c)),
        (src_ml, (0,       c),       (c,     h-2*c)),
        (src_mc, (c,       c),       (w-2*c, h-2*c)),
        (src_mr, (w-c,     c),       (c,     h-2*c)),
        (src_bl, (0,       h-c),     (c,     c)),
        (src_bc, (c,       h-c),     (w-2*c, c)),
        (src_br, (w-c,     h-c),     (c,     c)),
    ]

    for src_rect, dst_pos, dst_size in pieces:
        piece = pygame.transform.scale(image.subsurface(src_rect), dst_size)
        result.blit(piece, dst_pos)

    return result


def draw_9slice(surface: pygame.Surface, image: pygame.Surface,
                rect: pygame.Rect, corner: int = FRAME_CORNER) -> None:
    """Draw *image* onto *surface* at *rect* using 9-slice scaling."""
    scaled = scale_9slice(image, (rect.width, rect.height), corner)
    surface.blit(scaled, rect)

"""Small pygame surface helpers shared by the whole tool."""

import pygame

from create_new_pose import THUMB_BG


def trim(surface):
    """Cut away the transparent border."""
    return surface.subsurface(surface.get_bounding_rect()).copy()


def scaled(surface, factor):
    """Scale by a whole number, pixel for pixel."""
    w, h = surface.get_size()
    return pygame.transform.scale(surface, (w * factor, h * factor))


def smooth_fit(surface, size, max_factor=None):
    """The surface smoothly scaled to fit into `size`, keeping its proportions."""
    w, h = surface.get_size()
    factor = min(size[0] / w, size[1] / h)
    if max_factor is not None:
        factor = min(factor, max_factor)
    return pygame.transform.smoothscale(surface, (max(1, int(w * factor)), max(1, int(h * factor))))


def pixel_fit(surface, size):
    """The surface fitted into `size`: blown up by whole pixels, so pixel art stays crisp."""
    w, h = surface.get_size()
    factor = int(min(size[0] / w, size[1] / h))
    return scaled(surface, factor) if factor >= 1 else smooth_fit(surface, size)


def fitted(surface, size, background=THUMB_BG):
    """A surface scaled into a tile of `size`, centred."""
    image = smooth_fit(surface, size)
    tile = pygame.Surface(size)
    tile.fill(background)
    tile.blit(image, image.get_rect(center=tile.get_rect().center))
    return tile


def mirrored(surface):
    return pygame.transform.flip(surface, True, False)


def load_frame(path):
    """One of the NPC's saved frames, or None if it is not there or cannot be read right now.

    A frame can vanish or be half written at any moment while GIMP or another
    program saves over it, so a failed read is not an error, only a frame
    that is not there yet.
    """
    try:
        return pygame.image.load(str(path)).convert_alpha()
    except (pygame.error, OSError):
        return None


def is_blank(surface):
    """True for a missing or fully transparent image."""
    return not (surface and surface.get_bounding_rect().w)


def save_copy(source, target, mirror):
    """Save one image file as another, flipped if asked.

    Raises:
        pygame.error, OSError: If either file cannot be handled.
    """
    image = pygame.image.load(str(source)).convert_alpha()
    pygame.image.save(mirrored(image) if mirror else image, str(target))


def crop_alike(frames):
    """Crop frames that share one canvas to the box around all of them."""
    rects = [f.get_bounding_rect() for f in frames if f.get_bounding_rect().w]
    box = rects[0].unionall(rects[1:]) if rects else frames[0].get_rect()
    return [f.subsurface(box.clip(f.get_rect())).copy() for f in frames]

"""The Windows clipboard, for handing sheets to the Gemini web view and back.

pygame.scrap only moves text reliably, and tkinter none of the image formats
a browser understands, so this talks to user32 directly. An image is put on
the clipboard twice - as "PNG", which browsers prefer, and as a device
independent bitmap for everything else - and read back from whichever of
those is there, or from a file copied in the Explorer.

Everything returns a message instead of raising: the tool only reports it.
"""

import ctypes
import io
import struct
import sys
import time
from ctypes import wintypes

AVAILABLE = sys.platform == 'win32'

CF_DIB = 8
CF_UNICODETEXT = 13
CF_HDROP = 15
CF_DIBV5 = 17
GMEM_MOVEABLE = 0x0002
OPEN_ATTEMPTS = 10       # another program may hold the clipboard for a moment
OPEN_RETRY_S = 0.03
BMP_FILE_HEADER = 14
BI_BITFIELDS = 3

if AVAILABLE:
    _user32 = ctypes.WinDLL('user32', use_last_error=True)
    _kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    _shell32 = ctypes.WinDLL('shell32', use_last_error=True)

    _user32.OpenClipboard.argtypes = [wintypes.HWND]
    _user32.OpenClipboard.restype = wintypes.BOOL
    _user32.CloseClipboard.restype = wintypes.BOOL
    _user32.EmptyClipboard.restype = wintypes.BOOL
    _user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    _user32.SetClipboardData.restype = wintypes.HANDLE
    _user32.GetClipboardData.argtypes = [wintypes.UINT]
    _user32.GetClipboardData.restype = wintypes.HANDLE
    _user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
    _user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
    _user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
    _user32.RegisterClipboardFormatW.restype = wintypes.UINT
    _kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    _kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    _kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    _kernel32.GlobalLock.restype = ctypes.c_void_p
    _kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    _kernel32.GlobalUnlock.restype = wintypes.BOOL
    _kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]
    _kernel32.GlobalSize.restype = ctypes.c_size_t
    _kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    _kernel32.GlobalFree.restype = wintypes.HGLOBAL
    _shell32.DragQueryFileW.argtypes = [wintypes.HANDLE, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
    _shell32.DragQueryFileW.restype = wintypes.UINT


class ClipboardError(RuntimeError):
    pass


class _Open:
    """Holds the clipboard open for the duration of a with block."""

    def __enter__(self):
        if not AVAILABLE:
            raise ClipboardError('The clipboard is only supported on Windows.')
        for _ in range(OPEN_ATTEMPTS):
            if _user32.OpenClipboard(None):
                return self
            time.sleep(OPEN_RETRY_S)
        raise ClipboardError('The clipboard is busy - try again.')

    def __exit__(self, *exc):
        _user32.CloseClipboard()
        return False


def _png_format():
    return _user32.RegisterClipboardFormatW('PNG')


def _put(fmt, data):
    handle = _kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    if not handle:
        raise ClipboardError('Out of memory for the clipboard.')
    pointer = _kernel32.GlobalLock(handle)
    ctypes.memmove(pointer, data, len(data))
    _kernel32.GlobalUnlock(handle)
    # After a successful SetClipboardData the clipboard owns the memory.
    if not _user32.SetClipboardData(fmt, handle):
        _kernel32.GlobalFree(handle)
        raise ClipboardError('Windows refused the clipboard data.')


def _get(fmt):
    """The raw bytes of one clipboard format, or None."""
    if not _user32.IsClipboardFormatAvailable(fmt):
        return None
    handle = _user32.GetClipboardData(fmt)
    if not handle:
        return None
    pointer = _kernel32.GlobalLock(handle)
    if not pointer:
        return None
    try:
        return ctypes.string_at(pointer, _kernel32.GlobalSize(handle))
    finally:
        _kernel32.GlobalUnlock(handle)


def copy_text(text):
    """Puts text on the clipboard, replacing what was there."""
    with _Open():
        _user32.EmptyClipboard()
        _put(CF_UNICODETEXT, (text + '\0').encode('utf-16-le'))


def copy_image(surface):
    """Puts a pygame surface on the clipboard as PNG and as a bitmap."""
    import pygame  # noqa: PLC0415 - the module itself does not need pygame

    image = surface.convert() if surface.get_bitsize() != 24 else surface
    png, bmp = io.BytesIO(), io.BytesIO()
    pygame.image.save(image, png, 'sheet.png')
    pygame.image.save(image, bmp, 'sheet.bmp')
    with _Open():
        _user32.EmptyClipboard()
        _put(_png_format(), png.getvalue())
        _put(CF_DIB, bmp.getvalue()[BMP_FILE_HEADER:])


def _dib_to_bmp(dib):
    """A device independent bitmap with the file header it lacks."""
    header_size, = struct.unpack_from('<I', dib, 0)
    bit_count, compression = struct.unpack_from('<HI', dib, 14)
    colors_used, = struct.unpack_from('<I', dib, 32)
    colors = colors_used or (1 << bit_count if bit_count <= 8 else 0)
    masks = 12 if compression == BI_BITFIELDS and header_size == 40 else 0
    offset = BMP_FILE_HEADER + header_size + masks + colors * 4
    return struct.pack('<2sIHHI', b'BM', BMP_FILE_HEADER + len(dib), 0, 0, offset) + dib


def _copied_files():
    handle = _user32.GetClipboardData(CF_HDROP)
    if not handle:
        return []
    count = _shell32.DragQueryFileW(handle, 0xFFFFFFFF, None, 0)
    files = []
    for index in range(count):
        length = _shell32.DragQueryFileW(handle, index, None, 0) + 1
        buffer = ctypes.create_unicode_buffer(length)
        _shell32.DragQueryFileW(handle, index, buffer, length)
        files.append(buffer.value)
    return files


def paste_image():
    """What the clipboard holds that could be an image.

    Returns:
        ('png', bytes), ('bmp', bytes), ('file', path) or None.

    Raises:
        ClipboardError: If the clipboard cannot be opened.
    """
    with _Open():
        data = _get(_png_format())
        if data:
            return 'png', data
        for fmt in (CF_DIBV5, CF_DIB):
            data = _get(fmt)
            if data:
                return 'bmp', _dib_to_bmp(data)
        if _user32.IsClipboardFormatAvailable(CF_HDROP):
            files = _copied_files()
            if files:
                return 'file', files[0]
    return None

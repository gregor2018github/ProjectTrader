"""The base of every screen of the Sprite Manager.

The app (Sprite_Manager.SpriteManager) owns what all screens share - the
window, fonts, API settings, the chosen NPC and its review store, the Gemini
worker, the status line - and shows one View at a time. A View draws the
area between header and footer and handles the input the app does not.
"""


class View:
    def __init__(self, app):
        self.app = app

    def header(self):
        """(title, hint) for the top of the window."""
        return '', ''

    def footer(self):
        """(left buttons, right buttons) along the foot of the window.

        The app's own back, folder and settings buttons may be among them;
        the app handles those.
        """
        return (), ()

    def update_footer(self):
        """Bring footer labels and enabled states up to date, before drawing."""

    def draw(self, screen, mouse):
        """Draw the body of the screen."""

    def click(self, pos):
        """A left click that hit none of the app's buttons."""

    def key(self, event):
        """A key the app has no use for."""

    def right_click(self, pos):
        """A right click."""

    def mouse_motion(self, pos, buttons):
        """The mouse moved; buttons as pygame's event.buttons (left, middle, right)."""

    def mouse_up(self, pos, button):
        """A mouse button let go."""

    def captures_keys(self):
        """True while typing into the view, so every key goes to it and none to the app."""
        return False

    def text_input(self, text):
        """Text typed while captures_keys()."""

    def scroll_by(self, steps):
        """Mouse wheel, steps > 0 is up."""

    def drop_file(self, path):
        """A file dropped onto the window."""

    def back(self):
        """Escape or Back; returns False if there is nowhere to go back to."""
        return False

    def refresh(self):
        """Files or answers changed; rebuild what is shown from them."""

    def tick(self):
        """Once per frame while the screen is shown."""

"""Send reference sheets to Gemini and get the finished sheet back.

Used by create_new_pose.py, which builds the 2x2 sheets and the prompt and
then lets the image model fill in the empty cell.

The API key is looked for in this order:

    1. the environment variable GEMINI_API_KEY
    2. GEMINI_API_KEY=... in a .env file in the project root
    3. a file holding nothing but the key, in the virtual environment
       (trade_envi/GEMINI_API_KEY.txt), or in the project root, or wherever
       GEMINI_API_KEY_FILE points

None of these places can be committed: .gitignore excludes .env and the
virtual environment, and venv itself writes a .gitignore with '*' into it.

Needs the SDK:

    pip install google-genai

The module imports without the SDK; SDK_ERROR then says what is missing and
every request fails with that message instead of crashing the tool.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path

try:
    from google import genai
    from google.genai import errors, types
    SDK_ERROR = ''
except ImportError as exc:  # the tool stays usable without the SDK installed
    genai = errors = types = None
    SDK_ERROR = f'{exc} - run: pip install google-genai'

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / '.env'
ENV_KEY = 'GEMINI_API_KEY'
ENV_KEY_FILE = 'GEMINI_API_KEY_FILE'  # path to a file holding nothing but the key
ENV_MODEL = 'GEMINI_IMAGE_MODEL'
ENV_EXTRA_MODELS = 'GEMINI_IMAGE_MODELS'  # comma separated, added to the list below

# Files searched for a bare key, after the environment and .env. The virtual
# environment is a good place for it: venv writes a .gitignore with '*' there,
# so the key cannot be committed by accident.
KEY_FILE_NAME = 'GEMINI_API_KEY.txt'

SETTINGS_FILE = Path(__file__).resolve().parent / 'output' / 'pose_settings.json'

# Image models offered in the tool: (model id, what it is good for). The
# preview builds of these are left out on purpose; "Fetch models" in the
# settings dialog asks the API for everything the key can reach, and
# GEMINI_IMAGE_MODELS adds fixed ones.
IMAGE_MODELS = (
    ('gemini-3.1-flash-image', 'fast and cheap, a good default'),
    ('gemini-3-pro-image', 'Nano Banana Pro - best likeness, 1K/2K/4K'),
    ('gemini-3.1-flash-lite-image', 'cheapest, for many tries at once'),
    ('gemini-2.5-flash-image', 'the original Nano Banana'),
)
DEFAULT_MODEL = IMAGE_MODELS[0][0]

# '' means: let the model keep the proportions/size of the sheet it was given.
ASPECT_RATIOS = ('', '1:1', '2:3', '3:2', '3:4', '4:3', '9:16', '16:9', '21:9')
IMAGE_SIZES = ('', '1K', '2K', '4K')
MAX_TRIES = 4  # answers that can be requested per sheet in one go

RETRYABLE_CODES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 4
BASE_BACKOFF_S = 2.0
# A 429 saying one of these is a daily or an unpaid quota, not a burst: it
# will not clear within the backoff, so the sheet fails right away instead of
# blocking the queue for half a minute.
HARD_QUOTA_HINTS = ('PerDay', 'limit: 0')
# What a key without billing gets back for every image model.
NO_BILLING_HINT = ('image generation is not part of the free tier - '
                   'enable billing for the API key')

MIME_TO_SUFFIX = {'image/png': '.png', 'image/jpeg': '.jpg', 'image/webp': '.webp'}


class GeminiError(RuntimeError):
    """Raised when a sheet could not be generated.

    Attributes:
        code: The HTTP status the API answered with, 0 for local problems.
    """

    def __init__(self, message: str, code: int = 0) -> None:
        super().__init__(message)
        self.code = code


def is_retryable(exc) -> bool:
    """Whether waiting a moment could make this API error go away."""
    if exc.code not in RETRYABLE_CODES:
        return False
    return not (exc.code == 429 and any(hint in str(exc) for hint in HARD_QUOTA_HINTS))


def describe_error(exc) -> str:
    """One readable line out of an API error, instead of its JSON dump."""
    message = (getattr(exc, 'message', '') or str(exc)).strip()
    if exc.code == 429 and 'limit: 0' in str(exc):
        return f'API error 429: {NO_BILLING_HINT}'
    if len(message) > 200:
        message = message[:200].rsplit(' ', 1)[0] + ' ...'
    return f'API error {exc.code}: {message}'


@dataclass(frozen=True)
class GeneratedImage:
    """One image returned by the model."""

    data: bytes
    mime_type: str
    model_text: str = ''

    @property
    def suffix(self) -> str:
        """File extension matching the returned MIME type."""
        return MIME_TO_SUFFIX.get(self.mime_type, '.png')


@dataclass(frozen=True)
class Settings:
    """What to ask the image model for; edited in the tool's settings dialog."""

    model: str = DEFAULT_MODEL
    aspect_ratio: str = ''   # '' = keep the sheet's proportions
    image_size: str = ''     # '' = the model's own default (1K)
    tries: int = 1           # answers requested per sheet

    def summary(self) -> str:
        """One line for the footer, e.g. 'gemini-2.5-flash-image, 1:1, 2K, 2x'."""
        parts = [self.model, self.aspect_ratio or 'sheet ratio', self.image_size or 'default size']
        if self.tries > 1:
            parts.append(f'{self.tries} tries')
        return ', '.join(parts)

    def image_config(self):
        """types.ImageConfig for the chosen size settings, or None if unset."""
        if types is None or not (self.aspect_ratio or self.image_size):
            return None
        return types.ImageConfig(aspect_ratio=self.aspect_ratio or None,
                                 image_size=self.image_size or None)

    def with_values(self, **changes) -> Settings:
        return replace(self, **changes)

    @classmethod
    def load(cls, path: Path = SETTINGS_FILE) -> Settings:
        """Reads the settings last used, falling back to the defaults."""
        try:
            stored = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            stored = {}
        known = {key: stored[key] for key in cls.__dataclass_fields__ if key in stored}
        try:
            settings = cls(**known)
            return settings.with_values(tries=max(1, min(MAX_TRIES, int(settings.tries))))
        except (TypeError, ValueError):
            return cls()

    def save(self, path: Path = SETTINGS_FILE) -> None:
        """Remembers the settings for the next run; failures are ignored."""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(asdict(self), indent=2) + '\n', encoding='utf-8')
        except OSError:
            pass


def read_env_file(path: Path = ENV_FILE) -> dict:
    """Reads simple KEY=VALUE lines from a .env file.

    Args:
        path: The .env file. A missing file yields an empty mapping.

    Returns:
        The parsed values, without quotes around them.
    """
    values = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def env_value(key: str) -> str:
    """The environment wins over the .env file; '' when neither has the key."""
    return os.environ.get(key) or read_env_file().get(key, '')


def key_files() -> list:
    """Files that may hold the key, in the order they are searched.

    The virtual environment comes first, then the project root; a path in
    GEMINI_API_KEY_FILE wins over both.
    """
    named = env_value(ENV_KEY_FILE)
    candidates = [Path(named)] if named else []
    candidates += [Path(sys.prefix) / KEY_FILE_NAME,
                   ROOT / 'trade_envi' / KEY_FILE_NAME,
                   ROOT / KEY_FILE_NAME]
    unique = []
    for path in candidates:
        if path not in unique:
            unique.append(path)
    return unique


def read_key_file(path: Path) -> str:
    """The key from a file holding it as raw text, '' if there is none.

    A file written as GEMINI_API_KEY=... is understood as well.
    """
    try:
        text = path.read_text(encoding='utf-8-sig')
    except OSError:
        return ''
    for line in text.splitlines():
        line = line.strip().strip('"').strip("'")
        if not line or line.startswith('#'):
            continue
        if line.upper().startswith(ENV_KEY + '='):
            line = line.split('=', 1)[1].strip().strip('"').strip("'")
        return line
    return ''


def load_api_key() -> str:
    """Returns the API key from the environment, the .env file or a key file.

    Raises:
        GeminiError: If no key is configured anywhere.
    """
    key = env_value(ENV_KEY)
    for path in key_files():
        if key:
            break
        key = read_key_file(path)
    if not key:
        places = ', '.join(str(path) for path in key_files()[-3:])
        raise GeminiError(
            f'No API key. Set {ENV_KEY} in the environment or in {ENV_FILE.name} '
            f'in the project root, or put the key as plain text into one of: {places}'
        )
    return key


def known_models() -> list:
    """Model ids offered in the settings dialog, extras from the environment last."""
    models = [model for model, _ in IMAGE_MODELS]
    for extra in env_value(ENV_EXTRA_MODELS).split(',') + [env_value(ENV_MODEL)]:
        extra = extra.strip()
        if extra and extra not in models:
            models.append(extra)
    return models


def model_note(model: str) -> str:
    """The short description of a model, or '' for one that was added later."""
    return dict(IMAGE_MODELS).get(model, '')


class GeminiClient:
    """Thin wrapper around the Gemini image models for sheet completion."""

    def __init__(self, api_key: str = '') -> None:
        """Creates the client.

        Args:
            api_key: API key; taken from the environment or .env when omitted.

        Raises:
            GeminiError: If the SDK is missing or no API key is configured.
        """
        if genai is None:
            raise GeminiError(SDK_ERROR)
        self._client = genai.Client(api_key=api_key or load_api_key())

    def complete_sheet(self, prompt: str, sheet_bytes: bytes, settings: Settings,
                       mime_type: str = 'image/png') -> GeneratedImage:
        """Sends one sheet plus its prompt and returns the model's image.

        Args:
            prompt: The instruction text for this sheet.
            sheet_bytes: The reference sheet as encoded image bytes.
            settings: Model and output size to ask for.
            mime_type: MIME type of the sheet.

        Returns:
            The first image the model returned.

        Raises:
            GeminiError: On API errors, blocked prompts, or a reply without
                an image.
        """
        contents = [types.Part.from_bytes(data=sheet_bytes, mime_type=mime_type), prompt]
        response = self._generate(settings, contents)

        if not response.candidates:
            feedback = response.prompt_feedback
            raise GeminiError(f'Request blocked ({feedback.block_reason if feedback else "unknown"})')

        candidate = response.candidates[0]
        parts = candidate.content.parts if candidate.content and candidate.content.parts else []
        model_text = '\n'.join(part.text for part in parts if part.text).strip()
        for part in parts:
            if part.inline_data and part.inline_data.data:
                return GeneratedImage(
                    data=part.inline_data.data,
                    mime_type=part.inline_data.mime_type or 'image/png',
                    model_text=model_text,
                )
        raise GeminiError(f'No image returned ({candidate.finish_reason}): {model_text[:200]}')

    def discover_models(self) -> list:
        """Image model ids the account can currently reach.

        Returns:
            The ids, sorted. Used to offer models newer than IMAGE_MODELS.

        Raises:
            GeminiError: If the model list cannot be read.
        """
        try:
            listing = list(self._client.models.list())
        except Exception as exc:  # the SDK wraps several transport errors here
            raise GeminiError(f'Could not list models: {exc}') from exc
        found = set()
        for model in listing:
            name = (model.name or '').split('/')[-1]
            actions = model.supported_actions or ()
            if 'image' in name and (not actions or 'generateContent' in actions):
                found.add(name)
        return sorted(found)

    # --- requests ---------------------------------------------------------

    def _generate(self, settings: Settings, contents: list):
        """Calls the model, once with the size settings and once without them.

        Not every model accepts an aspect ratio or an image size; when one
        rejects the setting the sheet is still worth trying at the model's
        own default rather than failing the whole run.
        """
        image_config = settings.image_config()
        try:
            return self._call_with_retry(settings.model, contents, image_config)
        except GeminiError as exc:
            # Only a rejected request is worth a second try; a quota or a key
            # problem would fail exactly the same way without the config.
            if image_config is None or exc.code != 400:
                raise
            return self._call_with_retry(settings.model, contents, None)

    def _call_with_retry(self, model: str, contents: list, image_config):
        """Calls the model, retrying rate limits and server errors.

        Raises:
            GeminiError: If the error is not retryable or all attempts failed.
        """
        config = types.GenerateContentConfig(
            response_modalities=['TEXT', 'IMAGE'],
            image_config=image_config,
            # Nothing here calls tools; without this the SDK warns on every request.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                return self._client.models.generate_content(
                    model=model, contents=contents, config=config)
            except errors.APIError as exc:
                if attempt == MAX_ATTEMPTS or not is_retryable(exc):
                    raise GeminiError(describe_error(exc), exc.code) from exc
                time.sleep(BASE_BACKOFF_S * 2 ** (attempt - 1))
        raise GeminiError('unreachable')


def next_free_path(folder: Path, stem: str, suffix: str) -> Path:
    """Returns a path that does not exist yet, numbering repeated tries.

    vintner_front_move1_gemini.png, then _gemini_2.png, _gemini_3.png, ...

    Args:
        folder: Target folder.
        stem: File name without the counter and extension.
        suffix: File extension, including the dot.

    Returns:
        The first free path.
    """
    path = folder / f'{stem}{suffix}'
    counter = 2
    while path.exists():
        path = folder / f'{stem}_{counter}{suffix}'
        counter += 1
    return path

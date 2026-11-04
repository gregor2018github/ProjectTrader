---
name: make-release
description: Publish a new Windows release of Merchant's Rise (MerchantsRise-<version>-windows.zip on GitHub Releases) and remove the previous one, so only the latest release is kept. Use when the user asks for a new release, a new version, a new build for players, or to "ship"/"publish" the game.
---

# Make a release

A release is a GitHub release holding one zip, `MerchantsRise-<version>-windows.zip`
(about 250 MB): `MerchantsRise.exe` plus `_internal/`, needing nothing installed.
The zips are **not** in git (`/release/` is ignored); they live only as release assets.

The user keeps **only the latest release**: old ones are deleted, release and tag,
once the new one is up. Anyone wanting an old version can build it from the source.

## How it is built

Pushing a tag `v<version>` runs `.github/workflows/release.yml` on a Windows runner:
it runs `build_tools/Release/build_release.py <version>` (PyInstaller one-folder
build in its own venv, then a smoke test: the exe starts a new game, plays a few
seconds and must exit 0) and publishes the zip with `gh release create`. A run takes
about 2 minutes. If the smoke test fails, no release is created.

Only git-tracked assets go in, minus what the game never loads (`EXCLUDED_SUFFIXES`,
`EXCLUDED_FOLDERS`, `EXCLUDED_FOLDER_PREFIXES` in `build_release.py`). So an
untracked sound or sprite the code uses will be missing from the release.

## Steps

1. **Check the tree.** `git status`: everything the release should contain is
   committed and pushed (`main...origin/main` not ahead). The usual leftovers
   (`saves/`, `settings.json`) are not shipped anyway. If the code loads a file
   that is untracked, say so and get it committed first.
   `python -m pytest -q` passes.
2. **Check new kinds of files.** If the game started loading a new kind of file or
   folder since the last release (`git log <last tag>..HEAD --stat`), make sure the
   exclusions in `build_release.py` do not drop it.
3. **Pick the version.** Find the current one with `gh release list`. Bump the
   minor (`0.1.0` -> `0.2.0`) for a normal release with new features; the patch
   (`0.2.0` -> `0.2.1`) for fixes only; say which you chose. Ask only if the user
   hinted at a big milestone (`1.0.0`).
4. **Tag and push** at the pushed `HEAD` (lightweight tags, as before):
   ```bash
   git tag v<version> && git push origin v<version>
   ```
5. **Watch the build** to the end:
   ```bash
   RUN=$(gh run list --workflow release.yml --limit 1 --json databaseId --jq '.[0].databaseId')
   gh run watch $RUN --exit-status --interval 20 > /dev/null; echo $?
   gh release view v<version> --json url,assets --jq '.url, (.assets[] | "\(.name) \(.size)")'
   ```
   On failure: `gh run view $RUN --log-failed`, fix, then delete the tag
   (`git push origin :refs/tags/v<version>; git tag -d v<version>`) and tag again.
   The old release is still in place, so nothing is lost.
6. **Remove the old release(s)** only after the new one is published with its zip:
   ```bash
   gh release delete v<old> --cleanup-tag --yes   # also deletes the remote tag and, here, the local one
   git tag -d v<old> 2>/dev/null; rm -f release/MerchantsRise-<old>-windows.zip
   gh release list; git ls-remote --tags origin  # only the new one left
   ```
7. **Report** the release URL and size, the version chosen and what was removed.

A local build (`py build_tools/Release/build_release.py <version>`) is only needed to
debug a failing CI run; it writes to `release/` and takes a few minutes.

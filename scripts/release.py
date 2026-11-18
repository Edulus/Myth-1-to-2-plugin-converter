"""Build, and optionally publish, the ready-made *Sir Mauriac's Tale* download.

The GitHub release ``sir-mauriac-sb-1`` carries one zip: CbC's TFL campaign
converted by the current converter, with every stock TFL tag built in, plus a
Read Me and CbC's credits. It does not update itself, so it has to be rebuilt
after every converter version that changes the output; between 16 and 17
November 2026 it sat at 0.12 while 0.13-0.18 shipped, and testers using it
were testing old work. The steps are in documentation/site-and-releases.md;
this script is those steps.

Build only (writes the zip and prints its checksum; changes nothing public):

    python scripts/release.py --tfl-tags "<TFL>/TAGS"

Build and publish (uploads, updates the release notes, checks a fresh
download, then updates the site's download constants and rebuilds the site;
commit and push afterwards):

    python scripts/release.py --tfl-tags "<TFL>/TAGS" --publish

The source plugin and the two text files are kept in the git-ignored
``local/release/`` (see that section of the documentation). ``--tfl-tags``
may also come from the environment variable ``TFL_TAGS_DIR``.
"""

import argparse
import hashlib
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import __version__  # noqa: E402

RELEASE_TAG = "sir-mauriac-sb-1"
REPO = "Edulus/Myth-1-to-2-plugin-converter"
ZIP_NAME = "Sir-Mauriac-Tale-for-Myth-II.zip"
PLUGIN_NAME = "ZZ Mauriac TFL2SB"
README_NAME = "Sir Mauriac's Tale - Read Me.txt"
CREDITS_NAME = "Sir Mauriac's Tale - Credits.txt"
LOCAL = ROOT / "local" / "release"
SITE = ROOT / "scripts" / "keep_site.py"
DOWNLOAD_URL = f"https://github.com/{REPO}/releases/download/{RELEASE_TAG}/{ZIP_NAME}"

README_VERSION = re.compile(r"made with version [0-9][0-9.]* of the converter")

NOTES = (
    "Sir Mauriac's Tale by CbC, converted for Myth II 1.8.5 with the Myth Plugin "
    "Converter (version {version}). Extract the zip straight into Myth II's plugins "
    "folder, then New Game and choose the campaign ZZ Mauriac TFL2SB. Nothing else "
    "to install. SHA-256: {sha}"
)


class ReleaseError(Exception):
    """A step failed; nothing after it was done."""


def readme_for(text, version):
    """The Read Me with its version line set to ``version``, in Windows line
    endings (the zip is for Windows players; Notepad on older systems shows LF
    files as one line). Exactly one version line must be present."""
    found = README_VERSION.findall(text)
    if len(found) != 1:
        raise ReleaseError(f"the Read Me should have one 'made with version X of the converter' line, has {len(found)}")
    text = README_VERSION.sub(f"made with version {version} of the converter", text)
    return text.replace("\r\n", "\n").replace("\n", "\r\n")


def build_zip(zip_path, plugin, readme_text, credits):
    """The release zip: three files at its top level, no folder."""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.write(plugin, PLUGIN_NAME)
        z.writestr(README_NAME, readme_text.encode("utf-8"))
        z.write(credits, CREDITS_NAME)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def site_constants(text, sha, megabytes, version):
    """keep_site.py with its three download constants replaced."""
    for name, value in (("DOWNLOAD_SHA256", f'"{sha}"'), ("DOWNLOAD_MB", str(megabytes)),
                        ("DOWNLOAD_VERSION", f'"{version}"')):
        text, n = re.subn(rf"^{name} = .*$", f"{name} = {value}", text, count=1, flags=re.M)
        if n != 1:
            raise ReleaseError(f"{name} not found in {SITE.name}")
    return text


def run(cmd, **kw):
    print("  $", " ".join(str(c) for c in cmd))
    done = subprocess.run(cmd, cwd=ROOT, **kw)
    if done.returncode:
        raise ReleaseError(f"command failed ({done.returncode}): {cmd[0]} {cmd[1] if len(cmd) > 1 else ''}")
    return done


def convert(source, out, tfl_tags):
    stock = [tfl_tags / "TAGS.GOR", tfl_tags / "ARTSOUND.GOR"]
    for p in stock + [source]:
        if not p.is_file():
            raise ReleaseError(f"not found: {p}")
    cmd = [sys.executable, "-m", "src", "convert", "--in", source, "--out", out, "--name", PLUGIN_NAME, "--force"]
    for p in stock:
        cmd += ["--stock", p]
    cmd.append("--all-stock")
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    run(cmd, env=env, stdout=subprocess.DEVNULL)


def verify_download(expected_sha, version):
    """Fetch the published zip as a player would and check it."""
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / ZIP_NAME
        urllib.request.urlretrieve(DOWNLOAD_URL, path)
        got = sha256(path)
        if got != expected_sha:
            raise ReleaseError(f"downloaded zip has SHA-256 {got}, expected {expected_sha}")
        with zipfile.ZipFile(path) as z:
            readme = z.read(README_NAME).decode("utf-8")
        if f"made with version {version} of the converter" not in readme:
            raise ReleaseError("downloaded zip's Read Me does not name this version")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--tfl-tags", type=pathlib.Path, default=os.environ.get("TFL_TAGS_DIR"),
                    help="your TFL tags folder, holding TAGS.GOR and ARTSOUND.GOR (or set TFL_TAGS_DIR)")
    ap.add_argument("--source", type=pathlib.Path, default=LOCAL / "cbc.TFL.mauriac.gor")
    ap.add_argument("--readme", type=pathlib.Path, default=LOCAL / README_NAME)
    ap.add_argument("--credits", type=pathlib.Path, default=LOCAL / CREDITS_NAME)
    ap.add_argument("--out-dir", type=pathlib.Path, default=None,
                    help="where to build (default local/release/build-<version>)")
    ap.add_argument("--publish", action="store_true",
                    help="upload to the GitHub release, check a fresh download, update the site")
    args = ap.parse_args(argv)
    if not args.tfl_tags:
        ap.error("--tfl-tags (or TFL_TAGS_DIR) is required")

    version = __version__
    out_dir = args.out_dir or LOCAL / f"build-{version}"
    out_dir.mkdir(parents=True, exist_ok=True)
    plugin = out_dir / PLUGIN_NAME
    zip_path = out_dir / ZIP_NAME

    try:
        for p in (args.readme, args.credits):
            if not p.is_file():
                raise ReleaseError(f"not found: {p}")
        print(f"1. Converting with converter {version}")
        convert(args.source, plugin, args.tfl_tags)
        print("2. Zipping the plugin, Read Me and credits")
        readme = readme_for(args.readme.read_text(encoding="utf-8"), version)
        build_zip(zip_path, plugin, readme, args.credits)
        sha = sha256(zip_path)
        megabytes = round(zip_path.stat().st_size / 1_000_000)
        print(f"   {zip_path}\n   {megabytes} MB, SHA-256 {sha}")
        if not args.publish:
            print("Built only. Run again with --publish to upload it.")
            return 0

        print("3. Uploading to the GitHub release")
        run(["gh", "release", "upload", RELEASE_TAG, zip_path, "--clobber", "--repo", REPO])
        run(["gh", "release", "edit", RELEASE_TAG, "--repo", REPO,
             "--notes", NOTES.format(version=version, sha=sha)])
        print("4. Checking a fresh download")
        verify_download(sha, version)
        print("5. Updating the site's download constants and rebuilding the site")
        SITE.write_text(site_constants(SITE.read_text(encoding="utf-8"), sha, megabytes, version), encoding="utf-8")
        run([sys.executable, str(SITE)], env=dict(os.environ, PYTHONIOENCODING="utf-8"), stdout=subprocess.DEVNULL)
        print(f"Published {version}. Now commit scripts/keep_site.py and docs/, and push.")
        return 0
    except ReleaseError as exc:
        print(f"Stopped: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

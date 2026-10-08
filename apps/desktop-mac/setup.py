"""py2app build configuration for Researchly.app.

Build:      python3 setup.py py2app          (see build_app.sh)
Dev build:  python3 setup.py py2app -A       (alias mode — links to this
            folder instead of bundling; fast, but the app only works on
            this machine with this Python env. Fine for personal use!)

Bundling spaCy + numpy makes a large app (~400-600 MB) and py2app can need
coaxing; if the full build misbehaves, use alias mode — for a personal
tool it is effectively equivalent.
"""

import importlib.util
import sys
from pathlib import Path
from setuptools import setup

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "packages" / "core"))  # so py2app finds `researchly`

APP = ["researchly_app.py"]
DATA_FILES = [("assets", ["assets/menubar.png"])]


def installed(candidates):
    """py2app crashes on any listed package that isn't importable
    (e.g. `langcodes` is a usual spaCy dependency but absent in some
    installs) — so bundle only what actually exists in this Python."""
    kept, skipped = [], []
    for name in candidates:
        try:
            spec = importlib.util.find_spec(name)
        except (ImportError, ModuleNotFoundError, ValueError):
            spec = None
        (kept if spec else skipped).append(name)
    if skipped:
        print(f"py2app packages skipped (not installed): {skipped}")
    print(f"py2app packages bundled: {kept}")
    return kept

OPTIONS = {
    "argv_emulation": False,
    "plist": {
        "CFBundleName": "Researchly",
        "CFBundleDisplayName": "Researchly",
        "CFBundleIdentifier": "local.researchly.desktop",
        "CFBundleShortVersionString": "0.5.0",
        "LSUIElement": True,              # menu-bar app: no Dock icon
        "NSHumanReadableCopyright": "Local personal build",
    },
    # the heavy lifting: make sure the engine and its stack are bundled.
    # 'researchly' brings data/scientific_terms.txt; 'symspellpy' brings its
    # frequency dictionary (both live inside the package directories, which
    # py2app copies wholesale).
    #
    # language_tool_python IS bundled (it used to be left out deliberately).
    # Leaving it out meant the built app had no grammar tier at all, and
    # said nothing about it — the same silent-failure the health layer
    # exists to end. It is only the Python wrapper: LanguageTool itself
    # (~259 MB of Java) still downloads to ~/.cache on first use, and
    # health.find_java() locates a JDK even when Homebrew installed it
    # keg-only. If neither is present the app now SAYS the grammar tier is
    # off, with the remedy, instead of quietly checking less than it claims.
    "packages": installed([
        "researchly", "spacy", "en_core_web_sm", "thinc", "numpy",
        "srsly", "catalogue", "wasabi", "blis", "preshed", "cymem",
        "murmurhash", "spacy_legacy", "spacy_loggers", "langcodes",
        "language_data", "symspellpy", "pydantic", "pydantic_core",
        "typing_extensions", "smart_open", "weasel", "confection",
        "language_tool_python",
        # File readers (S2): LaTeX by parsing, .docx without XXE. Without
        # them the app falls back to regex LaTeX masking and says so.
        "pylatexenc", "defusedxml",
        # language_tool_python downloads LanguageTool over HTTPS with
        # requests on first use. py2app pulled requests in but not its
        # dependency chain, so the built app warned
        # "Unable to find acceptable character detection dependency" and
        # would have had no CA bundle to verify the download with — the
        # grammar tier would have failed for every tester with a cold
        # ~/.cache, while working here because ours is warm.
        "requests", "urllib3", "certifi", "idna", "charset_normalizer",
        "tqdm",
    ]),
    "includes": ["panel_html"],
    "excludes": ["pytest", "pip", "setuptools", "tkinter"],
}

setup(
    app=APP,
    name="Researchly",
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)

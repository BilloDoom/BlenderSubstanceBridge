import py_compile
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src" / "substance_texture_hookup"
DIST = ROOT / "dist"
VERSION = "1.1.0"

ADDON = SRC / "__init__.py"
MANIFEST = SRC / "blender_manifest.toml"


def main():
    py_compile.compile(str(ADDON), doraise=True, cfile=str(ROOT / ".build.pyc"))
    (ROOT / ".build.pyc").unlink(missing_ok=True)

    DIST.mkdir(exist_ok=True)

    extension_zip = DIST / f"substance_texture_hookup-{VERSION}.zip"
    with zipfile.ZipFile(extension_zip, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(MANIFEST, "blender_manifest.toml")
        archive.write(ADDON, "__init__.py")

    legacy_py = DIST / "substance_texture_hookup.py"
    shutil.copyfile(ADDON, legacy_py)

    legacy_zip = DIST / f"substance_texture_hookup-{VERSION}-legacy.zip"
    with zipfile.ZipFile(legacy_zip, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(ADDON, "substance_texture_hookup/__init__.py")

    for path in (extension_zip, legacy_py, legacy_zip):
        print(f"{path.relative_to(ROOT)}  {path.stat().st_size} bytes")


if __name__ == "__main__":
    main()

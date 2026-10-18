import base64
import hashlib
import io
import tarfile
import urllib.request
from pathlib import Path

VERSION = "6.4.299"
INTEGRITY = "AVl138zALtfaAPvADulE0PZThbYzCBS79nL4pOSL/6Sm/4AH5A21BD9VHt97OlCuzJuCpmeZtAtkinisF4Vb1g=="
ROOT = Path(__file__).resolve().parents[1] / "src" / "paper_sa" / "static" / "vendor" / "pdfjs"
FILES = {"legacy/build/pdf.mjs", "legacy/build/pdf.worker.mjs", "LICENSE"}
PREFIXES = ("cmaps/", "standard_fonts/", "wasm/")


def main():
    url = f"https://registry.npmjs.org/pdfjs-dist/-/pdfjs-dist-{VERSION}.tgz"
    with urllib.request.urlopen(url, timeout=120) as response:
        archive = response.read()
    if base64.b64encode(hashlib.sha512(archive).digest()).decode() != INTEGRITY:
        raise RuntimeError("PDF.js package integrity verification failed")
    ROOT.mkdir(parents=True, exist_ok=True)
    count = 0
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as bundle:
        for member in bundle.getmembers():
            relative = member.name.removeprefix("package/")
            if not member.isfile() or not (relative in FILES or relative.startswith(PREFIXES)):
                continue
            target = (ROOT / relative).resolve()
            if not target.is_relative_to(ROOT.resolve()):
                raise RuntimeError("Unsafe archive path")
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.extractfile(member) as source:
                target.write_bytes(source.read())
            count += 1
    print(f"Vendored PDF.js {VERSION}: {count} files, verified SHA-512.")


if __name__ == "__main__":
    main()

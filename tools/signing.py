"""Shared helpers for PC Advisor data signing (ECDSA P-256 / SHA-256).

Private key: never stored in this repository.
  Default location: %USERPROFILE%\\.pcadvisor\\data_signing_key.pem
  Override with the environment variable PCADVISOR_SIGNING_KEY=<full path>.
  The key file is encrypted with a passphrase you choose.
Public key: tools/data_signing_public.txt (safe to publish, the app contains the same value).
"""
import base64, getpass, os, pathlib, sys

TOOLS = pathlib.Path(__file__).resolve().parent
ROOT = TOOLS.parent
PUBLIC_KEY_FILE = TOOLS / "data_signing_public.txt"
SIG_FILE = ROOT / "manifest.json.sig"


def need_crypto():
    try:
        import cryptography  # noqa: F401
    except ImportError:
        sys.exit("Missing library. Run once:  python -m pip install cryptography")


def private_key_path():
    p = os.environ.get("PCADVISOR_SIGNING_KEY")
    if p:
        return pathlib.Path(p)
    return pathlib.Path.home() / ".pcadvisor" / "data_signing_key.pem"


def ask_passphrase(confirm=False):
    p = os.environ.get("PCADVISOR_SIGNING_PASSPHRASE")
    if p:
        return p.encode("utf-8")
    p = getpass.getpass("Signing key passphrase: ")
    if confirm and p != getpass.getpass("Repeat passphrase: "):
        sys.exit("Passphrases do not match.")
    if len(p) < 8:
        sys.exit("Passphrase must be at least 8 characters.")
    return p.encode("utf-8")


def load_private_key():
    need_crypto()
    from cryptography.hazmat.primitives import serialization
    path = private_key_path()
    if not path.exists():
        sys.exit(f"Private key not found: {path}\nRun tools/make_signing_key.py first "
                 "or set PCADVISOR_SIGNING_KEY to the key file on your backup drive.")
    try:
        return serialization.load_pem_private_key(path.read_bytes(), password=ask_passphrase())
    except (ValueError, TypeError):
        sys.exit("Wrong passphrase (or damaged key file). Nothing was signed.")


def load_public_key():
    need_crypto()
    from cryptography.hazmat.primitives import serialization
    der = base64.b64decode(PUBLIC_KEY_FILE.read_text(encoding="ascii").strip())
    return serialization.load_der_public_key(der)


def sign(data: bytes) -> str:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    sig = load_private_key().sign(data, ec.ECDSA(hashes.SHA256()))
    return base64.b64encode(sig).decode("ascii")


def verify(data: bytes, sig_b64: str) -> bool:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    try:
        load_public_key().verify(base64.b64decode(sig_b64.strip()), data, ec.ECDSA(hashes.SHA256()))
        return True
    except (InvalidSignature, ValueError):
        return False

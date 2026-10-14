"""Run ONCE to create the PC Advisor data signing key pair.

  python tools/make_signing_key.py

- Writes the PRIVATE key (encrypted with your passphrase) OUTSIDE the repository
  (default %USERPROFILE%\\.pcadvisor\\data_signing_key.pem).
- Writes the PUBLIC key to tools/data_signing_public.txt and prints it (paste it into the app).
Back up the private key file AND the passphrase in 2 offline places (like pcadvisorkey).
If the private key is lost, you must ship an app update with a new public key.
"""
import base64, sys
from signing import ask_passphrase, need_crypto, private_key_path, PUBLIC_KEY_FILE

need_crypto()
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

path = private_key_path()
if path.exists():
    sys.exit(f"A key already exists at {path}. Refusing to overwrite it.")

key = ec.generate_private_key(ec.SECP256R1())
pem = key.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.BestAvailableEncryption(ask_passphrase(confirm=True)),
)
path.parent.mkdir(parents=True, exist_ok=True)
path.write_bytes(pem)

der = key.public_key().public_bytes(
    serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
pub = base64.b64encode(der).decode("ascii")
PUBLIC_KEY_FILE.write_text(pub + "\n", encoding="ascii")

print(f"Private key (keep secret, back it up twice): {path}")
print(f"Public key written to: {PUBLIC_KEY_FILE}")
print("\nPUBLIC KEY (for the app):\n" + pub)

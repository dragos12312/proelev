"""
Generate a self-signed TLS cert for the FastAPI dev server.

Writes certs/key.pem and certs/cert.pem in this folder. By default the cert
covers localhost and 127.0.0.1; pass any extra IPs/DNS names as args and
they will be added as Subject Alternative Names.

usage:
    python make_cert.py                           # localhost only
    python make_cert.py 192.168.56.1              # add the LAN IP

Run this once on the server machine before starting uvicorn with
    --ssl-keyfile certs/key.pem --ssl-certfile certs/cert.pem
"""
import ipaddress
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa


CERTS_DIR = Path(__file__).resolve().parent / "certs"
CERTS_DIR.mkdir(exist_ok=True)
KEY_PATH  = CERTS_DIR / "key.pem"
CERT_PATH = CERTS_DIR / "cert.pem"


def _san(name: str):
    """Decide whether the SAN entry is an IP or a DNS name."""
    try:
        ip = ipaddress.ip_address(name)
        return x509.IPAddress(ip)
    except ValueError:
        return x509.DNSName(name)


def generate(extra_names: list[str]) -> None:
    # 2048 bit rsa is plenty for a dev cert, faster than 4096 to generate
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "ProElev dev cert"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "ProElev"),
    ])

    names = ["localhost", "127.0.0.1"]
    names.extend(n for n in extra_names if n not in names)
    sans = [_san(n) for n in names]

    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(x509.SubjectAlternativeName(sans), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )

    KEY_PATH.write_bytes(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    CERT_PATH.write_bytes(cert.public_bytes(serialization.Encoding.PEM))

    print(f"wrote {KEY_PATH}")
    print(f"wrote {CERT_PATH}")
    print(f"covers: {', '.join(names)}")
    print()
    print("start uvicorn with:")
    print(
        "  python -m uvicorn main:app --host 0.0.0.0 --port 8000 "
        f"--ssl-keyfile {KEY_PATH.relative_to(Path.cwd()) if Path.cwd() in KEY_PATH.parents else KEY_PATH} "
        f"--ssl-certfile {CERT_PATH.relative_to(Path.cwd()) if Path.cwd() in CERT_PATH.parents else CERT_PATH}"
    )


if __name__ == "__main__":
    generate(sys.argv[1:])

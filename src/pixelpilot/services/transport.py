"""Per-instance TLS certificate: trust the issued certificate, never disable verification."""
from __future__ import annotations

import base64
import ssl
from datetime import UTC, datetime, timedelta

def issue_certificate() -> tuple[str, str]:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'PixelPilot private worker')])
    now = datetime.now(UTC)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(key, hashes.SHA256()))
    pem = cert.public_bytes(serialization.Encoding.PEM).decode('ascii')
    private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    return pem, base64.b64encode(private).decode('ascii')

def trusted_context(certificate: str) -> ssl.SSLContext:
    context = ssl.create_default_context(cadata=certificate)
    # Vast's IP/mapped port is assigned after provisioning. Trust is pinned to
    # our unique certificate instead of a public DNS name.
    context.check_hostname = False
    return context

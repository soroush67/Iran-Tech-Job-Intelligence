"""`certs` one-shot: put a TLS certificate where nginx expects it.

Real certificate: drop fullchain.pem + privkey.pem into ./nginx/certs (mounted at
/custom-certs) - they are copied. Otherwise a self-signed one is generated once
(for the PUBLIC_BASE_URL host) so HTTPS works out of the box on a LAN.
"""
import datetime
import ipaddress
import os
import shutil
import sys
from urllib.parse import urlsplit

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

OUT = "/certs"
CUSTOM = "/custom-certs"


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    cf, ck = os.path.join(CUSTOM, "fullchain.pem"), os.path.join(CUSTOM, "privkey.pem")
    if os.path.isfile(cf) and os.path.isfile(ck):
        shutil.copyfile(cf, os.path.join(OUT, "fullchain.pem"))
        shutil.copyfile(ck, os.path.join(OUT, "privkey.pem"))
        os.chmod(os.path.join(OUT, "privkey.pem"), 0o640)
        print("certs: using the provided certificate")
        return 0
    if os.path.isfile(os.path.join(OUT, "fullchain.pem")):
        print("certs: existing certificate kept")
        return 0
    host = urlsplit(os.environ.get("PUBLIC_BASE_URL", "https://localhost")).hostname or "localhost"
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    names: list[x509.GeneralName] = [x509.DNSName("localhost")]
    try:
        names.append(x509.IPAddress(ipaddress.ip_address(host)))
    except ValueError:
        names.append(x509.DNSName(host))
    names.append(x509.IPAddress(ipaddress.ip_address("127.0.0.1")))
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, host)])
    now = datetime.datetime.now(datetime.UTC)
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(minutes=5))
            .not_valid_after(now + datetime.timedelta(days=825))
            .add_extension(x509.SubjectAlternativeName(names), critical=False)
            .sign(key, hashes.SHA256()))
    with open(os.path.join(OUT, "privkey.pem"), "wb") as f:
        f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                  serialization.NoEncryption()))
    with open(os.path.join(OUT, "fullchain.pem"), "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    print(f"certs: self-signed certificate generated for {host}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

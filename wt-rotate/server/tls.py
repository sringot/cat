"""
Certificat TLS auto-signé pour servir la télécommande en HTTPS.

Le micro du navigateur (getUserMedia / MediaRecorder) n'est accessible qu'en
« contexte sécurisé » : HTTPS, ou localhost. Le téléphone arrive par l'IP du
réseau local — donc en HTTP simple, pas de micro possible. On génère ici un
certificat auto-signé (valable pour l'IP locale) à installer une fois sur les
téléphones qui doivent utiliser l'assistant vocal au micro.

Requiert : pip install cryptography
"""
import datetime
import ipaddress
import ssl
from pathlib import Path

CERT_FILE = Path(__file__).parent.parent / 'cert.pem'
KEY_FILE  = Path(__file__).parent.parent / 'key.pem'


def _cert_covers_ip(ip: str) -> bool:
    """Le certificat existant couvre-t-il déjà cette IP ? Sinon il faut le régénérer."""
    try:
        from cryptography import x509
        cert = x509.load_pem_x509_certificate(CERT_FILE.read_bytes())
        san  = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        ips  = [str(i) for i in san.value.get_values_for_type(x509.IPAddress)]
        return ip in ips
    except Exception:
        return False


def ensure_cert(ip: str) -> bool:
    """Génère le certificat s'il manque ou ne couvre plus l'IP.

    Retourne False si la lib `cryptography` est absente ou l'écriture échoue
    (le serveur tourne alors en HTTP seul, sans micro vocal).
    """
    if CERT_FILE.exists() and KEY_FILE.exists() and _cert_covers_ip(ip):
        return True
    # Tout sous un seul garde-fou : si `cryptography` est absent OU mal installé
    # (backend natif cassé → PanicException, pas une ImportError), on retourne
    # False et le serveur tourne en HTTP seul plutôt que de planter.
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        key  = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'wee rotate')])
        sans = [x509.DNSName('localhost'),
                x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]
        try:
            sans.append(x509.IPAddress(ipaddress.ip_address(ip)))
        except ValueError:
            pass

        now  = datetime.datetime.utcnow()
        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            # iOS refuse les certificats valables plus de 825 jours
            .not_valid_after(now + datetime.timedelta(days=800))
            .add_extension(x509.SubjectAlternativeName(sans), critical=False)
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(key, hashes.SHA256())
        )
        KEY_FILE.write_bytes(key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        ))
        CERT_FILE.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        return True
    except BaseException:
        # BaseException : PanicException (pyo3) n'hérite pas toujours d'Exception
        return False


def ssl_context():
    """Contexte SSL pour aiohttp, ou None si le certificat est indisponible."""
    if not (CERT_FILE.exists() and KEY_FILE.exists()):
        return None
    try:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(str(CERT_FILE), str(KEY_FILE))
        return ctx
    except Exception:
        return None


def cert_bytes():
    """Certificat public (.pem) à télécharger/installer sur le téléphone."""
    try:
        return CERT_FILE.read_bytes()
    except Exception:
        return None

"""
Apple App Attest verification (attestation + assertion).

Account-less abuse protection for /scan: the iOS app proves it is a genuine,
unmodified build running on real Apple hardware. No third-party dependency
beyond `cbor2` + `cryptography`; the verification steps follow Apple's
documented procedure:
https://developer.apple.com/documentation/devicecheck/validating-apps-that-connect-to-your-server

Attestation (one-time key registration):
  1. CBOR-decode; require fmt == "apple-appattest".
  2. Verify the x5c certificate chain up to Apple's App Attestation Root CA.
  3. nonce = SHA256(authData || SHA256(challenge)) must appear in the leaf
     certificate's extension OID 1.2.840.113635.100.8.2.
  4. key identifier == SHA256(leaf public key, uncompressed X9.62 point).
  5. authData RP ID hash == SHA256(app_id), counter == 0, AAGUID is the
     App Attest production (or, if opted in, development) environment,
     credentialId == key identifier.

Assertion (per-request proof):
  1. CBOR-decode {signature, authenticatorData}.
  2. Verify ECDSA-P256/SHA256 signature over
     authenticatorData || SHA256(clientData) with the registered public key.
  3. authenticatorData RP ID hash == SHA256(app_id); counter must strictly
     increase (replay protection).

Test hook: `_root_ca_pem_override` swaps the trust anchor so the full path
is exercised with a synthetic CA. Real-device verification is a launch gate.
"""

import hashlib
import logging
from dataclasses import dataclass
from typing import Optional

import cbor2
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

logger = logging.getLogger(__name__)

# Fetched 2026-07-05 from
# https://www.apple.com/certificateauthority/Apple_App_Attestation_Root_CA.pem
APPLE_APP_ATTEST_ROOT_CA_PEM = """-----BEGIN CERTIFICATE-----
MIICITCCAaegAwIBAgIQC/O+DvHN0uD7jG5yH2IXmDAKBggqhkjOPQQDAzBSMSYw
JAYDVQQDDB1BcHBsZSBBcHAgQXR0ZXN0YXRpb24gUm9vdCBDQTETMBEGA1UECgwK
QXBwbGUgSW5jLjETMBEGA1UECAwKQ2FsaWZvcm5pYTAeFw0yMDAzMTgxODMyNTNa
Fw00NTAzMTUwMDAwMDBaMFIxJjAkBgNVBAMMHUFwcGxlIEFwcCBBdHRlc3RhdGlv
biBSb290IENBMRMwEQYDVQQKDApBcHBsZSBJbmMuMRMwEQYDVQQIDApDYWxpZm9y
bmlhMHYwEAYHKoZIzj0CAQYFK4EEACIDYgAERTHhmLW07ATaFQIEVwTtT4dyctdh
NbJhFs/Ii2FdCgAHGbpphY3+d8qjuDngIN3WVhQUBHAoMeQ/cLiP1sOUtgjqK9au
Yen1mMEvRq9Sk3Jm5X8U62H+xTD3FE9TgS41o0IwQDAPBgNVHRMBAf8EBTADAQH/
MB0GA1UdDgQWBBSskRBTM72+aEH/pwyp5frq5eWKoTAOBgNVHQ8BAf8EBAMCAQYw
CgYIKoZIzj0EAwMDaAAwZQIwQgFGnByvsiVbpTKwSga0kP0e8EeDS4+sQmTvb7vn
53O5+FRXgeLhpJ06ysC5PrOyAjEAp5U4xDgEgllF7En3VcE3iexZZtKeYnpqtijV
oyFraWVIyd/dganmrduC1bmTBGwD
-----END CERTIFICATE-----
"""

APP_ATTEST_NONCE_OID = x509.ObjectIdentifier("1.2.840.113635.100.8.2")
AAGUID_PRODUCTION = b"appattest" + b"\x00" * 7
AAGUID_DEVELOPMENT = b"appattestdevelop"

# Test hook: replaces the Apple root as trust anchor when set.
_root_ca_pem_override: Optional[str] = None


class AttestationError(Exception):
    """Attestation or assertion failed verification."""


@dataclass
class AttestedKey:
    public_key_pem: str
    counter: int


def _trust_anchor() -> x509.Certificate:
    pem = _root_ca_pem_override or APPLE_APP_ATTEST_ROOT_CA_PEM
    return x509.load_pem_x509_certificate(pem.encode())


def _verify_chain(leaf: x509.Certificate, intermediates: list[x509.Certificate]) -> None:
    """Verify leaf ← intermediates ← trust anchor by signature and validity."""
    root = _trust_anchor()
    chain = [leaf, *intermediates, root]
    for child, issuer in zip(chain, chain[1:]):
        if child.issuer != issuer.subject:
            raise AttestationError("certificate chain broken: issuer mismatch")
        try:
            issuer.public_key().verify(
                child.signature, child.tbs_certificate_bytes,
                ec.ECDSA(child.signature_hash_algorithm),
            )
        except InvalidSignature:
            raise AttestationError("certificate chain broken: bad signature")


def _parse_auth_data(auth_data: bytes):
    """Returns (rp_id_hash, counter, aaguid, credential_id)."""
    if len(auth_data) < 55:
        raise AttestationError("authData too short")
    rp_id_hash = auth_data[:32]
    counter = int.from_bytes(auth_data[33:37], "big")
    aaguid = auth_data[37:53]
    cred_len = int.from_bytes(auth_data[53:55], "big")
    credential_id = auth_data[55:55 + cred_len]
    if len(credential_id) != cred_len:
        raise AttestationError("authData truncated credentialId")
    return rp_id_hash, counter, aaguid, credential_id


def verify_attestation(
    attestation: bytes,
    key_id: bytes,
    challenge: bytes,
    *,
    app_id: str,
    allow_development: bool = False,
) -> AttestedKey:
    """Verify a one-time App Attest attestation; returns the device public key."""
    try:
        obj = cbor2.loads(attestation)
        fmt = obj["fmt"]
        x5c = obj["attStmt"]["x5c"]
        auth_data = obj["authData"]
    except Exception:
        raise AttestationError("malformed attestation object")

    if fmt != "apple-appattest":
        raise AttestationError(f"unexpected attestation fmt: {fmt!r}")
    if not x5c:
        raise AttestationError("empty certificate chain")

    try:
        certs = [x509.load_der_x509_certificate(der) for der in x5c]
    except Exception:
        raise AttestationError("undecodable certificate in chain")
    leaf, intermediates = certs[0], certs[1:]
    _verify_chain(leaf, intermediates)

    # Nonce binds the attestation to our challenge.
    client_data_hash = hashlib.sha256(challenge).digest()
    nonce = hashlib.sha256(auth_data + client_data_hash).digest()
    try:
        ext = leaf.extensions.get_extension_for_oid(APP_ATTEST_NONCE_OID)
        ext_der = ext.value.public_bytes() if hasattr(ext.value, "public_bytes") else bytes(ext.value.value)
    except x509.ExtensionNotFound:
        raise AttestationError("nonce extension missing from leaf certificate")
    if nonce not in ext_der:
        raise AttestationError("nonce mismatch (challenge not bound)")

    # Key identifier is the SHA256 of the attested public key.
    public_key = leaf.public_key()
    if not isinstance(public_key, ec.EllipticCurvePublicKey):
        raise AttestationError("attested key is not an EC key")
    point = public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    if hashlib.sha256(point).digest() != key_id:
        raise AttestationError("key identifier mismatch")

    rp_id_hash, counter, aaguid, credential_id = _parse_auth_data(auth_data)
    if rp_id_hash != hashlib.sha256(app_id.encode()).digest():
        raise AttestationError("app ID mismatch")
    if counter != 0:
        raise AttestationError("attestation counter must be 0")
    if aaguid == AAGUID_DEVELOPMENT:
        if not allow_development:
            raise AttestationError("development environment attestation rejected")
    elif aaguid != AAGUID_PRODUCTION:
        raise AttestationError("unknown App Attest environment")
    if credential_id != key_id:
        raise AttestationError("credentialId does not match key identifier")

    pem = public_key.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    return AttestedKey(public_key_pem=pem, counter=counter)


def verify_assertion(
    assertion: bytes,
    client_data: bytes,
    public_key_pem: str,
    *,
    app_id: str,
    last_counter: int,
) -> int:
    """Verify a per-request App Attest assertion; returns the new counter."""
    try:
        obj = cbor2.loads(assertion)
        signature = obj["signature"]
        auth_data = obj["authenticatorData"]
    except Exception:
        raise AttestationError("malformed assertion object")

    if len(auth_data) < 37:
        raise AttestationError("authenticatorData too short")
    rp_id_hash = auth_data[:32]
    counter = int.from_bytes(auth_data[33:37], "big")

    if rp_id_hash != hashlib.sha256(app_id.encode()).digest():
        raise AttestationError("app ID mismatch")

    public_key = serialization.load_pem_public_key(public_key_pem.encode())
    message = auth_data + hashlib.sha256(client_data).digest()
    try:
        public_key.verify(signature, message, ec.ECDSA(hashes.SHA256()))
    except InvalidSignature:
        raise AttestationError("bad assertion signature")

    if counter <= last_counter:
        raise AttestationError(
            f"assertion counter did not increase ({counter} <= {last_counter})"
        )
    return counter

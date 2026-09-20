"""Exercise the upgraded libraries beyond mocked adapter boundaries."""

from __future__ import annotations

import hashlib
import io
import json

import cbor2
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from pypdf import PdfReader
from reportlab.pdfgen.canvas import Canvas
from webauthn import verify_authentication_response
from webauthn.helpers import bytes_to_base64url
from webauthn.helpers.exceptions import InvalidAuthenticationResponse
from yt_dlp import YoutubeDL


def test_pdf_generated_document_text_and_page_count():
    stream = io.BytesIO()
    canvas = Canvas(stream)
    canvas.drawString(40, 750, "Antiek dependency compatibility")
    canvas.showPage()
    canvas.save()
    stream.seek(0)
    reader = PdfReader(stream)
    assert len(reader.pages) == 1
    assert "Antiek dependency compatibility" in reader.pages[0].extract_text()


def test_webauthn_verifies_real_ecdsa_assertion_and_rejects_tampering():
    key = ec.generate_private_key(ec.SECP256R1())
    public = key.public_key().public_numbers()
    cose = cbor2.dumps({
        1: 2, 3: -7, -1: 1,
        -2: public.x.to_bytes(32, "big"), -3: public.y.to_bytes(32, "big"),
    })
    challenge = b"offline-library-compatibility-challenge"
    credential_id = b"offline-test-credential"
    client = json.dumps({
        "type": "webauthn.get", "challenge": bytes_to_base64url(challenge),
        "origin": "https://example.test", "crossOrigin": False,
    }).encode()
    authenticator = hashlib.sha256(b"example.test").digest() + b"\x05" + (1).to_bytes(4, "big")
    signature = key.sign(authenticator + hashlib.sha256(client).digest(), ec.ECDSA(hashes.SHA256()))
    credential = {
        "id": bytes_to_base64url(credential_id),
        "rawId": bytes_to_base64url(credential_id),
        "type": "public-key",
        "response": {
            "clientDataJSON": bytes_to_base64url(client),
            "authenticatorData": bytes_to_base64url(authenticator),
            "signature": bytes_to_base64url(signature),
        },
    }
    kwargs = dict(
        credential=credential, expected_challenge=challenge,
        expected_rp_id="example.test", expected_origin="https://example.test",
        credential_public_key=cose, credential_current_sign_count=0,
        require_user_verification=True,
    )
    verified = verify_authentication_response(**kwargs)
    assert verified.credential_id == credential_id
    assert verified.new_sign_count == 1
    assert verified.user_verified is True
    credential["response"]["signature"] = bytes_to_base64url(
        signature[:-1] + bytes([signature[-1] ^ 1])
    )
    with pytest.raises(InvalidAuthenticationResponse):
        verify_authentication_response(**kwargs)


def test_ytdlp_processes_metadata_without_fetching_media():
    with YoutubeDL({"quiet": True, "skip_download": True, "noplaylist": True}) as downloader:
        result = downloader.process_ie_result({
            "id": "offline-video", "title": "Offline compatibility",
            "url": "https://example.invalid/video.mp4", "ext": "mp4",
            "extractor": "generic", "webpage_url": "https://example.invalid/video",
        }, download=False)
    assert result["id"] == "offline-video"
    assert result["title"] == "Offline compatibility"
    assert result["ext"] == "mp4"

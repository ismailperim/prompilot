import ssl
from pathlib import Path

import certifi

from app.prometheus.client import tls_context


def test_tls_context_modes(tmp_path: Path) -> None:
    assert tls_context(False, None) is False
    assert tls_context(True, None) is True
    # a custom CA is loaded on top of the bundled store
    ca = tmp_path / "ca.pem"
    ca.write_text(Path(certifi.where()).read_text())
    context = tls_context(True, ca)
    assert isinstance(context, ssl.SSLContext) and context.verify_mode == ssl.CERT_REQUIRED

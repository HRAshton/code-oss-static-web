#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import copy
import json
import shutil
import ssl
from pathlib import Path
from typing import Any, cast


def export_provenance(bundle_dir: Path, artifacts_dir: Path) -> None:
    bundle_files = [path for path in bundle_dir.iterdir() if path.is_file()]
    if len(bundle_files) != 1:
        raise SystemExit(f'expected exactly one provenance bundle, found {len(bundle_files)}')

    bundle_path = bundle_files[0]
    bundle = cast(dict[str, Any], json.loads(bundle_path.read_text(encoding='utf-8')))
    media_type = bundle.get('mediaType', '')
    if not media_type.startswith('application/vnd.dev.sigstore.bundle.'):
        raise SystemExit(f'unexpected Sigstore bundle media type: {media_type!r}')

    envelope_value = bundle.get('dsseEnvelope')
    if not isinstance(envelope_value, dict):
        raise SystemExit('provenance bundle is missing a DSSE envelope')
    envelope = cast(dict[str, Any], envelope_value)
    if envelope.get('payloadType') != 'application/vnd.in-toto+json':
        raise SystemExit('provenance bundle has an unexpected DSSE payload type')

    signatures_value: Any = envelope.get('signatures')
    if not isinstance(signatures_value, list):
        raise SystemExit('provenance bundle must contain a DSSE signature list')
    signatures = cast(list[object], signatures_value)
    if len(signatures) != 1:
        raise SystemExit('provenance bundle must contain exactly one DSSE signature')
    signature = signatures[0]
    if not isinstance(signature, dict):
        raise SystemExit('provenance bundle contains an invalid DSSE signature')

    payload = envelope.get('payload')
    if not isinstance(payload, str):
        raise SystemExit('provenance bundle has an invalid DSSE payload')
    try:
        statement = cast(dict[str, Any], json.loads(base64.b64decode(payload, validate=True)))
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f'invalid in-toto statement payload: {exc}') from exc

    if statement.get('_type') != 'https://in-toto.io/Statement/v1':
        raise SystemExit('provenance payload is not an in-toto Statement v1')
    if statement.get('predicateType') != 'https://slsa.dev/provenance/v1':
        raise SystemExit('provenance payload is not SLSA provenance v1')

    expected: dict[str, str] = {}
    checksums = artifacts_dir / 'SHA256SUMS'
    for line in checksums.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        digest, name = line.split(None, 1)
        expected[name.strip().lstrip('*')] = digest

    subjects_value: Any = statement.get('subject')
    if not isinstance(subjects_value, list):
        raise SystemExit('provenance payload is missing subjects')
    subjects = cast(list[object], subjects_value)
    actual: dict[str, str] = {}
    for subject_value in subjects:
        if not isinstance(subject_value, dict):
            raise SystemExit('invalid provenance subject')
        subject = cast(dict[str, Any], subject_value)
        name = subject.get('name')
        digest_value = subject.get('digest')
        if not isinstance(name, str) or not isinstance(digest_value, dict):
            raise SystemExit('invalid provenance subject')
        digest = cast(dict[str, Any], digest_value)
        sha256 = digest.get('sha256')
        if not isinstance(sha256, str):
            raise SystemExit(f'provenance subject has no SHA-256 digest: {name}')
        actual[name] = sha256

    if actual != expected:
        raise SystemExit('provenance subjects do not exactly match SHA256SUMS')

    verification_value = bundle.get('verificationMaterial')
    if not isinstance(verification_value, dict):
        raise SystemExit('provenance bundle is missing verification material')
    verification = cast(dict[str, Any], verification_value)
    certificate_value = verification.get('certificate')
    if not isinstance(certificate_value, dict):
        raise SystemExit('provenance bundle is missing its signing certificate')
    certificate = cast(dict[str, Any], certificate_value)
    raw_certificate = certificate.get('rawBytes')
    if not isinstance(raw_certificate, str):
        raise SystemExit('provenance bundle has an invalid signing certificate')

    try:
        pem_certificate = ssl.DER_cert_to_PEM_cert(base64.b64decode(raw_certificate, validate=True))
    except (ValueError, ssl.SSLError) as exc:
        raise SystemExit(f'invalid signing certificate: {exc}') from exc

    shutil.copyfile(bundle_path, artifacts_dir / 'release-provenance.sigstore.json')

    legacy_envelope = copy.deepcopy(envelope)
    legacy_signatures = cast(list[dict[str, Any]], legacy_envelope['signatures'])
    legacy_signatures[0]['cert'] = pem_certificate
    (artifacts_dir / 'release-provenance.intoto.jsonl').write_text(
        json.dumps(legacy_envelope, separators=(',', ':')) + '\n',
        encoding='utf-8',
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--bundle-dir', type=Path, required=True)
    parser.add_argument('--artifacts-dir', type=Path, required=True)
    args = parser.parse_args()
    export_provenance(args.bundle_dir, args.artifacts_dir)


if __name__ == '__main__':
    main()

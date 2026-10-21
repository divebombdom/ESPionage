#!/usr/bin/env python3
"""Build an ESP-IDF/arduino-esp32 format x509 certificate bundle from a PEM
file containing root CA certificates (e.g. the Mozilla store from curl.se).

Bundle format (matches esp_crt_bundle.c in arduino-esp32):
  [0..1]  uint16 BE  number of certificates
  then, sorted by name, per certificate:
    [0..1]  uint16 BE  name_len   (subject Name, DER)
    [2..3]  uint16 BE  key_len    (SubjectPublicKeyInfo, DER)
    [4..]              name bytes, then key bytes

Usage: build_crt_bundle.py <cacert.pem> <out.bin>
"""
import sys
from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


def main(pem_path, out_path):
    data = open(pem_path, "rb").read()
    certs = x509.load_pem_x509_certificates(data)

    entries = []
    for cert in certs:
        name = cert.subject.public_bytes()  # DER of the Name
        key = cert.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
        entries.append((name, key))

    # The loader binary-searches by name — entries must be sorted by name.
    entries.sort(key=lambda e: e[0])

    out = bytearray()
    out += len(entries).to_bytes(2, "big")
    for name, key in entries:
        out += len(name).to_bytes(2, "big")
        out += len(key).to_bytes(2, "big")
        out += name
        out += key

    with open(out_path, "wb") as f:
        f.write(out)
    print(f"bundle: {len(entries)} certs, {len(out)} bytes -> {out_path}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

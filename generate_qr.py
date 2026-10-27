import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: generate_qr.py <url> <output.png>", file=sys.stderr)
        return 2

    url, output_path = sys.argv[1], Path(sys.argv[2])
    try:
        import qrcode
    except ImportError:
        print(
            "Missing qrcode module. Install it with: python -m pip install -r requirements.txt",
            file=sys.stderr,
        )
        return 1

    try:
        qrcode.make(url).save(output_path)
    except Exception as error:
        print(f"Could not create QR image: {error}", file=sys.stderr)
        return 1

    print(f"QR code saved: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

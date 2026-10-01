"""Export the console contract without opening Storage or contacting a provider."""
import argparse
import json
from pathlib import Path

from ebd.service import create_app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path,
        default=Path(__file__).resolve().parents[1] / "docs/api/openapi.json",
    )
    args = parser.parse_args()
    schema = create_app().openapi()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )
    print(f"Exported {len(schema['paths'])} paths to {args.output}")


if __name__ == "__main__":
    main()

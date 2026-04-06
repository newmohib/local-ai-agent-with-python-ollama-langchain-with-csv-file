import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.vector_store import export_hf_to_csv


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export HuggingFace product rows to a local CSV file."
    )
    parser.add_argument("--output", default=None, help="CSV output path")
    parser.add_argument("--limit", type=int, default=None, help="Maximum rows to export")
    parser.add_argument("--keyword", default=None, help="Optional keyword filter")
    args = parser.parse_args()

    result = export_hf_to_csv(
        output_path=args.output,
        limit=args.limit,
        keyword=args.keyword,
    )
    print(result)


if __name__ == "__main__":
    main()

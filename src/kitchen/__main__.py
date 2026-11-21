"""Run the app: python -m kitchen"""

from __future__ import annotations

import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(description="TheKitchen brewing assistant")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db", default=os.environ.get("KITCHEN_DB", "kitchen.db"))
    args = parser.parse_args()

    os.environ["KITCHEN_DB"] = args.db
    import uvicorn

    uvicorn.run("kitchen.api:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()

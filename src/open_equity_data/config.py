import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


def get_db_path() -> Path:
    db_path = os.environ.get("STOCKS_DB")

    if not db_path:
        raise RuntimeError(
            "STOCKS_DB environment variable is not set."
        )

    path = Path(db_path).expanduser()

    if not path.exists():
        raise FileNotFoundError(
            f"DuckDB database not found: {path}"
        )

    return path

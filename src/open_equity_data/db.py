import duckdb

from open_equity_data.config import get_db_path


def connect(read_only: bool = False):
    return duckdb.connect(
        str(get_db_path()),
        read_only=read_only,
    )

from open_equity_data.sec import (
    normalize_cik,
)


def test_normalize_cik():
    assert (
        normalize_cik("320193")
        == "0000320193"
    )

    assert (
        normalize_cik("CIK320193")
        == "0000320193"
    )

    assert (
        normalize_cik(320193)
        == "0000320193"
    )

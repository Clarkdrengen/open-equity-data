from open_equity_data.research.benchmark_dataset import (
    FEATURES,
    HORIZONS,
    allocate_equal_year_quotas,
)


def test_horizons():
    assert HORIZONS == (
        1,
        5,
        10,
        20,
        60,
    )


def test_feature_count():
    assert len(FEATURES) == 21
    assert len(set(FEATURES)) == 21


def test_equal_year_allocation():
    counts = [
        (2020, 100),
        (2021, 100),
        (2022, 100),
    ]

    result = allocate_equal_year_quotas(
        counts,
        90,
    )

    assert result == {
        2020: 30,
        2021: 30,
        2022: 30,
    }


def test_allocation_respects_capacity():
    counts = [
        (2020, 5),
        (2021, 100),
        (2022, 100),
    ]

    result = allocate_equal_year_quotas(
        counts,
        90,
    )

    assert result[2020] == 5
    assert sum(result.values()) == 90
    assert result[2021] <= 100
    assert result[2022] <= 100

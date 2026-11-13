from datetime import date

import pytest

from app.services.metrics import comparison, parse_count, parse_dynamics
from app.services.query_catalog import CatalogError, QueryCatalog
from app.services.wordstat_client import WordStatResponseError


@pytest.mark.parametrize("current,previous,trend,percent", [
    (120, 100, "up", 20.0), (80, 100, "down", -20.0), (10, 10, "flat", 0.0),
    (10, 0, "up", None), (0, 0, "flat", 0.0), (None, 5, "no_data", None),
])
def test_comparison(current, previous, trend, percent):
    result = comparison(current, previous)
    assert result["trend"] == trend and result["delta_percent"] == percent


@pytest.mark.parametrize("value", [True, 1.5, "1e3", "-1", "١٢", -1, 9223372036854775808])
def test_bad_counts(value):
    with pytest.raises(ValueError):
        parse_count(value)


def test_missing_days_are_not_zero():
    assert parse_dynamics({"results": []}, date(2026, 11, 11), date(2026, 11, 12)) == {}


@pytest.mark.parametrize("rows", [
    [{"date": "2026-11-10T00:00:00Z", "count": "1"}],
    [{"date": "2026-11-11T03:00:00+03:00", "count": "1"}],
    [{"date": "2026-11-11T00:00:00Z", "count": "1"}] * 2,
])
def test_bad_dates(rows):
    with pytest.raises(WordStatResponseError):
        parse_dynamics({"results": rows}, date(2026, 11, 11), date(2026, 11, 12))


def test_unknown_query_without_category():
    with pytest.raises(CatalogError):
        QueryCatalog(1, (), ()).select(query_id="unknown")

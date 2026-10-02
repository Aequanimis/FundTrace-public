from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from api.credibility import GRADE_RANK, assess_result_credibility


def _frames(*, current=None, disclosed=None, r2=0.9, converged=True, weekly_rows=8):
    industries = list((current or {"Alpha": 0.4, "Beta": 0.4}).keys())
    current = current or {"Alpha": 0.4, "Beta": 0.4}
    dates = pd.date_range("2026-01-02", periods=weekly_rows, freq="W-FRI")
    weekly = pd.DataFrame([current] * weekly_rows, index=dates, dtype=float)
    diagnostics = pd.DataFrame(
        {"r2": [r2] * weekly_rows, "converged": [converged] * weekly_rows}, index=dates
    )
    simulated = None
    if disclosed is not None:
        simulated = pd.DataFrame([disclosed], index=[pd.Timestamp("2025-12-31")], dtype=float)
    return weekly, diagnostics, simulated


def _assess(*, current=None, disclosed=None, disclosed_ratio=None, r2=0.9, converged=True, weekly_rows=8):
    weekly, diagnostics, simulated = _frames(
        current=current, disclosed=disclosed, r2=r2, converged=converged, weekly_rows=weekly_rows
    )
    disclosure = (
        {"ratio": disclosed_ratio, "date": pd.Timestamp("2025-12-31"), "available": True}
        if disclosed_ratio is not None
        else {"ratio": None, "date": None, "available": False}
    )
    return assess_result_credibility(
        weekly,
        diagnostics,
        disclosed_equity=disclosure,
        simulated=simulated,
        has_full_disclosure_structure=simulated is not None,
    )


def _assert_not_upgraded(result):
    assert GRADE_RANK[result["grade"]] <= GRADE_RANK[result["base_grade"]]


def test_base_a_with_all_sanity_normal_is_a():
    result = _assess(
        current={"Alpha": 0.4, "Beta": 0.4},
        disclosed={"Alpha": 0.4, "Beta": 0.4},
        disclosed_ratio=0.8,
    )
    assert result["base_grade"] == result["grade"] == "A"
    _assert_not_upgraded(result)


def test_base_a_with_moderate_structure_distance_is_capped_to_b():
    result = _assess(
        current={"Alpha": 0.55, "Beta": 0.25},
        disclosed={"Alpha": 0.20, "Beta": 0.60},
        disclosed_ratio=0.8,
    )
    assert result["base_grade"] == "A"
    assert result["grade"] == "B"
    assert "STRUCTURE_DISTANCE_HIGH" in result["sanity"]["warning_codes"]
    _assert_not_upgraded(result)


def test_base_a_with_severe_sum_gap_is_capped_to_c():
    result = _assess(current={"Alpha": 0.2}, disclosed_ratio=0.9)
    assert result["base_grade"] == "A"
    assert result["grade"] == "C"
    assert "SEVERE_EXPOSURE_GAP" in result["sanity"]["warning_codes"]
    _assert_not_upgraded(result)


@pytest.mark.parametrize(("r2", "expected"), [(0.70, "B"), (0.45, "C")])
def test_base_grade_is_retained_when_sanity_is_normal(r2, expected):
    result = _assess(
        current={"Alpha": 0.4, "Beta": 0.4},
        disclosed={"Alpha": 0.4, "Beta": 0.4},
        disclosed_ratio=0.8,
        r2=r2,
    )
    assert result["base_grade"] == result["grade"] == expected
    _assert_not_upgraded(result)


def test_non_converged_result_is_d():
    result = _assess(
        current={"Alpha": 0.4, "Beta": 0.4},
        disclosed={"Alpha": 0.4, "Beta": 0.4},
        disclosed_ratio=0.8,
        converged=False,
    )
    assert result["grade"] == "D"
    assert "MODEL_NOT_CONVERGED" in result["reason_codes"]


def test_two_severe_anomalies_with_poor_fit_is_d():
    result = _assess(
        current={"Alpha": 0.2, "Beta": 0.0, "Gamma": 0.0, "Delta": 0.0, "Epsilon": 0.0},
        disclosed={"Alpha": 0.2, "Beta": 0.15, "Gamma": 0.15, "Delta": 0.15, "Epsilon": 0.15},
        disclosed_ratio=0.95,
        r2=0.5,
    )
    assert result["grade"] == "D"
    assert "SEVERE_EXPOSURE_GAP" in result["sanity"]["warning_codes"]
    assert "MULTIPLE_MAJOR_INDUSTRIES_COLLAPSED" in result["sanity"]["warning_codes"]
    assert "MULTIPLE_SEVERE_ANOMALIES_WITH_POOR_FIT" in result["reason_codes"]
    _assert_not_upgraded(result)


def test_missing_disclosure_noise_and_contract_do_not_crash(monkeypatch):
    weekly, diagnostics, _ = _frames()

    def unavailable_noise(*args, **kwargs):
        raise RuntimeError("noise unavailable")

    monkeypatch.setattr("api.credibility.detect_shifts", unavailable_noise)
    result = assess_result_credibility(
        weekly,
        diagnostics,
        disclosed_equity={"ratio": None, "date": None, "available": False},
        simulated=None,
        metadata_path=None,
        has_full_disclosure_structure=False,
    )
    assert result["sanity"]["disclosed_equity_ratio"] is None
    assert result["sanity"]["noise_signal_status"] == "NOT_AVAILABLE_FOR_STRUCTURED_RATING"
    assert result["sanity"]["contract_equity_min"] is None
    _assert_not_upgraded(result)


def test_nan_inputs_have_safe_fallback():
    weekly, diagnostics, _ = _frames(r2=np.nan)
    weekly.iloc[-1, 0] = np.nan
    result = assess_result_credibility(
        weekly,
        diagnostics,
        disclosed_equity={"ratio": np.nan, "date": None, "available": False},
        simulated=None,
        has_full_disclosure_structure=False,
    )
    assert result["grade"] == "D"
    assert result["sanity"]["sum_gap_pp"] is None
    _assert_not_upgraded(result)

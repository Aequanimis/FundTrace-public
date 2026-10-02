"""Read-only V1.4 result-credibility policy over existing FundTrace artifacts.

This module deliberately does not alter model inputs, weekly positions, diagnostics,
or disclosure files.  It only explains how much confidence users should place in an
already-produced implied industry exposure result.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from lib.regress import detect_shifts


GRADE_RANK = {"A": 4, "B": 3, "C": 2, "D": 1}
CREDIBILITY_LABELS = {
    "A": "高可信",
    "B": "可参考",
    "C": "谨慎参考",
    "D": "暂不建议解读",
}
CREDIBILITY_DESCRIPTIONS = {
    "A": "模型拟合和结果稳定性均较好，可结合行业权重与变化方向进行观察。",
    "B": "模型整体可用，但部分行业绝对权重存在不确定性，建议更关注变化方向。",
    "C": "结果存在明显偏离或稳定性问题，建议仅弱参考变化方向，不要将绝对比例理解为真实持仓。",
    "D": "当前模型或数据状态不足以支持可靠判断。",
}
MODEL_QUALITY_LABELS = {
    "A": "优秀",
    "B": "可用",
    "C": "偏弱",
    "D": "不足",
}


def _finite(value: Any, default: float | None = None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _boolean(value: Any) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _grade(value: Any) -> str | None:
    candidate = str(value or "").strip().upper()
    return candidate if candidate in GRADE_RANK else None


def _cap_grade(grade: str, cap: str | None) -> str:
    if cap is None:
        return grade
    return cap if GRADE_RANK[cap] < GRADE_RANK[grade] else grade


def _safe_numeric_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0.0)


def _latest_row(frame: pd.DataFrame, latest_date: pd.Timestamp) -> pd.Series:
    eligible = frame.index[frame.index <= latest_date]
    return frame.loc[eligible[-1]] if len(eligible) else frame.iloc[-1]


def _date_string(value: pd.Timestamp | None) -> str | None:
    return value.strftime("%Y-%m-%d") if value is not None else None


def _normalise_percent_series(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values.astype(str).str.replace("%", "", regex=False), errors="coerce")
    numeric = numeric.replace([np.inf, -np.inf], np.nan).dropna()
    if numeric.empty:
        return numeric
    return numeric / 100.0 if float(numeric.abs().max()) > 1.0 else numeric


def read_disclosed_equity_ratio(path: Path | None) -> dict[str, Any]:
    """Read the latest full public industry-allocation total, if it is available.

    The public `industry_alloc.csv` percentages are the only source used for the
    total disclosed equity ratio.  The simulated SW matrix is intentionally not
    used for that total, so a Top10 sum can never masquerade as a full disclosure.
    """

    empty = {"ratio": None, "date": None, "available": False}
    if path is None or not path.is_file():
        return empty
    try:
        frame = pd.read_csv(path)
    except (OSError, pd.errors.ParserError, UnicodeDecodeError):
        return empty
    if frame.empty or len(frame.columns) < 3:
        return empty

    pct_column = next(
        (column for column in ("占净值比例", "pct", "weight", "占比") if column in frame.columns),
        frame.columns[2],
    )
    date_column = next(
        (column for column in ("截止时间", "period", "date", "日期") if column in frame.columns),
        frame.columns[4] if len(frame.columns) >= 5 else None,
    )
    if date_column is None:
        return empty

    dates = pd.to_datetime(frame[date_column], errors="coerce")
    values = _normalise_percent_series(frame[pct_column])
    valid = pd.DataFrame({"date": dates, "value": values}).dropna(subset=["date", "value"])
    if valid.empty:
        return empty
    disclosure_date = valid["date"].max()
    ratio = _finite(valid.loc[valid["date"] == disclosure_date, "value"].sum())
    if ratio is None or ratio <= 0:
        return empty
    return {"ratio": ratio, "date": pd.Timestamp(disclosure_date), "available": True}


def _read_contract_range(path: Path | None) -> tuple[float | None, float | None]:
    if path is None or not path.is_file():
        return None, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None, None
    if not isinstance(data, dict):
        return None, None
    lower = _finite(data.get("equity_min"))
    upper = _finite(data.get("equity_max"))
    if lower is not None and lower > 1:
        lower /= 100.0
    if upper is not None and upper > 1:
        upper /= 100.0
    return lower, upper


def _model_quality(r2: float | None, converged: bool, legacy_grade: str | None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Grade only existing current-window diagnostics; never rerun a model."""

    reasons: list[dict[str, Any]] = []
    if not converged:
        grade = "D"
        reasons.append({"code": "MODEL_NOT_CONVERGED", "message": "最新窗口未收敛，无法形成稳定结果。"})
    elif r2 is None:
        grade = "D"
        reasons.append({"code": "MODEL_R2_UNAVAILABLE", "message": "最新窗口缺少可用 R²，无法评估模型基础质量。"})
    elif r2 >= 0.80:
        grade = "A"
        reasons.append({"code": "MODEL_R2_HIGH", "message": f"最新窗口 R² 为 {r2:.3f}，模型拟合达到较高标准。"})
    elif r2 >= 0.60:
        grade = "B"
        reasons.append({"code": "MODEL_R2_MODERATE", "message": f"最新窗口 R² 为 {r2:.3f}，模型整体可用但存在不确定性。"})
    elif r2 >= 0.35:
        grade = "C"
        reasons.append({"code": "MODEL_R2_WEAK", "message": f"最新窗口 R² 为 {r2:.3f}，模型拟合偏弱。"})
    else:
        grade = "D"
        reasons.append({"code": "MODEL_R2_LOW", "message": f"最新窗口 R² 为 {r2:.3f}，不足以支持可靠解读。"})

    legacy = _grade(legacy_grade)
    if legacy is not None and GRADE_RANK[legacy] < GRADE_RANK[grade]:
        grade = legacy
        reasons.append({
            "code": "LEGACY_MODEL_GRADE_CAP",
            "message": f"既有模型报告评级为 {legacy}，基础模型质量不高于该历史模型判断。",
        })

    return {
        "grade": grade,
        "label": MODEL_QUALITY_LABELS[grade],
        "r2": r2,
        "converged": converged,
        "legacy_grade": legacy,
        "reason_codes": [reason["code"] for reason in reasons],
    }, reasons


def _noise_status(weekly: pd.DataFrame) -> tuple[str, dict[str, Any] | None]:
    """Reuse the existing `detect_shifts` 1.5σ rule without inventing noise logic."""

    try:
        shifts = detect_shifts(weekly, top_n=5, lookback=4, noise_window=52)
    except Exception:
        return "NOT_AVAILABLE_FOR_STRUCTURED_RATING", None
    if shifts.empty:
        return "NOT_AVAILABLE_FOR_STRUCTURED_RATING", None

    # Columns are intentionally selected by position: `detect_shifts` owns its
    # Chinese display labels, while this presentation policy only reuses values.
    shifts = shifts.loc[~shifts.iloc[:, 0].duplicated()].copy()
    changes = pd.to_numeric(shifts.iloc[:, 1], errors="coerce").fillna(0.0)
    bands = pd.to_numeric(shifts.iloc[:, 4], errors="coerce")
    material = changes.abs() > 1e-9
    if not bool(material.any()):
        return "NO_RECENT_MATERIAL_CHANGE", {"major_change_count": 0, "signal_count": 0}
    signals = material & bands.notna() & (changes.abs() > bands)
    return (
        "SIGNAL" if bool(signals.any()) else "WITHIN_NOISE",
        {"major_change_count": int(material.sum()), "signal_count": int(signals.sum())},
    )


def assess_result_credibility(
    weekly: pd.DataFrame,
    diagnostics: pd.DataFrame,
    *,
    legacy_grade: str | None = None,
    disclosed_equity: dict[str, Any] | None = None,
    simulated: pd.DataFrame | None = None,
    metadata_path: Path | None = None,
    has_full_disclosure_structure: bool = True,
) -> dict[str, Any]:
    """Return a V1.4 credibility explanation for existing local output files.

    `weekly` and `diagnostics` must already be read from disk.  This function is
    pure with respect to the analysis artifacts: it never writes them and only
    evaluates their latest available rows.
    """

    if weekly.empty or diagnostics.empty:
        raise ValueError("weekly and diagnostics outputs must be non-empty")
    weekly = _safe_numeric_frame(weekly)
    diagnostics = diagnostics.copy()
    latest_date = pd.Timestamp(weekly.index[-1])
    latest_diag = _latest_row(diagnostics, latest_date)
    r2 = _finite(latest_diag.get("r2"))
    converged = _boolean(latest_diag.get("converged", False))
    model_quality, model_reasons = _model_quality(r2, converged, legacy_grade)
    base_grade = model_quality["grade"]

    current = weekly.iloc[-1].astype(float)
    implicit_sum = _finite(current.sum(), 0.0) or 0.0
    disclosure = disclosed_equity or {"ratio": None, "date": None, "available": False}
    disclosed_ratio = _finite(disclosure.get("ratio"))
    allocation_date = disclosure.get("date")
    allocation_date = pd.Timestamp(allocation_date) if allocation_date is not None else None
    sum_gap_pp = abs(implicit_sum - disclosed_ratio) * 100.0 if disclosed_ratio is not None else None

    warnings: list[dict[str, Any]] = []

    def warn(code: str, message: str, cap: str | None = None, severity: str = "warning") -> None:
        warnings.append({"code": code, "message": message, "cap": cap, "severity": severity})

    if sum_gap_pp is None:
        warn("DISCLOSURE_ALLOCATION_UNAVAILABLE", "未找到完整行业配置，未对暴露合计差异作降级判断。")
    elif sum_gap_pp >= 50.0:
        warn("SEVERE_EXPOSURE_GAP", f"隐含暴露合计与完整行业配置相差 {sum_gap_pp:.1f}pp。", "C", "severe")
    elif sum_gap_pp >= 30.0:
        warn("EXPOSURE_GAP_HIGH", f"隐含暴露合计与完整行业配置相差 {sum_gap_pp:.1f}pp。", "C")
    elif sum_gap_pp >= 20.0:
        warn("EXPOSURE_GAP_MODERATE", f"隐含暴露合计与完整行业配置相差 {sum_gap_pp:.1f}pp。", "B")
    elif sum_gap_pp >= 10.0:
        warn("EXPOSURE_GAP_WARNING", f"隐含暴露合计与完整行业配置相差 {sum_gap_pp:.1f}pp。")

    reallocation_distance_pp: float | None = None
    largest_shift_industry: str | None = None
    largest_shift_pp: float | None = None
    near_zero_drop_count: int | None = None
    structure_date: pd.Timestamp | None = None
    if simulated is not None and not simulated.empty and has_full_disclosure_structure:
        simulated = _safe_numeric_frame(simulated)
        reference_date = allocation_date or latest_date
        eligible = simulated.index[simulated.index <= reference_date]
        if len(eligible):
            structure_date = pd.Timestamp(eligible[-1])
            disclosed = simulated.loc[structure_date]
            industries = current.index.union(disclosed.index)
            aligned_current = current.reindex(industries, fill_value=0.0).fillna(0.0)
            aligned_disclosed = disclosed.reindex(industries, fill_value=0.0).fillna(0.0)
            distance = (aligned_current - aligned_disclosed).abs()
            reallocation_distance_pp = float(0.5 * distance.sum() * 100.0)
            largest_shift_industry = str(distance.idxmax()) if len(distance) else None
            largest_shift_pp = float(distance.max() * 100.0) if len(distance) else None
            near_zero_drop_count = int(((aligned_disclosed >= 0.03) & (aligned_current <= 0.005)).sum())

    disclosure_date = allocation_date or structure_date
    days_since_disclosure = int((latest_date - disclosure_date).days) if disclosure_date is not None else None
    if reallocation_distance_pp is None:
        warn("STRUCTURE_COMPARISON_UNAVAILABLE", "缺少可对齐的完整披露行业结构，未对结构偏离作降级判断。")
    elif days_since_disclosure is not None and days_since_disclosure <= 60:
        if reallocation_distance_pp >= 55.0:
            warn("STRUCTURE_DISTANCE_SEVERE", f"披露后 {days_since_disclosure} 天内行业结构偏离 {reallocation_distance_pp:.1f}pp。", "C")
        elif reallocation_distance_pp >= 30.0:
            warn("STRUCTURE_DISTANCE_HIGH", f"披露后 {days_since_disclosure} 天内行业结构偏离 {reallocation_distance_pp:.1f}pp。", "B")
        elif reallocation_distance_pp >= 20.0:
            warn("STRUCTURE_DISTANCE_WARNING", f"披露后 {days_since_disclosure} 天内行业结构偏离 {reallocation_distance_pp:.1f}pp。")
    elif reallocation_distance_pp is not None:
        if reallocation_distance_pp >= 60.0:
            warn("STRUCTURE_DISTANCE_SEVERE", f"披露后 {days_since_disclosure} 天行业结构偏离 {reallocation_distance_pp:.1f}pp。", "C")
        elif reallocation_distance_pp >= 45.0:
            warn("STRUCTURE_DISTANCE_HIGH", f"披露后 {days_since_disclosure} 天行业结构偏离 {reallocation_distance_pp:.1f}pp。", "B")
        elif reallocation_distance_pp >= 30.0:
            warn("STRUCTURE_DISTANCE_WARNING", f"披露后 {days_since_disclosure} 天行业结构偏离 {reallocation_distance_pp:.1f}pp。")

    if largest_shift_pp is not None:
        if largest_shift_pp >= 35.0 and (sum_gap_pp or 0.0) >= 30.0:
            warn(
                "LARGEST_SHIFT_WITH_EXPOSURE_GAP",
                f"{largest_shift_industry} 单行业偏离 {largest_shift_pp:.1f}pp，且暴露合计差异较大。",
                "C",
                "severe",
            )
        elif largest_shift_pp >= 25.0:
            warn("LARGEST_INDUSTRY_SHIFT_HIGH", f"{largest_shift_industry} 单行业偏离 {largest_shift_pp:.1f}pp。", "B")
        elif largest_shift_pp >= 15.0:
            warn("LARGEST_INDUSTRY_SHIFT_WARNING", f"{largest_shift_industry} 单行业偏离 {largest_shift_pp:.1f}pp。")

    if near_zero_drop_count is not None:
        if near_zero_drop_count >= 4 and (sum_gap_pp or 0.0) >= 30.0:
            warn(
                "MULTIPLE_MAJOR_INDUSTRIES_COLLAPSED",
                f"有 {near_zero_drop_count} 个此前主要行业当前接近零暴露。",
                "C",
                "severe",
            )
        elif near_zero_drop_count >= 3:
            warn("MULTIPLE_MAJOR_INDUSTRIES_WARNING", f"有 {near_zero_drop_count} 个此前主要行业当前接近零暴露。")

    recent_exposure_change_4w_pp: float | None = None
    if len(weekly) >= 5:
        target = latest_date - pd.Timedelta(days=28)
        reference_index = weekly.index[weekly.index <= target]
        if len(reference_index):
            reference_sum = float(weekly.loc[reference_index[-1]].sum())
            recent_exposure_change_4w_pp = float((implicit_sum - reference_sum) * 100.0)
            if abs(recent_exposure_change_4w_pp) < 1e-9:
                recent_exposure_change_4w_pp = 0.0
            decline_pp = -recent_exposure_change_4w_pp
            if decline_pp >= 50.0 and implicit_sum < 0.50:
                warn("RECENT_EXPOSURE_COLLAPSE_SEVERE", f"近四周隐含暴露合计下降 {decline_pp:.1f}pp。", "C", "severe")
            elif decline_pp >= 30.0:
                warn("RECENT_EXPOSURE_COLLAPSE", f"近四周隐含暴露合计下降 {decline_pp:.1f}pp。", "B")

    noise_signal_status, noise_detail = _noise_status(weekly)
    if noise_signal_status == "WITHIN_NOISE":
        warn("RECENT_CHANGES_WITHIN_NOISE", "近期主要行业变化均未超过现有 1.5σ 噪声带。", "B")

    equity_min, equity_max = _read_contract_range(metadata_path)
    if equity_min is not None and implicit_sum < equity_min - 0.20:
        warn(
            "CONTRACT_RANGE_CONFLICT",
            "隐含收益暴露明显低于产品已保存的权益仓位下限；隐含收益暴露并非实际股票仓位。",
            "C",
        )

    final_grade = base_grade
    cap_codes: list[str] = []
    for item in warnings:
        previous = final_grade
        final_grade = _cap_grade(final_grade, item["cap"])
        if item["cap"] is not None and GRADE_RANK[final_grade] < GRADE_RANK[previous]:
            cap_codes.append(item["code"])

    severe_count = sum(1 for item in warnings if item["severity"] == "severe")
    if r2 is not None and r2 < 0.60 and severe_count >= 2:
        final_grade = _cap_grade(final_grade, "D")
        warning = {
            "code": "MULTIPLE_SEVERE_ANOMALIES_WITH_POOR_FIT",
            "message": "多个严重现实一致性异常同时出现，且最新窗口拟合偏弱。",
            "cap": "D",
            "severity": "severe",
        }
        warnings.append(warning)
        cap_codes.append(warning["code"])

    reason_items = [*model_reasons, *warnings]
    reason_codes = list(dict.fromkeys(item["code"] for item in reason_items))
    reasons = list(dict.fromkeys(item["message"] for item in reason_items))
    warning_codes = list(dict.fromkeys(item["code"] for item in warnings))
    return {
        "grade": final_grade,
        "label": CREDIBILITY_LABELS[final_grade],
        "description": CREDIBILITY_DESCRIPTIONS[final_grade],
        "base_grade": base_grade,
        "reason_codes": reason_codes,
        "reasons": reasons,
        "grade_cap_reason": "; ".join(cap_codes) if cap_codes else "BASE_QUALITY_ONLY",
        "model_quality": model_quality,
        "sanity": {
            "implicit_exposure_sum": implicit_sum,
            "disclosed_equity_ratio": disclosed_ratio,
            "sum_gap_pp": sum_gap_pp,
            "reallocation_distance_pp": reallocation_distance_pp,
            "largest_shift_industry": largest_shift_industry,
            "largest_shift_pp": largest_shift_pp,
            "near_zero_drop_count": near_zero_drop_count,
            "recent_exposure_change_4w_pp": recent_exposure_change_4w_pp,
            "days_since_disclosure": days_since_disclosure,
            "noise_signal_status": noise_signal_status,
            "noise_detail": noise_detail,
            "disclosure_allocation_available": bool(disclosure.get("available")),
            "structure_comparison_available": reallocation_distance_pp is not None,
            "contract_equity_min": equity_min,
            "contract_equity_max": equity_max,
            "warning_codes": warning_codes,
        },
    }

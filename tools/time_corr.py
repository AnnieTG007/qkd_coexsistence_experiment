import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

def read_time_series_from_excel(
    excel_path: str,
    sheet_name=0,
    time_col=None,
    value_cols=None,
):
    """
    读取 Excel 并自动识别时间列/数值列。
    兼容“无表头、第一行就是数据”的文件（你附件就是这种）。
    """
    # 先按“无表头”读取，避免把第一行当作列名
    df = pd.read_excel(excel_path, sheet_name=sheet_name, header=None)

    # 去掉全空行
    df = df.dropna(how="all").reset_index(drop=True)

    # 自动识别时间列：优先尝试每一列能否大比例解析为 datetime
    if time_col is None:
        best_col = None
        best_parse_ratio = 0.0
        for c in df.columns:
            parsed = pd.to_datetime(df[c], errors="coerce")
            ratio = parsed.notna().mean()
            if ratio > best_parse_ratio:
                best_parse_ratio = ratio
                best_col = c
        if best_col is None or best_parse_ratio < 0.6:
            raise ValueError(
                "未能可靠识别时间列。请显式指定 time_col（列索引或列名）。"
            )
        time_col = best_col

    # 解析时间列
    ts = pd.to_datetime(df[time_col], errors="coerce")
    if ts.notna().mean() < 0.6:
        raise ValueError("时间列解析失败率过高，请检查时间格式或手动指定 time_col。")

    # 自动识别数值列：除时间列外，能转成数值的列
    numeric_candidates = []
    for c in df.columns:
        if c == time_col:
            continue
        s = pd.to_numeric(df[c], errors="coerce")
        if s.notna().mean() >= 0.6:
            numeric_candidates.append(c)

    if not numeric_candidates:
        raise ValueError("未找到可靠的数值列。请检查数据或手动指定 value_cols。")

    if value_cols is None:
        value_cols = numeric_candidates
    else:
        # 允许用户指定子集
        value_cols = list(value_cols)

    out = pd.DataFrame({"time": ts})
    for c in value_cols:
        out[f"value_{c}"] = pd.to_numeric(df[c], errors="coerce")

    # 清理、排序
    out = out.dropna(subset=["time"]).sort_values("time")
    out = out.drop_duplicates(subset=["time"], keep="last").reset_index(drop=True)
    out = out.set_index("time")

    return out


def summarize_sampling(index: pd.DatetimeIndex):
    """给出采样间隔的基本统计，帮助判断是否需要重采样。"""
    if len(index) < 3:
        return None
    deltas = index.to_series().diff().dropna().dt.total_seconds().values
    return {
        "n": len(index),
        "delta_seconds_median": float(np.median(deltas)),
        "delta_seconds_mean": float(np.mean(deltas)),
        "delta_seconds_min": float(np.min(deltas)),
        "delta_seconds_max": float(np.max(deltas)),
        "irregularity_ratio_max_over_median": float(np.max(deltas) / np.median(deltas)) if np.median(deltas) > 0 else np.nan,
    }


def maybe_resample(series: pd.Series, target_freq: str = None):
    """
    如果数据采样不均匀，建议重采样到固定频率后再做自相关检验。
    - target_freq=None：根据中位采样间隔自动估计一个秒级频率，例如 '11S'
    """
    info = summarize_sampling(series.index)
    if info is None:
        return series, {"resampled": False, "reason": "too_short"}

    # 自动估计频率
    if target_freq is None:
        sec = max(1, int(round(info["delta_seconds_median"])))
        target_freq = f"{sec}S"

    # 重采样 + 线性插值（也可改成 forward-fill/不插值）
    s = series.sort_index()
    s_rs = s.resample(target_freq).mean()
    s_rs = s_rs.interpolate(method="time")

    return s_rs, {"resampled": True, "target_freq": target_freq, "sampling_info": info}


def autocorr_report(series: pd.Series, max_lag: int = 20):
    """
    用多种方法检测时间相关性（自相关）：
    - ACF（自相关系数）
    - Ljung-Box 检验：原假设“到某些滞后为止均无自相关”
    - Durbin-Watson：主要针对一阶自相关的粗判据（接近2表示无明显一阶自相关）
    - ADF / KPSS：平稳性检验（不等同于“有无自相关”，但对解释很有帮助）
    """
    series = series.dropna()
    if len(series) < max_lag + 5:
        raise ValueError(f"样本点太少（{len(series)}），不够做 max_lag={max_lag} 的检验。")

    # 依赖 statsmodels；若环境没有，给出友好提示
    try:
        from statsmodels.stats.diagnostic import acorr_ljungbox
        from statsmodels.stats.stattools import durbin_watson
        from statsmodels.tsa.stattools import adfuller, kpss
        from statsmodels.tsa.stattools import acf
    except Exception as e:
        raise RuntimeError(
            "缺少 statsmodels 依赖。请先安装：pip install statsmodels\n"
            f"原始错误：{e}"
        )

    # ACF
    acf_vals = acf(series.values, nlags=max_lag, fft=True)

    # Ljung-Box：返回每个 lag 的统计量与 p 值
    lb = acorr_ljungbox(series.values, lags=list(range(1, max_lag + 1)), return_df=True)

    # Durbin-Watson（对“增量”更常用：这里对原序列给一个参考）
    dw = float(durbin_watson(series.values))

    # ADF（原假设：有单位根=非平稳）
    adf_stat, adf_p, *_ = adfuller(series.values, autolag="AIC")

    # KPSS（原假设：平稳；与 ADF 互补）
    # 注意：kpss 在某些情况下会报错（如常数序列），做保护
    try:
        kpss_stat, kpss_p, *_ = kpss(series.values, regression="c", nlags="auto")
        kpss_out = (float(kpss_stat), float(kpss_p))
    except Exception:
        kpss_out = (np.nan, np.nan)

    # 一个简单判定逻辑（可按你领域需求改严/改松）：
    # - 若 Ljung-Box 在多个 lag 上显著（p<0.05），认为存在时间相关性
    sig_lags = lb.index[lb["lb_pvalue"] < 0.05].tolist()
    has_autocorr = len(sig_lags) >= max(2, max_lag // 5)  # 例如 max_lag=20 时，至少 4 个滞后显著

    report = {
        "n": int(len(series)),
        "max_lag": int(max_lag),
        "acf": {f"lag_{i}": float(acf_vals[i]) for i in range(0, max_lag + 1)},
        "ljung_box_pvalues": {f"lag_{int(i)}": float(lb.loc[i, "lb_pvalue"]) for i in lb.index},
        "ljung_box_significant_lags(p<0.05)": [int(i) for i in sig_lags],
        "durbin_watson": dw,
        "adf_pvalue(unit_root_null)": float(adf_p),
        "kpss_pvalue(stationary_null)": float(kpss_out[1]) if np.isfinite(kpss_out[1]) else None,
        "conclusion_has_time_correlation": bool(has_autocorr),
        "conclusion_basis": (
            "Ljung-Box 在多个滞后上显著（p<0.05）→ 认为存在自相关"
            if has_autocorr
            else "Ljung-Box 多数滞后不显著 → 未发现强自相关证据（不等于绝对无相关）"
        ),
    }
    return report


def main():
    # 改成你的文件路径
    excel_path = r"data/[100.]GHz 8channel 13dBm 2026-01-07 16-57-59/1_QKD_SKR_info.xlsx"

    # 读入（自动识别时间列与数值列）
    df = read_time_series_from_excel(excel_path)

    print("读取成功，列：", df.columns.tolist())
    print("前5行：")
    print(df.head())

    # 逐列判断时间相关性
    for col in df.columns:
        s = df[col].dropna()

        # 如采样不均匀，重采样到固定间隔后再检验（推荐）
        s2, meta = maybe_resample(s, target_freq=None)
        print("\n" + "=" * 80)
        print(f"列 {col} | resample_meta = {meta}")

        rep = autocorr_report(s2, max_lag=20)

        print("样本点数 n =", rep["n"])
        print("Durbin-Watson =", rep["durbin_watson"])
        print("ADF p-value（单位根原假设）=", rep["adf_pvalue(unit_root_null)"])
        print("KPSS p-value（平稳原假设）=", rep["kpss_pvalue(stationary_null)"])
        print("Ljung-Box 显著滞后（p<0.05）=", rep["ljung_box_significant_lags(p<0.05)"])
        print("结论：conclusion_has_time_correlation =", rep["conclusion_has_time_correlation"])
        print("依据：", rep["conclusion_basis"])

        # 如需查看 ACF 数值（lag_0..lag_20）
        # print("ACF：", rep["acf"])

if __name__ == "__main__":
    main()
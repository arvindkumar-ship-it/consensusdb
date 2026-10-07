"""Welch t-test bina scipy ke. n>=30 pe p-value ke liye normal approximation kaafi accurate hai."""
import math


def _mean_var(x):
    n = len(x)
    m = sum(x) / n
    v = sum((a - m) ** 2 for a in x) / (n - 1) if n > 1 else 0.0
    return m, v


def _pct(x, p):
    s = sorted(x)
    return s[min(len(s) - 1, int(round((len(s) - 1) * p / 100)))]


def welch(a, b, min_samples: int = 30) -> dict:
    """a = control/before, b = treatment/after. improvement_pct > 0 matlab b tez (latency kam)."""
    if len(a) < min_samples or len(b) < min_samples:
        return {"significant": None, "reason": f"data kam hai (control={len(a)}, treatment={len(b)}, chahiye >= {min_samples})",
                "n_control": len(a), "n_treatment": len(b)}
    ma, va = _mean_var(a)
    mb, vb = _mean_var(b)
    se = math.sqrt(va / len(a) + vb / len(b))
    if se == 0:
        p = 1.0 if ma == mb else 0.0
        t = 0.0
    else:
        t = (ma - mb) / se
        p = math.erfc(abs(t) / math.sqrt(2))  # two-sided
    return {
        "n_control": len(a), "n_treatment": len(b),
        "mean_control_ms": round(ma, 3), "mean_treatment_ms": round(mb, 3),
        "p95_control_ms": round(_pct(a, 95), 3), "p95_treatment_ms": round(_pct(b, 95), 3),
        "improvement_pct": round(100 * (ma - mb) / ma, 1) if ma else 0.0,
        "t": round(t, 3), "p_value": round(p, 6), "significant": p < 0.05,
    }

"""Statistical analysis (spec 26/27, design decision C-12).

Cp/Cpk use the *within* sigma estimated from the average moving range (MR-bar / 1.128, individuals data);
Pp/Ppk use the overall sample sigma (n-1). Indices are never computed when data requirements are not met —
an explicit status is returned instead.
"""
import math
import statistics
from typing import Sequence

D2 = 1.128   # d2 for moving range of size 2


def describe(values: Sequence[float]) -> dict:
    n = len(values)
    if n == 0:
        return {"n": 0, "status": "NO_DATA"}
    out = {"n": n, "mean": statistics.fmean(values), "median": statistics.median(values), "min": min(values), "max": max(values)}
    if n >= 2:
        sd = statistics.stdev(values)
        out.update(sd=sd, variance=sd * sd, cv_pct=(sd / out["mean"] * 100) if out["mean"] else None)
    else:
        out.update(sd=None, variance=None, cv_pct=None)
    return out


def sigma_within(values: Sequence[float]) -> float | None:
    if len(values) < 2:
        return None
    mr = [abs(values[i] - values[i - 1]) for i in range(1, len(values))]
    return (sum(mr) / len(mr)) / D2


def control_limits(values: Sequence[float]) -> dict | None:
    """Individuals chart: X-bar ± 2.66·MR-bar."""
    if len(values) < 2:
        return None
    mr = [abs(values[i] - values[i - 1]) for i in range(1, len(values))]
    mrbar = sum(mr) / len(mr)
    cl = statistics.fmean(values)
    return {"cl": cl, "ucl": cl + 2.66 * mrbar, "lcl": cl - 2.66 * mrbar, "mr_bar": mrbar,
            "sigma": mrbar / D2}


def capability(values: Sequence[float], lsl: float | None, usl: float | None, min_n: int = 25) -> dict:
    n = len(values)
    res: dict = {"n": n, "min_n": min_n, "cp": None, "cpk": None, "pp": None, "ppk": None, "status": "OK", "notes": []}
    if lsl is None and usl is None:
        res["status"] = "SPECIFICATION_UNAVAILABLE"
        return res
    if n < min_n:
        res["status"] = "INSUFFICIENT_DATA"
        return res
    mean = statistics.fmean(values)
    sw, so = sigma_within(values), statistics.stdev(values)
    if not sw or not so or sw <= 0 or so <= 0:
        res["status"] = "ZERO_VARIANCE"
        return res
    res.update(mean=mean, sigma_within=sw, sigma_overall=so)
    if lsl is not None and usl is not None:
        res["cp"], res["pp"] = (usl - lsl) / (6 * sw), (usl - lsl) / (6 * so)
    cpu = (usl - mean) / (3 * sw) if usl is not None else None
    cpl = (mean - lsl) / (3 * sw) if lsl is not None else None
    ppu = (usl - mean) / (3 * so) if usl is not None else None
    ppl = (mean - lsl) / (3 * so) if lsl is not None else None
    res["cpk"] = min(x for x in (cpu, cpl) if x is not None)
    res["ppk"] = min(x for x in (ppu, ppl) if x is not None)
    if lsl is None:
        res["notes"].append("LSL unavailable: one-sided (upper) index")
    if usl is None:
        res["notes"].append("USL unavailable: one-sided (lower) index")
    if n >= 8:
        # Shapiro-Wilk would need scipy; use a skewness/kurtosis screen as a lightweight normality warning
        m = mean
        m2 = sum((x - m) ** 2 for x in values) / n
        m3 = sum((x - m) ** 3 for x in values) / n
        m4 = sum((x - m) ** 4 for x in values) / n
        skew, kurt = m3 / m2 ** 1.5, m4 / m2 ** 2 - 3
        if abs(skew) > 1 or abs(kurt) > 2:
            res["notes"].append("NON_NORMAL_WARNING: distribution is skewed/heavy-tailed; indices may be unreliable")
    return res


def nelson_rules(values: Sequence[float], mean: float, sigma: float, enabled: Sequence[int] = (1, 2, 3, 4, 5, 6)) -> list[dict]:
    """Return violations as {rule, index} (index = position of the point that completes the pattern)."""
    out: list[dict] = []
    if sigma <= 0 or len(values) < 2:
        return out
    z = [(v - mean) / sigma for v in values]
    n = len(z)

    def add(rule: int, i: int, text: str):
        if rule in enabled:
            out.append({"rule": rule, "index": i, "text": text})

    for i in range(n):
        if abs(z[i]) > 3:
            add(1, i, "One point beyond 3σ")
        if i >= 8 and (all(x > 0 for x in z[i - 8:i + 1]) or all(x < 0 for x in z[i - 8:i + 1])):
            add(2, i, "Nine points in a row on the same side of the mean")
        if i >= 5 and (all(z[j] < z[j + 1] for j in range(i - 5, i)) or all(z[j] > z[j + 1] for j in range(i - 5, i))):
            add(3, i, "Six points steadily increasing or decreasing")
        if i >= 13 and all((z[j] - z[j - 1]) * (z[j + 1] - z[j]) < 0 for j in range(i - 12, i)):
            add(4, i, "Fourteen points alternating up and down")
        if i >= 2 and sum(1 for x in z[i - 2:i + 1] if x > 2) >= 2 or i >= 2 and sum(1 for x in z[i - 2:i + 1] if x < -2) >= 2:
            add(5, i, "Two of three points beyond 2σ on the same side")
        if i >= 4 and (sum(1 for x in z[i - 4:i + 1] if x > 1) >= 4 or sum(1 for x in z[i - 4:i + 1] if x < -1) >= 4):
            add(6, i, "Four of five points beyond 1σ on the same side")
        if i >= 14 and all(abs(x) < 1 for x in z[i - 14:i + 1]):
            add(7, i, "Fifteen points within 1σ of the mean (stratification)")
        if i >= 7 and all(abs(x) > 1 for x in z[i - 7:i + 1]):
            add(8, i, "Eight points beyond 1σ on either side")
    return out


def month_key(d) -> str:
    return f"{d.year}-{d.month:02d}"

from collections import defaultdict
from datetime import date, timedelta
from statistics import mean


def summarize(records):
    rows = sorted(records, key=lambda r: r["date"])
    base = {"source": "UCI Bike Sharing / Capital Bikeshare (사용자 변경 포함)", "unit": "건/일"}
    if not rows:
        return {**base, "period": None, "as_of": None, "count": 0, "metrics": {
            "total": 0, "average": None, "max": None, "min": None,
            "max_date": None, "min_date": None}, "trend": "데이터 없음",
            "recent": {"change_percent": None}, "monthly": [], "annual": []}
    values = [r["value"] for r in rows]
    lowest, highest = min(rows, key=lambda r: r["value"]), max(rows, key=lambda r: r["value"])
    monthly, annual = defaultdict(list), defaultdict(list)
    for row in rows:
        monthly[row["date"][:7]].append(row["value"])
        annual[row["date"][:4]].append(row["value"])
    last = date.fromisoformat(rows[-1]["date"])
    by_date = {r["date"]: r["value"] for r in rows}

    def window(start):
        days = [(last - timedelta(days=i)).isoformat() for i in range(start, start + 7)]
        return mean([by_date[d] for d in days]) if all(d in by_date for d in days) else None

    current, previous = window(0), window(7)
    change = (current / previous - 1) * 100 if current is not None and previous not in (None, 0) else None
    if change is None:
        trend = "비교 불가 · 연속 14일 기록 또는 양수인 이전 7일 평균 필요"
    else:
        direction = "유지" if abs(change) < 1 else ("증가" if change > 0 else "감소")
        trend = f"{direction} · 최근 7일 평균 {change:+.1f}% (직전 7일 대비)"
    return {**base, "period": f"{rows[0]['date']} ~ {rows[-1]['date']}", "as_of": rows[-1]["date"],
            "count": len(rows), "metrics": {"total": sum(values), "average": round(mean(values), 2),
            "max": highest["value"], "max_date": highest["date"], "min": lowest["value"],
            "min_date": lowest["date"]}, "trend": trend,
            "recent": {"current_average": round(current, 2) if current is not None else None,
                       "previous_average": round(previous, 2) if previous is not None else None,
                       "change_percent": round(change, 2) if change is not None else None,
                       "start": (last - timedelta(days=6)).isoformat(), "end": last.isoformat()},
            "monthly": [{"month": k, "count": len(v), "total": sum(v), "average": round(mean(v), 2)}
                        for k, v in monthly.items()],
            "annual": [{"year": k, "count": len(v), "total": sum(v), "average": round(mean(v), 2)}
                       for k, v in annual.items()]}

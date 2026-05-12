from typing import Any
import pandas as pd


def detect_elliott_scenario(swings: pd.DataFrame, trend: str) -> dict[str, Any]:
    """
    Uproszczony scenariusz falowy.

    To nie jest pełne automatyczne oznaczanie fal Elliotta. Moduł sprawdza,
    czy ostatnie swingi mogą przypominać układ 1-2-3 albo 1-2-3-4-5.
    """
    if swings.empty or trend not in ["wzrostowy", "spadkowy"] or len(swings) < 4:
        return {"available": False, "status": "Za mało danych do scenariusza Elliotta."}

    recent = swings.tail(6).reset_index(drop=True)
    score = 0
    messages = []

    if trend == "wzrostowy":
        # Szukamy uproszczonego układu low-high-low-high-low-high.
        expected = ["low", "high", "low", "high"]
        if len(recent) >= 4 and list(recent.tail(4)["type"]) == expected:
            wave = recent.tail(4).reset_index(drop=True)
            p0, p1, p2, p3 = [float(x) for x in wave["price"]]
            f1 = p1 - p0
            f2 = p1 - p2
            f3 = p3 - p2

            if f1 > 0 and f2 > 0 and f3 > 0:
                retracement = f2 / f1
                extension = f3 / f1

                if retracement >= 0.5 and p2 > p0:
                    score += 2
                    messages.append("F2 spełnia warunek min. 50% i nie wybija początku F1.")
                if extension >= 1.414:
                    score += 2
                    messages.append("F3 osiąga min. 141,4% F1.")
                if p3 > p1:
                    score += 1
                    messages.append("F3 wybija szczyt F1.")

                return {
                    "available": True,
                    "scenario": "Możliwy układ wzrostowy 1-2-3",
                    "score": score,
                    "retracement_f2": retracement,
                    "extension_f3": extension,
                    "status": " | ".join(messages) if messages else "Scenariusz słaby / niepełny.",
                }

    if trend == "spadkowy":
        expected = ["high", "low", "high", "low"]
        if len(recent) >= 4 and list(recent.tail(4)["type"]) == expected:
            wave = recent.tail(4).reset_index(drop=True)
            p0, p1, p2, p3 = [float(x) for x in wave["price"]]
            f1 = p0 - p1
            f2 = p2 - p1
            f3 = p2 - p3

            if f1 > 0 and f2 > 0 and f3 > 0:
                retracement = f2 / f1
                extension = f3 / f1

                if retracement >= 0.5 and p2 < p0:
                    score += 2
                    messages.append("F2 spełnia warunek min. 50% i nie wybija początku F1.")
                if extension >= 1.414:
                    score += 2
                    messages.append("F3 osiąga min. 141,4% F1.")
                if p3 < p1:
                    score += 1
                    messages.append("F3 wybija dołek F1.")

                return {
                    "available": True,
                    "scenario": "Możliwy układ spadkowy 1-2-3",
                    "score": score,
                    "retracement_f2": retracement,
                    "extension_f3": extension,
                    "status": " | ".join(messages) if messages else "Scenariusz słaby / niepełny.",
                }

    return {"available": False, "status": "Brak czytelnego prostego scenariusza 1-2-3."}

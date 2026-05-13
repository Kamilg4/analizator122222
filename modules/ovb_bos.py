from typing import Any
import pandas as pd
from .config import OVB_RATIO


def find_corrections(swings: pd.DataFrame, trend: str) -> list[dict[str, Any]]:
    """Znajduje korekty w aktualnym trendzie."""
    corrections = []

    if trend == "wzrostowy":
        for i in range(len(swings) - 1):
            start = swings.iloc[i]
            end = swings.iloc[i + 1]

            if start["type"] == "high" and end["type"] == "low":
                size = float(start["price"] - end["price"])

                if size > 0:
                    corrections.append(
                        {
                            "from_time": str(start["time"]),
                            "to_time": str(end["time"]),
                            "from_price": float(start["price"]),
                            "to_price": float(end["price"]),
                            "size": size,
                        }
                    )

    elif trend == "spadkowy":
        for i in range(len(swings) - 1):
            start = swings.iloc[i]
            end = swings.iloc[i + 1]

            if start["type"] == "low" and end["type"] == "high":
                size = float(end["price"] - start["price"])

                if size > 0:
                    corrections.append(
                        {
                            "from_time": str(start["time"]),
                            "to_time": str(end["time"]),
                            "from_price": float(start["price"]),
                            "to_price": float(end["price"]),
                            "size": size,
                        }
                    )

    return corrections


def calculate_ovb(swings: pd.DataFrame, trend: str, last_candle: pd.Series) -> dict[str, Any]:
    """Wyznacza OVB jako 141,4% największej korekty w trendzie."""
    if swings.empty or trend not in ["wzrostowy", "spadkowy"]:
        return {
            "available": False,
            "reason": "Brak czytelnego trendu. OVB nie jest liczone.",
            "state": "unavailable",
        }

    corrections = find_corrections(swings, trend)

    if not corrections:
        return {
            "available": False,
            "reason": "Nie wykryto korekt potrzebnych do obliczenia OVB.",
            "state": "unavailable",
        }

    max_correction = max(corrections, key=lambda item: item["size"])

    if trend == "wzrostowy":
        last_highs = swings[swings["type"] == "high"]

        if last_highs.empty:
            return {"available": False, "reason": "Brak ostatniego szczytu dla trendu wzrostowego.", "state": "unavailable"}

        base_swing = last_highs.iloc[-1]
        ovb_level = float(base_swing["price"] - OVB_RATIO * max_correction["size"])

        close = float(last_candle["close"])
        low = float(last_candle["low"])

        if close < ovb_level:
            state = "confirmed"
            status = "OVB POTWIERDZONE — świeca zamknęła się poniżej poziomu OVB. Trend wzrostowy jest zagrożony."
        elif low < ovb_level:
            state = "wick"
            status = "OVB NARUSZONE KNOTEM — cena zeszła poniżej OVB, ale zamknięcie nie potwierdziło przebicia."
        else:
            state = "not_broken"
            status = "OVB NIEPRZEBITE — trend wzrostowy nadal technicznie się broni."

    else:
        last_lows = swings[swings["type"] == "low"]

        if last_lows.empty:
            return {"available": False, "reason": "Brak ostatniego dołka dla trendu spadkowego.", "state": "unavailable"}

        base_swing = last_lows.iloc[-1]
        ovb_level = float(base_swing["price"] + OVB_RATIO * max_correction["size"])

        close = float(last_candle["close"])
        high = float(last_candle["high"])

        if close > ovb_level:
            state = "confirmed"
            status = "OVB POTWIERDZONE — świeca zamknęła się powyżej poziomu OVB. Trend spadkowy jest zagrożony."
        elif high > ovb_level:
            state = "wick"
            status = "OVB NARUSZONE KNOTEM — cena wyszła powyżej OVB, ale zamknięcie nie potwierdziło przebicia."
        else:
            state = "not_broken"
            status = "OVB NIEPRZEBITE — trend spadkowy nadal technicznie się broni."

    return {
        "available": True,
        "trend": trend,
        "corrections": corrections,
        "max_correction": max_correction,
        "base_swing_time": str(base_swing["time"]),
        "base_swing_price": float(base_swing["price"]),
        "ovb_level": ovb_level,
        "state": state,
        "status": status,
    }


def find_last_impulse(swings: pd.DataFrame, trend: str) -> dict[str, Any]:
    """
    Szuka ostatniego impulsu w aktualnym trendzie.

    Trend wzrostowy: ostatni impuls = low -> high.
    Trend spadkowy: ostatni impuls = high -> low.
    """
    if swings.empty or trend not in ["wzrostowy", "spadkowy"]:
        return {"available": False, "reason": "Brak trendu lub swingów."}

    last_impulse = None

    if trend == "wzrostowy":
        for i in range(len(swings) - 1):
            start = swings.iloc[i]
            end = swings.iloc[i + 1]

            if start["type"] == "low" and end["type"] == "high" and end["price"] > start["price"]:
                last_impulse = {
                    "direction": "up",
                    "base_time": str(start["time"]),
                    "base_price": float(start["price"]),
                    "end_time": str(end["time"]),
                    "end_price": float(end["price"]),
                }

    if trend == "spadkowy":
        for i in range(len(swings) - 1):
            start = swings.iloc[i]
            end = swings.iloc[i + 1]

            if start["type"] == "high" and end["type"] == "low" and end["price"] < start["price"]:
                last_impulse = {
                    "direction": "down",
                    "base_time": str(start["time"]),
                    "base_price": float(start["price"]),
                    "end_time": str(end["time"]),
                    "end_price": float(end["price"]),
                }

    if last_impulse is None:
        return {"available": False, "reason": "Nie znaleziono ostatniego impulsu dla BOS."}

    return {"available": True, **last_impulse}


def calculate_bos(swings: pd.DataFrame, trend: str, last_candle: pd.Series) -> dict[str, Any]:
    """Sprawdza BOS, czyli wybicie podstawy ostatniego impulsu."""
    impulse = find_last_impulse(swings, trend)

    if not impulse.get("available"):
        return {
            "available": False,
            "reason": impulse.get("reason", "Nie udało się wyznaczyć impulsu."),
            "state": "unavailable",
        }

    base_price = impulse["base_price"]
    close = float(last_candle["close"])
    high = float(last_candle["high"])
    low = float(last_candle["low"])

    if trend == "wzrostowy":
        if close < base_price:
            state = "confirmed"
            status = "BOS POTWIERDZONY — zamknięcie świecy poniżej podstawy ostatniego impulsu wzrostowego."
        elif low < base_price:
            state = "sweep"
            status = "LIQUIDITY SWEEP — cena zebrała płynność poniżej podstawy, ale zamknęła się wyżej (fałszywe wybicie)."
        else:
            state = "not_broken"
            status = "BOS BRAK — podstawa ostatniego impulsu wzrostowego nie została wybita."

    elif trend == "spadkowy":
        if close > base_price:
            state = "confirmed"
            status = "BOS POTWIERDZONY — zamknięcie świecy powyżej podstawy ostatniego impulsu spadkowego."
        elif high > base_price:
            state = "sweep"
            status = "LIQUIDITY SWEEP — cena zebrała płynność powyżej podstawy, ale zamknęła się niżej (fałszywe wybicie)."
        else:
            state = "not_broken"
            status = "BOS BRAK — podstawa ostatniego impulsu spadkowego nie została wybita."

    else:
        return {
            "available": False,
            "reason": "BOS liczony jest tylko dla trendu wzrostowego albo spadkowego.",
            "state": "unavailable",
        }

    return {
        "available": True,
        "trend": trend,
        "base_price": base_price,
        "base_time": impulse["base_time"],
        "impulse_end_price": impulse["end_price"],
        "impulse_end_time": impulse["end_time"],
        "state": state,
        "status": status,
    }


def check_opposite_structure(swings: pd.DataFrame, previous_trend: str) -> dict[str, Any]:
    """
    Sprawdza uproszczony trzeci element zmiany trendu:
    czy pojawia się nowa przeciwna struktura.
    """
    if swings.empty or previous_trend not in ["wzrostowy", "spadkowy"]:
        return {"available": False, "confirmed": False, "status": "Brak danych do oceny nowej struktury."}

    highs = swings[swings["type"] == "high"].tail(2)
    lows = swings[swings["type"] == "low"].tail(2)

    if len(highs) < 2 or len(lows) < 2:
        return {"available": False, "confirmed": False, "status": "Za mało szczytów/dołków do oceny nowej struktury."}

    previous_high = float(highs["price"].iloc[0])
    current_high = float(highs["price"].iloc[1])
    previous_low = float(lows["price"].iloc[0])
    current_low = float(lows["price"].iloc[1])

    if previous_trend == "wzrostowy":
        confirmed = current_high < previous_high and current_low < previous_low
        status = "NOWA STRUKTURA SPADKOWA — ostatni szczyt i dołek są niżej niż poprzednie." if confirmed else "Brak pełnej nowej struktury spadkowej."
    else:
        confirmed = current_high > previous_high and current_low > previous_low
        status = "NOWA STRUKTURA WZROSTOWA — ostatni szczyt i dołek są wyżej niż poprzednie." if confirmed else "Brak pełnej nowej struktury wzrostowej."

    return {
        "available": True,
        "confirmed": confirmed,
        "status": status,
        "previous_high": previous_high,
        "current_high": current_high,
        "previous_low": previous_low,
        "current_low": current_low,
    }


def build_trend_change_summary(ovb_result: dict[str, Any], bos_result: dict[str, Any], opposite_structure: dict[str, Any]) -> dict[str, Any]:
    """Łączy OVB, BOS i nową strukturę w jeden opis 3x zmiany trendu."""
    ovb_confirmed = ovb_result.get("state") == "confirmed"
    bos_confirmed = bos_result.get("state") == "confirmed"
    new_structure_confirmed = bool(opposite_structure.get("confirmed"))

    score = int(ovb_confirmed) + int(bos_confirmed) + int(new_structure_confirmed)

    if score == 0:
        status = "Brak potwierdzeń zmiany trendu. Aktualny trend nadal się broni."
    elif score == 1:
        status = "Pierwsze ostrzeżenie zmiany trendu. Jeszcze za mało na pełną zmianę kierunku."
    elif score == 2:
        status = "Silne ostrzeżenie zmiany trendu. Brakuje jednego z trzech potwierdzeń."
    else:
        status = "3x ZMIANA TRENDU SPEŁNIONA — OVB, BOS i nowa struktura są potwierdzone."

    return {
        "score": score,
        "ovb_confirmed": ovb_confirmed,
        "bos_confirmed": bos_confirmed,
        "new_structure_confirmed": new_structure_confirmed,
        "status": status,
    }

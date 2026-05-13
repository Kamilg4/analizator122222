from __future__ import annotations

from typing import Any
import pandas as pd


DIRECTIONAL_TRENDS = {"wzrostowy", "spadkowy"}


def calculate_trend_scores(swings: pd.DataFrame, points_to_check: int) -> dict[str, Any]:
    """
    Liczy jakość trendu na wybranej liczbie ostatnich szczytów i dołków.

    Metryki podstawowe:
    - up_score: jak często kolejne szczyty i dołki rosną,
    - down_score: jak często kolejne szczyty i dołki spadają.

    Metryki pomocnicze:
    - high_net_pct / low_net_pct: łączne przesunięcie szczytów i dołków
      w badanym oknie, dzięki czemu trend główny nie znika tylko dlatego,
      że końcówka ruchu ma krótką lokalną korektę.
    """
    points_to_check = max(int(points_to_check), 3)

    empty_result = {
        "available": False,
        "high_up_score": 0.0,
        "low_up_score": 0.0,
        "high_down_score": 0.0,
        "low_down_score": 0.0,
        "up_score": 0.0,
        "down_score": 0.0,
        "high_count": 0,
        "low_count": 0,
        "points_to_check": points_to_check,
        "first_high": None,
        "last_high": None,
        "first_low": None,
        "last_low": None,
        "high_net_pct": 0.0,
        "low_net_pct": 0.0,
        "avg_net_pct": 0.0,
    }

    if swings is None or swings.empty:
        return empty_result

    highs = swings[swings["type"] == "high"].tail(points_to_check)["price"].reset_index(drop=True)
    lows = swings[swings["type"] == "low"].tail(points_to_check)["price"].reset_index(drop=True)

    if len(highs) < 3 or len(lows) < 3:
        return empty_result | {
            "high_count": int(len(highs)),
            "low_count": int(len(lows)),
        }

    high_diff = highs.diff().dropna()
    low_diff = lows.diff().dropna()

    high_up_score = float((high_diff > 0).mean())
    low_up_score = float((low_diff > 0).mean())
    high_down_score = float((high_diff < 0).mean())
    low_down_score = float((low_diff < 0).mean())

    up_score = (high_up_score + low_up_score) / 2.0
    down_score = (high_down_score + low_down_score) / 2.0

    first_high = float(highs.iloc[0])
    last_high = float(highs.iloc[-1])
    first_low = float(lows.iloc[0])
    last_low = float(lows.iloc[-1])

    high_net_pct = ((last_high - first_high) / first_high * 100.0) if first_high else 0.0
    low_net_pct = ((last_low - first_low) / first_low * 100.0) if first_low else 0.0
    avg_net_pct = (high_net_pct + low_net_pct) / 2.0

    return {
        "available": True,
        "high_up_score": high_up_score,
        "low_up_score": low_up_score,
        "high_down_score": high_down_score,
        "low_down_score": low_down_score,
        "up_score": up_score,
        "down_score": down_score,
        "high_count": int(len(highs)),
        "low_count": int(len(lows)),
        "points_to_check": points_to_check,
        "first_high": first_high,
        "last_high": last_high,
        "first_low": first_low,
        "last_low": last_low,
        "high_net_pct": high_net_pct,
        "low_net_pct": low_net_pct,
        "avg_net_pct": avg_net_pct,
    }


def _trend_from_scores(scores: dict[str, Any], min_score: float) -> str:
    """Zamienia surowe score struktury na etykietę trendu."""
    if not scores.get("available"):
        return "nieczytelny"

    up_score = float(scores.get("up_score", 0.0))
    down_score = float(scores.get("down_score", 0.0))

    if up_score >= min_score and up_score > down_score:
        return "wzrostowy"

    if down_score >= min_score and down_score > up_score:
        return "spadkowy"

    return "nieczytelny"


def _major_trend_with_displacement(scores: dict[str, Any], min_score: float) -> tuple[str, str]:
    """
    Klasyfikuje trend główny.

    Najpierw korzysta z klasycznej logiki strukturalnej HH/HL lub LH/LL.
    Jeśli sama sekwencja zmian jest mieszana, ale w całym badanym oknie zarówno
    szczyty, jak i dołki przesunęły się wyraźnie w jednym kierunku, uznajemy to za
    trend główny przez szersze przemieszczenie struktury.

    Ta reguła pomaga w sytuacjach typu:
    - długi spadek,
    - końcowe odbicie z kilkoma lokalnymi HH/HL,
    - stary algorytm mówił "wzrostowy", mimo że większy trend nadal był spadkowy.
    """
    structural_trend = _trend_from_scores(scores, min_score)
    if structural_trend in DIRECTIONAL_TRENDS:
        return structural_trend, "struktura"

    if not scores.get("available"):
        return "nieczytelny", "brak_danych"

    high_net_pct = float(scores.get("high_net_pct", 0.0))
    low_net_pct = float(scores.get("low_net_pct", 0.0))

    # Próg 3% dotyczy tylko szerszego okna swingów, więc nie reaguje na mikroszum.
    if high_net_pct <= -3.0 and low_net_pct <= -3.0:
        return "spadkowy", "przemieszczenie_struktury_w_dol"

    if high_net_pct >= 3.0 and low_net_pct >= 3.0:
        return "wzrostowy", "przemieszczenie_struktury_w_gore"

    return "nieczytelny", "mieszany"


def determine_trend(swings: pd.DataFrame, points_to_check: int, min_score: float) -> str:
    """
    Funkcja zachowana dla zgodności wstecznej.

    Nowa aplikacja używa analyze_trend_structure(...), ale ta funkcja pozwala
    uniknąć błędów w starszych fragmentach kodu.
    """
    scores = calculate_trend_scores(swings, points_to_check)
    return _trend_from_scores(scores, min_score)


def analyze_trend_structure(
    swings: pd.DataFrame,
    local_points_to_check: int,
    min_score: float,
    *,
    major_points_multiplier: int = 3,
    major_points_min: int = 8,
    major_points_max: int = 18,
) -> dict[str, Any]:
    """
    Buduje dwuwarstwowy kontekst trendu na tym samym wybranym interwale:
    - trend lokalny: ostatnie kilka punktów swingowych,
    - trend główny: szersze okno swingów.

    Dzięki temu lokalne 3-4 wyższe szczyty w dużym trendzie spadkowym nie zmieniają
    już automatycznie oceny całego rynku na "wzrostowy".
    """
    local_points = max(int(local_points_to_check), 3)
    major_points = max(int(major_points_min), local_points * int(major_points_multiplier))
    major_points = min(int(major_points_max), major_points)

    local_scores = calculate_trend_scores(swings, local_points)
    major_scores = calculate_trend_scores(swings, major_points)

    local_trend = _trend_from_scores(local_scores, min_score)
    major_trend, major_basis = _major_trend_with_displacement(major_scores, min_score)

    if major_trend in DIRECTIONAL_TRENDS and local_trend in DIRECTIONAL_TRENDS:
        raw_state = "zgodny" if major_trend == local_trend else "konflikt_glowny_lokalny"
    elif major_trend in DIRECTIONAL_TRENDS:
        raw_state = "trend_glowny_bez_lokalnego_potwierdzenia"
    elif local_trend in DIRECTIONAL_TRENDS:
        raw_state = "trend_lokalny_bez_glownego"
    else:
        raw_state = "nieczytelny"

    return {
        "available": bool(local_scores.get("available") or major_scores.get("available")),
        "local_points_to_check": local_points,
        "major_points_to_check": major_points,
        "min_score": float(min_score),
        "local_scores": local_scores,
        "major_scores": major_scores,
        "local_trend": local_trend,
        "major_trend": major_trend,
        "major_trend_basis": major_basis,
        "raw_state": raw_state,
    }


def get_change_reference_trend(structural_context: dict[str, Any]) -> str:
    """
    Wybiera trend, względem którego liczymy OVB/BOS/3x zmianę trendu.

    Priorytet:
    1. trend główny, jeśli jest czytelny,
    2. trend lokalny, jeżeli większy kontekst jest nieczytelny,
    3. nieczytelny, jeśli nic nie jest wiarygodne.
    """
    major_trend = str(structural_context.get("major_trend", "nieczytelny"))
    local_trend = str(structural_context.get("local_trend", "nieczytelny"))

    if major_trend in DIRECTIONAL_TRENDS:
        return major_trend
    if local_trend in DIRECTIONAL_TRENDS:
        return local_trend
    return "nieczytelny"


def finalize_trend_context(
    structural_context: dict[str, Any],
    trend_change_summary: dict[str, Any],
) -> dict[str, Any]:
    """
    Buduje końcowy trend decyzyjny używany przez ranking stref.

    Zasada:
    - trend główny ma pierwszeństwo,
    - lokalny ruch przeciwny do trendu głównego traktujemy jak korektę/odreagowanie,
      dopóki OVB + BOS + nowa struktura nie dadzą mocniejszego potwierdzenia zmiany,
    - gdy trend główny jest nieczytelny, sam lokalny ruch NIE jest traktowany jako
      pełny trend decyzyjny; algorytm zachowuje ostrożność.
    """
    context = dict(structural_context)
    score = int(trend_change_summary.get("score", 0) or 0)

    major_trend = str(context.get("major_trend", "nieczytelny"))
    local_trend = str(context.get("local_trend", "nieczytelny"))

    effective_trend = "nieczytelny"
    market_state = "nieczytelny"
    status = "Brak wystarczająco czytelnej struktury trendowej."
    decision_note = "Nie wymuszam kierunku rynku."
    countertrend_hint = ""

    if major_trend in DIRECTIONAL_TRENDS and local_trend in DIRECTIONAL_TRENDS:
        if major_trend == local_trend:
            effective_trend = major_trend
            market_state = "trend_zgodny"
            status = f"Trend główny i lokalny są zgodne: {major_trend}."
            decision_note = "Kierunek z lokalnej struktury potwierdza szerszy kontekst."
        else:
            if score >= 3:
                effective_trend = local_trend
                market_state = "zmiana_trendu_potwierdzona"
                status = (
                    f"Trend główny był {major_trend}, ale lokalna struktura {local_trend} "
                    "ma komplet 3/3 potwierdzeń zmiany. Trend decyzyjny przełączam na nowy kierunek."
                )
                decision_note = "Zmiana kierunku jest potwierdzona według OVB + BOS + nowej struktury."
            elif score == 2:
                effective_trend = major_trend
                market_state = "silne_ostrzezenie_zmiany"
                status = (
                    f"Trend główny nadal: {major_trend}. Lokalna struktura jest {local_trend}, "
                    "a 3x zmiana trendu ma 2/3 potwierdzeń — to silne ostrzeżenie, ale jeszcze nie pełne odwrócenie."
                )
                decision_note = "Nie przestawiam trendu na przeciwny bez trzeciego potwierdzenia."
                countertrend_hint = (
                    "Lokalny ruch przeciwny może być późnym etapem korekty albo wczesną próbą zmiany trendu."
                )
            else:
                effective_trend = major_trend
                market_state = "lokalna_korekta_przeciw_trendowi"
                status = (
                    f"Trend główny: {major_trend}. Ostatnie swingi lokalnie wyglądają {local_trend}, "
                    "ale bez mocnej 3x zmiany trendu traktuję to jako korektę / odreagowanie, a nie pełne odwrócenie."
                )
                decision_note = "Lokalne HH/HL lub LH/LL nie wystarczają do odwrócenia całego trendu."
                countertrend_hint = (
                    "To może odpowiadać strukturze korekcyjnej lub ruchowi niższego rzędu; "
                    "algorytm nie nazywa tego automatycznie falą Elliotta, ale blokuje przedwczesne odwrócenie trendu."
                )

    elif major_trend in DIRECTIONAL_TRENDS:
        effective_trend = major_trend
        market_state = "trend_glowny_bez_lokalnego_potwierdzenia"
        status = (
            f"Trend główny jest {major_trend}, natomiast ostatnia struktura lokalna nie daje jeszcze "
            "czytelnego, niezależnego potwierdzenia kierunku."
        )
        decision_note = "Priorytet ma szerszy trend główny."

    elif local_trend in DIRECTIONAL_TRENDS:
        effective_trend = "nieczytelny"
        market_state = "tylko_lokalny_kierunek_bez_trendu_glownego"
        status = (
            f"Szerszy trend główny jest nieczytelny. Lokalna struktura wygląda {local_trend}, "
            "ale to za mało, aby program ogłosił pełny trend decyzyjny."
        )
        decision_note = "Lokalny kierunek traktuję jako informację pomocniczą, nie jako pełny trend."
        countertrend_hint = (
            "To może być krótki swing lub korekta w szerszej strukturze. Bez czytelnego trendu głównego algorytm zachowuje ostrożność."
        )

    else:
        effective_trend = "nieczytelny"
        market_state = "nieczytelny"
        status = "Ani trend główny, ani lokalny nie dają wystarczająco czytelnego kierunku."
        decision_note = "Rynek ma charakter mieszany / konsolidacyjny albo struktura jest za słaba."

    context.update(
        {
            "effective_trend": effective_trend,
            "market_state": market_state,
            "status": status,
            "decision_note": decision_note,
            "countertrend_hint": countertrend_hint,
            "trend_change_score": score,
            "display_label": effective_trend,
        }
    )
    return context


def get_trend_comment(trend: str, scores: dict[str, Any], min_score: float) -> str:
    """
    Funkcja zgodności wstecznej.
    Nowy UI korzysta przede wszystkim z trend_context['status'].
    """
    if not scores.get("available"):
        return "Za mało swingów, żeby wiarygodnie określić trend."

    up_pct = float(scores.get("up_score", 0.0)) * 100.0
    down_pct = float(scores.get("down_score", 0.0)) * 100.0
    min_pct = float(min_score) * 100.0

    if trend == "wzrostowy":
        return (
            f"Struktura częściej tworzy wyższe szczyty i wyższe dołki. "
            f"Wynik wzrostowy: {up_pct:.0f}% przy wymaganych {min_pct:.0f}%."
        )

    if trend == "spadkowy":
        return (
            f"Struktura częściej tworzy niższe szczyty i niższe dołki. "
            f"Wynik spadkowy: {down_pct:.0f}% przy wymaganych {min_pct:.0f}%."
        )

    return (
        f"Rynek jest nieczytelny albo konsolidacyjny. Wynik wzrostowy: {up_pct:.0f}%, "
        f"wynik spadkowy: {down_pct:.0f}%, wymagane: {min_pct:.0f}%."
    )

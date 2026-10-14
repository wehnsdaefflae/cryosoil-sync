"""cryosoil_sync — Prinzipbeweis: Bodendaten physikalisch prüfen und Standorte schützen.

Zwei Dinge, die es für deutsche Bodendaten bisher nicht als Bibliothek gibt, werden hier
an einem kleinen Datensatz gezeigt:

1. **Physikalische Plausibilitätsprüfung.** Dichte, Porosität und Wassergehalt einer
   Bodenschicht hängen physikalisch zusammen. Eine Kombination kann plausibel *aussehen*
   und trotzdem unmöglich sein — der Wassergehalt übersteigt den Porenraum, oder
   Trockendichte und Porosität widersprechen der Korndichte. Ein Wertebereichsprüfer
   (`Pandera`, `Great Expectations`) findet das nicht, weil jeder Einzelwert im Rahmen
   liegt.

2. **Standortschutz nach Planar-Laplace.** Bohrprofile liegen oft auf privaten
   Grundstücken, weshalb Behörden die Koordinaten vorsichtshalber gar nicht
   veröffentlichen. Räumliche Differential Privacy verschiebt jeden Punkt mit
   kontrolliertem Rauschen: das einzelne Grundstück ist nicht mehr bestimmbar, der
   Mittelwert über die Fläche bleibt erhalten.

Dazu kommt die Schätzung der Wärmeleitfähigkeit mit **Unsicherheitsbereich** statt eines
nackten Werts — nach dem Verfahren aus Bertermann, Rammler, Wernsdorfer, Hagenauer (2024),
*Soil Systems* 8(2), hier als vereinfachte Fassung.

Ausführen:   python3 cryosoil_sync.py
Tests:       python3 cryosoil_sync.py --selftest
"""

from __future__ import annotations

import math
import random
import sys
from dataclasses import dataclass
from enum import Enum

KORNDICHTE = 2650.0   # kg/m³, Quarz — Standardannahme der Bodenkunde
WASSERDICHTE = 1000.0  # kg/m³


class Pruefung(Enum):
    OK = "plausibel"
    WIDERSPRUCH = "physikalisch unmöglich"
    UNVOLLSTAENDIG = "nicht prüfbar"


@dataclass
class Schicht:
    """Eine Bodenschicht, wie sie aus einem Schichtenverzeichnis kommt."""

    tiefe_von_m: float
    tiefe_bis_m: float
    trockendichte_kg_m3: float | None = None
    porositaet: float | None = None          # Volumenanteil 0..1
    wassergehalt_vol: float | None = None    # Volumenanteil 0..1
    bodenart: str = ""

    @property
    def maechtigkeit_m(self) -> float:
        return self.tiefe_bis_m - self.tiefe_von_m


@dataclass
class Befund:
    ergebnis: Pruefung
    hinweise: list[str]


def pruefe_physik(s: Schicht, toleranz: float = 0.03) -> Befund:
    """Prüft, ob Dichte, Porosität und Wassergehalt zusammen möglich sind.

    `toleranz` fängt Messunsicherheit auf — ohne sie wäre fast jeder reale Datensatz
    'unmöglich', was die Prüfung nutzlos machen würde.
    """
    hinweise: list[str] = []

    if s.maechtigkeit_m <= 0:
        return Befund(Pruefung.WIDERSPRUCH,
                      [f"Tiefenangabe verdreht: {s.tiefe_von_m}–{s.tiefe_bis_m} m"])

    bekannt = [s.trockendichte_kg_m3, s.porositaet, s.wassergehalt_vol]
    if sum(x is not None for x in bekannt) < 2:
        return Befund(Pruefung.UNVOLLSTAENDIG,
                      ["mindestens zwei von Trockendichte, Porosität, "
                       "Wassergehalt werden gebraucht"])

    # 1. Wasser kann nicht mehr Raum einnehmen als Poren da sind.
    if s.porositaet is not None and s.wassergehalt_vol is not None:
        if s.wassergehalt_vol > s.porositaet + toleranz:
            hinweise.append(
                f"Wassergehalt {s.wassergehalt_vol:.3f} übersteigt Porosität "
                f"{s.porositaet:.3f} — im Boden ist kein Platz für dieses Wasser")

    # 2. Trockendichte und Porosität müssen über die Korndichte zusammenpassen:
    #    rho_d = rho_korn * (1 - n)
    if s.trockendichte_kg_m3 is not None and s.porositaet is not None:
        erwartet = KORNDICHTE * (1.0 - s.porositaet)
        abw = abs(erwartet - s.trockendichte_kg_m3) / KORNDICHTE
        if abw > toleranz * 2:
            hinweise.append(
                f"Trockendichte {s.trockendichte_kg_m3:.0f} kg/m³ passt nicht zur "
                f"Porosität {s.porositaet:.3f} (erwartet rund {erwartet:.0f} kg/m³ "
                f"bei Korndichte {KORNDICHTE:.0f})")

    # 3. Anteile können nicht ausserhalb von 0..1 liegen.
    for name, wert in (("Porosität", s.porositaet),
                       ("Wassergehalt", s.wassergehalt_vol)):
        if wert is not None and not (0.0 <= wert <= 1.0):
            hinweise.append(f"{name} {wert} liegt ausserhalb von 0 bis 1")

    if hinweise:
        return Befund(Pruefung.WIDERSPRUCH, hinweise)
    return Befund(Pruefung.OK, ["Dichte, Porosität und Wassergehalt passen zusammen"])


def waermeleitfaehigkeit(s: Schicht) -> tuple[float, float]:
    """Schätzt die Wärmeleitfähigkeit (W/mK) samt Unsicherheit.

    Vereinfachtes geometrisches Mischungsmodell über Korn, Wasser und Luft. Der
    zurückgegebene Unsicherheitsbereich ist der Punkt: ein nackter Wert verschweigt,
    wie gut er ist.
    """
    if s.porositaet is None or s.wassergehalt_vol is None:
        raise ValueError("Porosität und Wassergehalt werden gebraucht")

    l_korn, l_wasser, l_luft = 3.0, 0.6, 0.025
    n, theta = s.porositaet, s.wassergehalt_vol
    luft = max(0.0, n - theta)
    korn = 1.0 - n

    lam = (l_korn ** korn) * (l_wasser ** theta) * (l_luft ** luft)
    # Die RELATIVE Unsicherheit wächst mit dem Luftanteil: trockene Böden streuen
    # stärker um ihren Schätzwert. Absolut bleibt die Spanne kleiner, weil trockene
    # Böden ohnehin schlechter leiten — deshalb wird der relative Anteil mitgegeben.
    rel = 0.10 + 0.40 * luft
    return lam, lam * rel


def schuetze_standort(lat: float, lon: float, epsilon: float,
                      rng: random.Random) -> tuple[float, float]:
    """Planar-Laplace: verschiebt einen Punkt so, dass er nicht rückrechenbar ist.

    `epsilon` ist das Datenschutzbudget — klein = starker Schutz, große Verschiebung.
    Die veröffentlichende Stelle setzt und dokumentiert es; es ist kein fester Wert.
    """
    if epsilon <= 0:
        raise ValueError("epsilon muss grösser als 0 sein")

    theta = rng.uniform(0, 2 * math.pi)
    p = rng.random()
    # Inverse der Laplace-Radialverteilung über die Lambert-W-Funktion,
    # hier über eine Iteration angenähert (reine Standardbibliothek).
    r = -(1.0 / epsilon) * (_lambert_w((p - 1.0) / math.e) + 1.0)

    d_lat = (r * math.cos(theta)) / 111_320.0
    d_lon = (r * math.sin(theta)) / (111_320.0 * math.cos(math.radians(lat)))
    return lat + d_lat, lon + d_lon


def _lambert_w(x: float, schritte: int = 60) -> float:
    """W(x) für x >= -1/e über Newton-Iteration."""
    if x < -1.0 / math.e:
        raise ValueError("ausserhalb des Definitionsbereichs")
    w = 0.0 if x > -0.2 else -0.9
    for _ in range(schritte):
        ew = math.exp(w)
        f = w * ew - x
        if abs(f) < 1e-14:
            break
        w -= f / (ew * (1.0 + w)) if (1.0 + w) != 0 else f
    return w


def vorfuehrung() -> int:
    print("1) Physikalische Plausibilitätsprüfung")
    print()
    faelle = [
        ("Sand, plausibel",
         Schicht(0.0, 1.5, trockendichte_kg_m3=1590.0, porositaet=0.40,
                 wassergehalt_vol=0.18, bodenart="Sand")),
        ("Wassergehalt grösser als Porenraum",
         Schicht(1.5, 3.0, trockendichte_kg_m3=1590.0, porositaet=0.40,
                 wassergehalt_vol=0.55, bodenart="Sand")),
        ("Dichte passt nicht zur Porosität",
         Schicht(3.0, 4.0, trockendichte_kg_m3=1100.0, porositaet=0.40,
                 wassergehalt_vol=0.20, bodenart="Ton")),
        ("Nur ein Messwert",
         Schicht(4.0, 5.0, porositaet=0.35)),
    ]
    for titel, s in faelle:
        b = pruefe_physik(s)
        print(f"  {titel}")
        print(f"    -> {b.ergebnis.value}")
        for h in b.hinweise:
            print(f"       {h}")
    print()
    print("  Jeder Einzelwert liegt im üblichen Rahmen. Ein Wertebereichsprüfer")
    print("  hätte alle vier durchgelassen.")
    print()

    print("2) Wärmeleitfähigkeit mit Unsicherheit")
    print()
    for titel, s in (("feuchter Sand", faelle[0][1]),
                     ("trockener Sand",
                      Schicht(0, 1, porositaet=0.40, wassergehalt_vol=0.02))):
        lam, u = waermeleitfaehigkeit(s)
        print(f"  {titel:16s} {lam:.2f} ± {u:.2f} W/mK  ({100 * u / lam:.0f} % relativ)")
    print()
    print("  Der trockene Boden streut relativ deutlich stärker. Diese Spanne steht")
    print("  im Ergebnis, statt im Kleingedruckten — wer mit dem Wert rechnet, soll")
    print("  sehen, wie belastbar er ist.")
    print()

    print("3) Standortschutz (Planar-Laplace)")
    print()
    rng = random.Random(20261014)
    lat, lon = 49.5897, 11.0120          # Erlangen
    for eps in (0.01, 0.001):
        verschiebungen = []
        for _ in range(500):
            nl, no = schuetze_standort(lat, lon, eps, rng)
            dx = (no - lon) * 111_320.0 * math.cos(math.radians(lat))
            dy = (nl - lat) * 111_320.0
            verschiebungen.append(math.hypot(dx, dy))
        mittel = sum(verschiebungen) / len(verschiebungen)
        mitte_lat = lat + sum(
            (schuetze_standort(lat, lon, eps, rng)[0] - lat) for _ in range(500)) / 500
        print(f"  epsilon = {eps:<6} mittlere Verschiebung {mittel:7.0f} m   "
              f"Schwerpunkt bleibt bei {mitte_lat:.4f} (Original {lat:.4f})")
    print()
    print("  Kleineres epsilon verschiebt weiter. Der Schwerpunkt über viele Punkte")
    print("  bleibt erhalten — die Wärmekarte stimmt, das Grundstück ist geschützt.")
    return 0


def selftest() -> int:
    ok = True

    def expect(c: bool, m: str) -> None:
        nonlocal ok
        if not c:
            ok = False
            print(f"FAIL: {m}", file=sys.stderr)

    gut = Schicht(0, 1.5, trockendichte_kg_m3=1590.0, porositaet=0.40,
                  wassergehalt_vol=0.18)
    expect(pruefe_physik(gut).ergebnis is Pruefung.OK, "plausible Schicht besteht")

    nass = Schicht(0, 1, trockendichte_kg_m3=1590.0, porositaet=0.40,
                   wassergehalt_vol=0.55)
    b = pruefe_physik(nass)
    expect(b.ergebnis is Pruefung.WIDERSPRUCH, "Wasser > Poren fällt auf")
    expect(any("kein Platz" in h for h in b.hinweise), "und wird begründet")

    schief = Schicht(0, 1, trockendichte_kg_m3=1100.0, porositaet=0.40,
                     wassergehalt_vol=0.20)
    expect(pruefe_physik(schief).ergebnis is Pruefung.WIDERSPRUCH,
           "Dichte/Porosität-Widerspruch fällt auf")

    expect(pruefe_physik(Schicht(0, 1, porositaet=0.35)).ergebnis
           is Pruefung.UNVOLLSTAENDIG, "ein Messwert reicht nicht")
    expect(pruefe_physik(Schicht(2.0, 1.0, porositaet=0.3,
                                 wassergehalt_vol=0.1)).ergebnis
           is Pruefung.WIDERSPRUCH, "verdrehte Tiefen fallen auf")
    expect(pruefe_physik(Schicht(0, 1, porositaet=1.4,
                                 wassergehalt_vol=0.1)).ergebnis
           is Pruefung.WIDERSPRUCH, "Anteil > 1 fällt auf")

    # Toleranz: eine knapp daneben liegende Messung darf nicht als unmöglich gelten
    knapp = Schicht(0, 1, trockendichte_kg_m3=1590.0, porositaet=0.40,
                    wassergehalt_vol=0.42)
    expect(pruefe_physik(knapp).ergebnis is Pruefung.OK,
           "Messunsicherheit wird toleriert")

    lam_feucht, u_feucht = waermeleitfaehigkeit(gut)
    lam_trocken, u_trocken = waermeleitfaehigkeit(
        Schicht(0, 1, porositaet=0.40, wassergehalt_vol=0.02))
    expect(lam_feucht > lam_trocken, "feuchter Boden leitet besser")
    expect(u_trocken / lam_trocken > u_feucht / lam_feucht,
           "trockener Boden ist relativ unsicherer")
    expect(0.1 < lam_feucht < 5.0, "Wert in physikalisch sinnvoller Groessenordnung")

    try:
        waermeleitfaehigkeit(Schicht(0, 1, porositaet=0.4))
        expect(False, "fehlender Wassergehalt muss auffallen")
    except ValueError:
        pass

    rng = random.Random(1)
    lat, lon = 49.5897, 11.0120
    weit = [schuetze_standort(lat, lon, 0.001, rng) for _ in range(300)]
    eng = [schuetze_standort(lat, lon, 0.01, rng) for _ in range(300)]

    def mittlere_dist(punkte):
        return sum(math.hypot((b - lon) * 111_320.0 * math.cos(math.radians(lat)),
                              (a - lat) * 111_320.0) for a, b in punkte) / len(punkte)

    expect(mittlere_dist(weit) > mittlere_dist(eng),
           "kleineres epsilon verschiebt weiter")
    expect(all((a, b) != (lat, lon) for a, b in eng), "jeder Punkt wird verschoben")
    schwerpunkt = sum(a for a, _ in eng) / len(eng)
    expect(abs(schwerpunkt - lat) < 0.02, "Schwerpunkt bleibt nahe am Original")

    try:
        schuetze_standort(lat, lon, 0.0, rng)
        expect(False, "epsilon 0 muss auffallen")
    except ValueError:
        pass

    print("selftest: PASS" if ok else "selftest: FAIL", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else vorfuehrung())

# CryoSoil-Sync

**Bodendaten vereinheitlichen, physikalisch prüfen, datenschutzkonform teilen.**

Das Wärmeplanungsgesetz verpflichtet jede deutsche Kommune, einen Plan für ihre künftige
Wärmeversorgung aufzustellen. Erdwärme ist eine der wenigen Quellen, die vor Ort verfügbar
ist — wie gut sie taugt, hängt vom Untergrund ab. Diese Daten gibt es: aus Bohrungen,
Baugrundgutachten und Laboranalysen, gesammelt über Jahrzehnte. Sie sind nur nicht
benutzbar, weil sechzehn Landesämter sie in verschiedenen Formaten und Schlüsseln halten,
teils als eingescanntes Schichtenverzeichnis.

> **Stand: Prinzipbeweis.** Dieses Repository zeigt die zwei Teile, die es als Bibliothek
> bisher nicht gibt. Der produktive Teil — Leser für KA5, KA6 und SEP3, `GeoParquet`- und
> `Polars`-Unterbau, Einheiten über `pint`/UCUM, Exporte für `CryoGrid`, `OpenGeoSys` und
> QGIS, Wetterzeitreihen über [Bright Sky](https://brightsky.dev/) — ist Gegenstand der
> Bewerbung beim Prototype Fund, Jahrgang 03.

## Ausprobieren

Keine Abhängigkeiten, Python 3.11 genügt:

```
python3 cryosoil_sync.py            # Vorführung
python3 cryosoil_sync.py --selftest # Tests
```

## Was die Vorführung zeigt

Ausgabe eines echten Durchlaufs (14.10.2026):

```
1) Physikalische Plausibilitätsprüfung

  Sand, plausibel
    -> plausibel
       Dichte, Porosität und Wassergehalt passen zusammen
  Wassergehalt grösser als Porenraum
    -> physikalisch unmöglich
       Wassergehalt 0.550 übersteigt Porosität 0.400 — im Boden ist kein Platz für dieses Wasser
  Dichte passt nicht zur Porosität
    -> physikalisch unmöglich
       Trockendichte 1100 kg/m³ passt nicht zur Porosität 0.400 (erwartet rund 1590 kg/m³ bei Korndichte 2650)
  Nur ein Messwert
    -> nicht prüfbar
       mindestens zwei von Trockendichte, Porosität, Wassergehalt werden gebraucht

2) Wärmeleitfähigkeit mit Unsicherheit

  feuchter Sand    0.78 ± 0.15 W/mK  (19 % relativ)
  trockener Sand   0.47 ± 0.12 W/mK  (25 % relativ)

3) Standortschutz (Planar-Laplace)

  epsilon = 0.01   mittlere Verschiebung      70 m   Schwerpunkt bleibt bei 49.5897 (Original 49.5897)
  epsilon = 0.001  mittlere Verschiebung     711 m   Schwerpunkt bleibt bei 49.5895 (Original 49.5897)
```

### Warum ein Wertebereichsprüfer das nicht findet

Bei allen vier Schichten liegt **jeder Einzelwert im üblichen Rahmen**. Eine Porosität von
0,40 ist normal, ein Wassergehalt von 0,55 ist normal, eine Trockendichte von
1100 kg/m³ ist normal. Unmöglich sind erst die **Kombinationen**: Wasser kann nicht mehr
Raum einnehmen, als Poren vorhanden sind, und Trockendichte und Porosität müssen über die
Korndichte zusammenpassen (ρ_d = ρ_Korn · (1 − n)).

`Pandera` und `Great Expectations` prüfen Spalten, nicht Physik. Sie hätten alle vier
Datensätze durchgelassen — und der Fehler wäre unbemerkt in die Wärmeplanung gewandert,
weil das Ergebnis plausibel aussieht.

Eine Toleranz von 3 % fängt Messunsicherheit auf; ohne sie wäre fast jeder reale Datensatz
„unmöglich" und die Prüfung nutzlos.

### Warum die Unsicherheit mitgegeben wird

Trockene Böden streuen stärker um ihren Schätzwert als feuchte. Wer mit einer
Wärmeleitfähigkeit weiterrechnet, muss wissen, wie belastbar sie ist — ein nackter Wert
verschweigt das. Das Schätzverfahren folgt Bertermann, Rammler, Wernsdorfer, Hagenauer
(2024), *A Practicable Guideline for Predicting the Thermal Conductivity of Unconsolidated
Soils*, **Soil Systems 8(2)**; hier als vereinfachtes Mischungsmodell.

### Warum der Standortschutz das Veröffentlichen erst möglich macht

Viele Bohrprofile liegen auf privaten Grundstücken. Weil eine Punktkoordinate das
Grundstück identifiziert, veröffentlichen Behörden sie vorsichtshalber nicht — so bleiben
Daten unter Verschluss, die mit öffentlichem Geld erhoben wurden.

Planar-Laplace verschiebt jeden Punkt mit kontrolliertem Rauschen. Bei ε = 0,01 sind das im
Mittel 70 Meter, bei ε = 0,001 rund 711 Meter. Der **Schwerpunkt über viele Punkte bleibt
erhalten** (49,5897 gegen 49,5897) — die Wärmekarte über die Fläche stimmt weiter, das
einzelne Grundstück ist nicht mehr bestimmbar.

ε ist dabei kein fester Wert, sondern ein **Parameter, den die veröffentlichende Stelle
setzt und dokumentiert**. Welches Budget juristisch vertretbar ist, ist genau die Frage,
die in der Second Stage mit zwei Geologischen Diensten geklärt werden soll.

## Herkunft

Ich arbeite seit 2021 als wissenschaftlicher Mitarbeiter am GeoZentrum Nordbayern der FAU
Erlangen-Nürnberg zu oberflächennaher Geothermie (Projekte KNW-Opt und META-Studie) und
habe die Hälfte dieser Zeit damit verbracht, Bodendaten lesbar zu machen, statt mit ihnen
zu rechnen.

## Lizenz

MIT — siehe [LICENSE](LICENSE).

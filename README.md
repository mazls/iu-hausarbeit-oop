# 🏭 Maschinen-Signale – OOP-Hausarbeit

Hausarbeit im Modul **Objektorientierte Programmierung (IU)**: Eine Werkzeugmaschine meldet ihren Zustand zyklisch über MQTT, und das Programm wertet die Signale objektorientiert aus.

```
werk/maschine/SN-4711/temperatur   ->  "42.7"
werk/maschine/SN-4711/strom        ->  "8.4"
werk/maschine/SN-4711/position     ->  "125.40;88.10;12.75"
werk/maschine/SN-4711/status       ->  "RUNNING"
```

Jede Signalart hat eine eigene Struktur: Temperatur ist eine Zahl mit Grenzwerten, Position hat drei Komponenten, und Status ist gar keine Zahl. Diese Unterschiede bildet eine Vererbungshierarchie ab. Die abstrakte Basisklasse `Signal` legt fest, was alle gemeinsam haben: empfangen, auswerten, prüfen, darstellen.

## Gezeigte OOP-Konzepte

| Konzept | Umsetzung |
|---|---|
| Abstraktion | `Signal` als abstrakte Basisklasse (`ABC`) |
| Vererbung | zweistufige Hierarchie, z. B. `Signal → NumericSignal → TemperatureSignal` |
| Method Overriding | `parse()` ist in jeder Unterklasse anders |
| Erweitern über `super()` | `TemperatureSignal.is_plausible()` |
| Polymorphismus | `Machine` behandelt alle Signalarten gleich |
| Kapselung | `_value`, `_timestamp`, `@property` |
| Komposition | eine `Machine` *hat* Signale |
| Strategie-Muster | `ValueConverter` (Identity, Kelvin, lineare Skalierung) |
| Klassenattribute | `unit`, `_instance_count` |
| Magic Methods | `__str__`, `__repr__`, `__eq__` |
| Eigene Exceptions | `SignalError`, `DecodingError` |

## Starten

Es gibt keine externen Abhängigkeiten. Python ab 3.10 genügt.

```bash
python3 Hausarbeit_OOP.py
```

Der MQTT-Eingang ist simuliert, damit der Fokus auf der Klassenstruktur liegt.

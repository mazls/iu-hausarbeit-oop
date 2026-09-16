"""
Szenario
--------
Eine Werkzeugmaschine meldet ihren Zustand zyklisch über MQTT. Die
Nachrichten laufen unter einem Topic-Muster ein, das die Seriennummer der
Maschine enthält:

    werk/maschine/<seriennummer>/<signalname>

Beispiele:
    werk/maschine/SN-4711/temperatur   ->  "42.7"
    werk/maschine/SN-4711/strom        ->  "8.4"
    werk/maschine/SN-4711/position     ->  "125.40;88.10;12.75"
    werk/maschine/SN-4711/status       ->  "RUNNING"

Die Signale unterscheiden sich strukturell erheblich: Ein Temperaturwert ist
eine einzelne Gleitkommazahl mit Grenzwerten, eine Position besteht aus drei
Komponenten, ein Status ist überhaupt keine Zahl. Genau diese Unterschiede
werden über eine Vererbungshierarchie abgebildet, während die Gemeinsamkeit, 
jedes Signal wird empfangen, ausgewertet, geprüft und dargestellt, in
einer abstrakten Basisklasse festgehalten wird.

Demonstrierte OOP-Konzepte
--------------------------
    Abstraktion .......... Signal als abstrakte Basisklasse
    Vererbung ............ zweistufige Hierarchie mit vier Blattklassen
    Method Overriding .... parse() in jeder Unterklasse verschieden
    Erweitern via super()  TemperatureSignal.is_plausible()
    Polymorphismus ....... Machine behandelt alle Signalarten gleich
    Kapselung ............ _value, _timestamp, @property
    Komposition .......... Machine *hat* Signale
    Klassenattribute ..... unit, _instance_count
    Magic Methods ........ __str__, __repr__, __eq__

Das Programm läuft ohne externe Abhängigkeiten; der Nachrichteneingang ist
simuliert, damit der Fokus auf der Struktur liegt.
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from datetime import datetime, timezone


class SignalError(Exception):
    """Oberklasse aller Fehler bei der Signalverarbeitung."""


class DecodingError(SignalError):
    """Die empfangenen Nutzdaten waren nicht interpretierbar."""


# ===========================================================================
# 1) Abstraktion: die gemeinsame Basisklasse aller Signale
# ===========================================================================

class Signal(ABC):
    """Abstrakte Basisklasse aller Maschinensignale.

    Sie legt fest, was jedes Signal können muss: Nutzdaten auswerten
    (parse) und sich selbst auf Plausibilität prüfen. parse() ist
    abstrakt, weil sich die Nutzdatenformate grundlegend unterscheiden;
    is_plausible() und update() besitzen dagegen eine sinnvolle
    Standardimplementierung.

    Ein direkter Instanziierungsversuch löst einen TypeError aus: Die
    Klasse beschreibt ein Konzept, kein konkretes Signal.
    """

    unit: str = ""              # Klassenattribut, je Unterklasse ueberschrieben
    _instance_count: int = 0

    def __init__(self, name: str) -> None:
        self.name = name                        # Instanzattribut
        self._value: object = None              # gekapselter Zustand
        self._timestamp: datetime | None = None
        self._update_count = 0
        Signal._instance_count += 1

    # -- gekapselter Zugriff ------------------------------------------------

    @property
    def value(self) -> object:
        """Nur lesender Zugriff.

        Ein Setter fehlt bewusst: Der Wert darf ausschliesslich über
        update() gesetzt werden, weil dort zugleich Zeitstempel und
        Zähler gepflegt werden. Wäre das Attribut öffentlich, könnte
        ein Wert ohne zugehörigen Zeitstempel entstehen.
        """
        return self._value

    @property
    def timestamp(self) -> datetime | None:
        return self._timestamp

    @property
    def has_value(self) -> bool:
        return self._value is not None

    # -- abstrakter Vertrag -------------------------------------------------

    @abstractmethod
    def parse(self, payload: str) -> object:
        """Wandelt die empfangenen Nutzdaten in einen Wert um."""

    # -- Standardverhalten, ueberschreibbar ---------------------------------

    def is_plausible(self) -> bool:
        """Prüft, ob der aktuelle Wert sinnvoll ist."""
        return self.has_value

    def supports_averaging(self) -> bool:
        """Lässt sich über diesem Signal ein Mittelwert bilden?

        Die Standardannahme lautet: ja. Signalarten ohne diese Eigenschaft
        überschreiben die Methode, vergleichbar mit einem Vogel, der die
        von seiner Oberklasse zugesagte Faehigkeit zu fliegen nicht besitzt.
        """
        return True

    def update(self, payload: str) -> None:
        """Vorlagenmethode: legt den Ablauf fest, nicht die Auswertung.

        Der Ablauf, auswerten, speichern, Zeit stempeln, ist für alle
        Signale gleich. Welcher Code beim Auswerten läuft, entscheidet
        erst die jeweilige Unterklasse.
        """
        self._value = self.parse(payload)
        self._timestamp = datetime.now(timezone.utc)
        self._update_count += 1

    def __str__(self) -> str:
        if not self.has_value:
            return f"{self.name}: <kein Wert>"
        marker = "" if self.is_plausible() else "  [unplausibel]"
        return f"{self.name:<12} {self._value} {self.unit}{marker}"

    def __repr__(self) -> str:
        return f"{type(self).__name__}(name={self.name!r})"


# ===========================================================================
# 2) Zwischenstufe: numerische Signale mit Grenzwerten
# ===========================================================================

class NumericSignal(Signal):
    """Gemeinsame Oberklasse aller skalaren Messgrößen.

    Diese Zwischenstufe existiert, weil Temperatur und Strom sich zwar im
    Wertebereich und in der Einheit unterscheiden, in der Auswertung der
    Nutzdaten und der Grenzwertprüfung aber identisch sind. Ohne sie
    müsste derselbe Code in beiden Unterklassen stehen.
    """

    def __init__(self, name: str, minimum: float, maximum: float) -> None:
        super().__init__(name)
        self.minimum = minimum
        self.maximum = maximum

    def parse(self, payload: str) -> float:
        try:
            return float(payload.replace(",", "."))
        except ValueError as fehler:
            raise DecodingError(
                f"{self.name}: '{payload}' ist keine Zahl"
            ) from fehler

    def is_plausible(self) -> bool:
        if not self.has_value:
            return False
        return self.minimum <= self._value <= self.maximum


class TemperatureSignal(NumericSignal):
    """Temperatur in Grad Celsius.

    Überschreibt is_plausible() nicht vollständig, sondern *erweitert*
    die Prüfung der Oberklasse über super(): Zusätzlich zum Wertebereich
    wird ein unrealistisch schneller Anstieg erkannt, wie er auf einen
    Sensordefekt hindeutet.
    """

    unit = "degC"
    MAX_GRADIENT = 15.0     # Klassenattribut: zulässige Aenderung je Zyklus

    def __init__(self, name: str = "Temperatur",
                 minimum: float = -20.0, maximum: float = 120.0) -> None:
        super().__init__(name, minimum, maximum)
        self._previous: float | None = None

    def update(self, payload: str) -> None:
        self._previous = self._value if isinstance(self._value, float) else None
        super().update(payload)

    def is_plausible(self) -> bool:
        if not super().is_plausible():       # Basisprüfung übernehmen
            return False
        if self._previous is None:
            return True
        return abs(self._value - self._previous) <= self.MAX_GRADIENT


class KelvinTemperatureSignal(TemperatureSignal):
    """Temperatur, die in Kelvin gesendet, aber in Grad Celsius geführt wird.

    Ein Musterfall für das *erweiternde* Überschreiben: parse() ruft
    zunächst die geerbte Implementierung auf, die die Zeichenkette in eine
    Gleitkommazahl wandelt, und rechnet deren Ergebnis anschliessend um. Der
    eigentliche Zugewinn besteht aus einer einzigen Zeile; alles Übrige
    wird übernommen.

    Grenzwerte, Gradientenprüfung, Darstellung und Einheit bleiben
    unverändert gültig, weil die Umrechnung an der frühestmoeglichen
    Stelle stattfindet. Alle nachgelagerten Bestandteile arbeiten weiterhin
    ausschliesslich mit Grad Celsius.
    """

    source_unit = "K"           # Signal Einheit
    ABSOLUTE_ZERO = -273.15     # Nullpunkt in Grad Celsius

    def parse(self, payload: str) -> float:
        kelvin = super().parse(payload)         # geerbtes Verhalten nutzen
        if kelvin < 0:
            raise DecodingError(
                f"{self.name}: {kelvin} K liegt unter dem absoluten Nullpunkt"
            )
        return round(kelvin + self.ABSOLUTE_ZERO, 2)


class RawTemperatureSignal(TemperatureSignal):
    """Temperatur, die als roher Zählwert einer Analogbaugruppe eintrifft.

    Analog-Eingangskarten liefern keine physikalischen Größen, sondern
    ganzzahlige Digits. Der Messbereich der Karte wird linear auf den
    Messbereich der Größe abgebildet.

    Grenzwerte, Gradientenpruefung und Darstellung werden
    unverändert geerbt.
    Zielgrenzen sind identisch mit dem physikalischen Messbereich.
    """

    RAW_MIN = 0
    RAW_MAX = 27648         # typischer Endwert einer Analogbaugruppe

    def parse(self, payload: str) -> float:
        digits = super().parse(payload)         # geerbte Zahlenwandlung
        if not self.RAW_MIN <= digits <= self.RAW_MAX:
            raise DecodingError(
                f"{self.name}: Rohwert {digits:.0f} ausserhalb "
                f"{self.RAW_MIN}..{self.RAW_MAX}"
            )
        spanne = (self.maximum - self.minimum) / (self.RAW_MAX - self.RAW_MIN)
        return round(self.minimum + (digits - self.RAW_MIN) * spanne, 2)


class CurrentSignal(NumericSignal):
    """Stromaufnahme in Ampere."""

    unit = "A"

    def __init__(self, name: str = "Strom",
                 minimum: float = 0.0, maximum: float = 32.0) -> None:
        super().__init__(name, minimum, maximum)


# ===========================================================================
# 3) Positionssignal: drei Komponenten statt einer
# ===========================================================================

class RawCurrentSignal(CurrentSignal):
    """Stromaufnahme als roher Zählwert.

    Diese Klasse ist bewusst aufgenommen worden, um ein Problem sichtbar zu
    machen: Ihr parse() ist mit dem von RawTemperatureSignal bis auf die
    Oberklasse identisch. Die Skalierung ist eine Eigenschaft des Sensors,
    nicht der Messgröße, sie über die Vererbungshierarchie abzubilden,
    führt zu doppeltem Code.

    Kämen weitere Einheiten hinzu (Fahrenheit, Milliampere) und weitere
    Messgrößen (Druck, Drehzahl), wäre fuer jede Kombination eine eigene
    Klasse nötig. Der folgende Abschnitt zeigt die Alternative.
    """

    RAW_MIN = 0
    RAW_MAX = 27648

    def parse(self, payload: str) -> float:
        digits = super().parse(payload)
        if not self.RAW_MIN <= digits <= self.RAW_MAX:
            raise DecodingError(
                f"{self.name}: Rohwert {digits:.0f} ausserhalb "
                f"{self.RAW_MIN}..{self.RAW_MAX}"
            )
        spanne = (self.maximum - self.minimum) / (self.RAW_MAX - self.RAW_MIN)
        return round(self.minimum + (digits - self.RAW_MIN) * spanne, 2)


# ---------------------------------------------------------------------------
# Alternative: Umrechnung als eigenstaendiges, austauschbares Objekt
# ---------------------------------------------------------------------------

class ValueConverter(ABC):
    """Rechnet einen empfangenen Zahlenwert in die Zielgröße um."""

    @abstractmethod
    def convert(self, raw: float) -> float:
        ...

    def __str__(self) -> str:
        return type(self).__name__


class IdentityConverter(ValueConverter):
    """Keine Umrechnung, der Wert kommt bereits in der Zieleinheit an."""

    def convert(self, raw: float) -> float:
        return raw


class KelvinConverter(ValueConverter):
    """Kelvin nach Grad Celsius."""

    ABSOLUTE_ZERO = -273.15

    def convert(self, raw: float) -> float:
        if raw < 0:
            raise DecodingError(f"{raw} K liegt unter dem absoluten Nullpunkt")
        return raw + self.ABSOLUTE_ZERO


class LinearScaling(ValueConverter):
    """Lineare Abbildung eines Rohwertbereichs auf einen Zielbereich."""

    def __init__(self, raw_min: float, raw_max: float,
                 out_min: float, out_max: float) -> None:
        self.raw_min, self.raw_max = raw_min, raw_max
        self.out_min, self.out_max = out_min, out_max

    def convert(self, raw: float) -> float:
        if not self.raw_min <= raw <= self.raw_max:
            raise DecodingError(
                f"Rohwert {raw:.0f} ausserhalb {self.raw_min}..{self.raw_max}"
            )
        spanne = (self.out_max - self.out_min) / (self.raw_max - self.raw_min)
        return self.out_min + (raw - self.raw_min) * spanne


class ConvertingSignal(NumericSignal):
    """Numerisches Signal, dessen Umrechnung von aussen vorgegeben wird.

    Diese eine Klasse ersetzt RawTemperatureSignal, RawCurrentSignal und
    KelvinTemperatureSignal zusammen: Was dort über je eine eigene
    Unterklasse gelöst wurde, ist hier ein austauschbares Objekt.

    Die Einheit wird als Instanzattribut gesetzt und überdeckt damit das
    gleichnamige Klassenattribut der Basisklasse, ein Signal kann seine
    Einheit nun zur Laufzeit erhalten statt zur Übersetzungszeit.
    """

    def __init__(self, name: str, minimum: float, maximum: float,
                 unit: str = "", converter: ValueConverter | None = None) -> None:
        super().__init__(name, minimum, maximum)
        self.unit = unit                                # ueberdeckt Klassenattribut
        self.converter = converter or IdentityConverter()   # Komposition

    def parse(self, payload: str) -> float:
        rohwert = super().parse(payload)                # geerbte Zahlenwandlung
        return round(self.converter.convert(rohwert), 2)


class PositionSignal(Signal):
    """Achsposition als Tripel aus X-, Y- und Z-Koordinate.

    Überschreibt parse() vollständig, weil die Nutzdaten aus drei durch
    Semikolon getrennten Werten bestehen. Zeigt zugleich, dass der Typ des
    gekapselten Wertes je Unterklasse ein anderer sein darf, hier ein
    Tupel statt einer Zahl.
    """

    unit = "mm"
    WORKSPACE = {"x": (0.0, 800.0), "y": (0.0, 600.0), "z": (0.0, 400.0)}

    def __init__(self, name: str = "Position") -> None:
        super().__init__(name)

    def parse(self, payload: str) -> tuple[float, float, float]:
        teile = payload.split(";")
        if len(teile) != 3:
            raise DecodingError(
                f"{self.name}: drei Komponenten erwartet, {len(teile)} erhalten"
            )
        try:
            x, y, z = (float(t.replace(",", ".")) for t in teile)
        except ValueError as fehler:
            raise DecodingError(
                f"{self.name}: '{payload}' enthält keine gültigen Zahlen"
            ) from fehler
        return (x, y, z)

    def is_plausible(self) -> bool:
        if not self.has_value:
            return False
        return all(
            unten <= wert <= oben
            for wert, (unten, oben) in zip(self._value, self.WORKSPACE.values())
        )

    def supports_averaging(self) -> bool:
        # Ein Mittelwert ueber Positionen ist fachlich nicht sinnvoll.
        return False

    def __str__(self) -> str:
        if not self.has_value:
            return f"{self.name}: <kein Wert>"
        x, y, z = self._value
        marker = "" if self.is_plausible() else "  [ausserhalb Arbeitsraum]"
        return f"{self.name:<12} X={x:.2f} Y={y:.2f} Z={z:.2f} {self.unit}{marker}"


# ===========================================================================
# 4) Statussignal: nicht numerisch
# ===========================================================================

class StateSignal(Signal):
    """Betriebszustand der Maschine.

    Überschreibt sowohl parse() als auch is_plausible() vollständig, weil
    die Prüfung hier keine Grenzwertfrage ist, sondern eine Frage der
    Zugehoerigkeit zu einer festen Menge zulässiger Zustände.
    """

    unit = ""
    ALLOWED = ("IDLE", "RUNNING", "PAUSED", "ERROR")

    def __init__(self, name: str = "Status") -> None:
        super().__init__(name)

    def parse(self, payload: str) -> str:
        zustand = payload.strip().upper()
        if zustand not in self.ALLOWED:
            raise DecodingError(f"{self.name}: unbekannter Zustand '{payload}'")
        return zustand

    def is_plausible(self) -> bool:
        return self.has_value and self._value != "ERROR"

    def supports_averaging(self) -> bool:
        # Zwischen RUNNING und ERROR gibt es keinen Mittelwert.
        return False


# ===========================================================================
# 5) Komposition: die Maschine als Behaelter ihrer Signale
# ===========================================================================

class Machine:
    """Eine Maschine, identifiziert über ihre Seriennummer.

    Die Maschine *hat* Signale, sie *ist* kein Signal, deshalb Komposition
    statt Vererbung. Sie kennt ausschliesslich den Typ Signal und muss nicht
    wissen, ob ein einzelnes davon eine Zahl, ein Tripel oder eine
    Zeichenkette verwaltet. Ein fünftes Signal lässt sich ergänzen, ohne
    diese Klasse anzufassen.
    """

    def __init__(self, serial: str) -> None:
        self.serial = serial
        self._signals: dict[str, Signal] = {}

    def add_signal(self, key: str, signal: Signal) -> None:
        if not isinstance(signal, Signal):
            raise TypeError("Nur Objekte vom Typ Signal sind zulässig.")
        self._signals[key] = signal

    def handle_message(self, topic: str, payload: str) -> None:
        """Ordnet eine eingehende Nachricht dem passenden Signal zu."""
        schluessel = topic.rsplit("/", 1)[-1]
        signal = self._signals.get(schluessel)

        if signal is None:
            print(f"    kein Signal für '{schluessel}' registriert")
            return

        try:
            signal.update(payload)              # polymorpher Aufruf
        except SignalError as fehler:
            print(f"    verworfen: {fehler}")

    def snapshot(self) -> None:
        print(f"\n  Maschine {self.serial}")
        for signal in self._signals.values():   # identischer Aufruf,
            print(f"    {signal}")              # unterschiedliches Verhalten

    def problems(self) -> list[Signal]:
        return [s for s in self._signals.values()
                if s.has_value and not s.is_plausible()]

    def __eq__(self, other: object) -> bool:
        """Zwei Maschinen sind gleich, wenn ihre Seriennummer gleich ist.

        Die Identitaet hängt nicht von den aktuellen Messwerten ab.
        """
        if not isinstance(other, Machine):
            return NotImplemented
        return self.serial == other.serial

    def __hash__(self) -> int:
        return hash(self.serial)

    def __repr__(self) -> str:
        return f"Machine(serial={self.serial!r})"


# ===========================================================================
# 6) MQTT-Anbindung
# ===========================================================================

class MqttClient:
    """Nimmt Nachrichten entgegen und leitet sie an die Maschine weiter.

    Der Client kennt weder Signalarten noch Wertebereiche. Seine einzige
    Aufgabe ist die Zustellung.
    """

    DEFAULT_PORT = 1883

    def __init__(self, host: str, machine: Machine,
                 port: int = DEFAULT_PORT) -> None:
        self.host = host
        self.port = port
        self.machine = machine
        self.base_topic = f"werk/maschine/{machine.serial}"
        self._connected = False
        self._received = 0

    @property
    def received(self) -> int:
        return self._received

    def connect(self) -> None:
        print(f"  verbinde mit {self.host}:{self.port}")
        print(f"  abonniert: {self.base_topic}/#")
        self._connected = True

    def on_message(self, topic: str, payload: str) -> None:
        """Rueckruf des Brokers."""
        if not self._connected:
            return
        self._received += 1
        print(f"    <- {topic} = {payload}")
        self.machine.handle_message(topic, payload)

    def simulate_cycle(self) -> None:
        """Ersetzt in diesem Beispiel den echten Broker."""
        self.on_message(f"{self.base_topic}/temperatur",
                        f"{random.uniform(38.0, 46.0):.1f}")
        self.on_message(f"{self.base_topic}/strom",
                        f"{random.uniform(6.0, 9.5):.2f}")
        self.on_message(f"{self.base_topic}/position",
                        ";".join(f"{random.uniform(0, 500):.2f}" for _ in range(3)))
        self.on_message(f"{self.base_topic}/status",
                        random.choice(["RUNNING", "RUNNING", "IDLE"]))

    def disconnect(self) -> None:
        self._connected = False
        print(f"\n  Verbindung getrennt ({self._received} Nachrichten empfangen)")


# ===========================================================================
# 7) Beispielablauf
# ===========================================================================

def main() -> None:
    random.seed(42)     # reproduzierbare Ausgabe für die Dokumentation

    print("=" * 68)
    print(" 1  Die abstrakte Basisklasse ist nicht instanziierbar")
    print("=" * 68)
    try:
        Signal("unzulaessig")
    except TypeError as fehler:
        print(f"  Erwarteter Fehler: {fehler}")

    print("\n" + "=" * 68)
    print(" 2  Aufbau der Maschine")
    print("=" * 68)

    maschine = Machine("SN-4711")
    maschine.add_signal("temperatur", TemperatureSignal())
    maschine.add_signal("strom", CurrentSignal())
    maschine.add_signal("position", PositionSignal())
    maschine.add_signal("status", StateSignal())

    for signal in maschine._signals.values():
        mittelbar = "ja" if signal.supports_averaging() else "nein"
        print(f"  {signal!r:<32} Einheit: {signal.unit or '-':<5} "
              f"mittelbar: {mittelbar}")

    client = MqttClient("broker.intern", maschine)
    print()
    client.connect()

    print("\n" + "=" * 68)
    print(" 3  Zwei Nachrichtenzyklen")
    print("=" * 68)

    for zyklus in (1, 2):
        print(f"\n  Zyklus {zyklus}:")
        client.simulate_cycle()
        maschine.snapshot()

    print("\n" + "=" * 68)
    print(" 4  Fehlerhafte Nachrichten")
    print("=" * 68)
    client.on_message(f"{client.base_topic}/temperatur", "n/a")
    client.on_message(f"{client.base_topic}/position", "10.0;20.0")
    client.on_message(f"{client.base_topic}/status", "BOOTING")
    client.on_message(f"{client.base_topic}/drehzahl", "1450")

    print("\n" + "=" * 68)
    print(" 5  Unplausible Werte")
    print("=" * 68)
    client.on_message(f"{client.base_topic}/temperatur", "95.0")
    client.on_message(f"{client.base_topic}/position", "950.00;88.10;12.75")
    client.on_message(f"{client.base_topic}/status", "ERROR")
    maschine.snapshot()

    print("\n  Auffaellige Signale:")
    for signal in maschine.problems():
        print(f"    {signal.name}")

    print("\n" + "=" * 68)
    print(" 6  Sensor mit abweichender Einheit")
    print("=" * 68)

    zweite = Machine("SN-4712")
    zweite.add_signal("temperatur", KelvinTemperatureSignal())
    zweite.add_signal("status", StateSignal())

    client2 = MqttClient("broker.intern", zweite)
    client2.connect()
    client2.on_message(f"{client2.base_topic}/temperatur", "316.25")
    client2.on_message(f"{client2.base_topic}/status", "RUNNING")
    zweite.snapshot()

    print("\n  Umrechnung bereits beim Auswerten:")
    print(f"    Einheit des Signal : {KelvinTemperatureSignal.source_unit}")
    print(f"    geführte Einheit       : {KelvinTemperatureSignal.unit}")
    print(f"    Grenzwerte unveraendert : "
          f"{zweite._signals['temperatur'].minimum} bis "
          f"{zweite._signals['temperatur'].maximum} "
          f"{KelvinTemperatureSignal.unit}")

    print("\n  Unmögliche Nutzdaten werden abgewiesen:")
    client2.on_message(f"{client2.base_topic}/temperatur", "-5.0")

    print("\n" + "=" * 68)
    print(" 7  Rohwerte einer Analogbaugruppe: Vererbung")
    print("=" * 68)

    dritte = Machine("SN-4713")
    dritte.add_signal("temperatur", RawTemperatureSignal())
    dritte.add_signal("strom", RawCurrentSignal())

    client3 = MqttClient("broker.intern", dritte)
    client3.connect()
    client3.on_message(f"{client3.base_topic}/temperatur", "13824")
    client3.on_message(f"{client3.base_topic}/strom", "6912")
    dritte.snapshot()

    print("\n  Rohwert ausserhalb des Bereichs:")
    client3.on_message(f"{client3.base_topic}/temperatur", "30000")

    print("\n" + "=" * 68)
    print(" 8  Dieselbe Aufgabe über Komposition")
    print("=" * 68)

    vierte = Machine("SN-4714")
    vierte.add_signal("temperatur", ConvertingSignal(
        "Temperatur", -20.0, 120.0, "degC",
        LinearScaling(0, 27648, -20.0, 120.0)))
    vierte.add_signal("strom", ConvertingSignal(
        "Strom", 0.0, 32.0, "A",
        LinearScaling(0, 27648, 0.0, 32.0)))
    vierte.add_signal("kessel", ConvertingSignal(
        "Kessel", -20.0, 400.0, "degC", KelvinConverter()))

    client4 = MqttClient("broker.intern", vierte)
    client4.connect()
    client4.on_message(f"{client4.base_topic}/temperatur", "13824")
    client4.on_message(f"{client4.base_topic}/strom", "6912")
    client4.on_message(f"{client4.base_topic}/kessel", "463.15")
    vierte.snapshot()

    print("\n  Gegenüberstellung:")
    print("    Vererbung  : 3 Unterklassen (Raw-Temperatur, Raw-Strom, Kelvin)")
    print("    Komposition: 1 Klasse mit 3 austauschbaren Umrechnern")
    for schluessel, signal in vierte._signals.items():
        print(f"      {schluessel:<11} -> {signal.converter}")

    print("\n" + "=" * 68)
    print(" 9  Identität der Maschine")
    print("=" * 68)
    andere = Machine("SN-4711")
    print(f"  maschine == andere : {maschine == andere}  (gleiche Seriennummer)")
    print(f"  maschine is andere : {maschine is andere}  (verschiedene Objekte)")
    print(f"  erzeugte Signalobjekte insgesamt: {Signal._instance_count}")

    client.disconnect()


if __name__ == "__main__":
    main()

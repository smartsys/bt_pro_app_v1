"""Erklärtexte der eigenen Indikatoren für das Info-Fenster im Chart-Playground.

Bewusst getrennt von den Docstrings im Indikator-Code: Der Docstring erklärt einem
Entwickler die Umsetzung — Herkunft der Vorlage, Kausalität, Fallstricke. Hier steht,
was der Indikator im Chart tut und was ein Parameter praktisch bewirkt, in derselben
Sprache, in der man über eine Strategie nachdenkt.

Aufbau je Eintrag:

- ``was``     — was man im Chart sieht, in zwei bis vier Sätzen.
- ``wie``     — wie der Wert zustande kommt (optional, wenn ``was`` das schon trägt).
- ``inputs``  — nur die Eingaben, bei denen die Wahl etwas ändert (optional).
- ``params``  — je Parameter, was größere oder kleinere Werte bewirken.
- ``outputs`` — je Ausgabereihe, was sie enthält.

Die Schlüssel sind die Klassennamen ohne Gruppen-Prefix (``dwsSignumPivot``), die
Parameter- und Ausgabenamen genau die der Factory. Fehlt ein Indikator hier, fällt das
Info-Fenster auf seinen Docstring zurück.
"""

INDICATOR_EXPLANATIONS: dict[str, dict] = {

    'dwsSignumPivot': {
        'was': (
            'Ein Pivot-Hoch ist eine Kerze, deren Hoch höher ist als die drei Kerzen links '
            'und die drei Kerzen rechts davon. Ein lokaler Gipfel. Pivot-Tief entsprechend '
            'ein lokales Tal. Weil man die drei Kerzen rechts abwarten muss, steht ein Pivot '
            'erst drei Tage nach dem Gipfel fest. Deshalb springen die grauen Treppenlinien '
            'im Chart drei Kerzen hinter dem Hoch. Das ist noch keine Handelsaussage, nur '
            'eine Liste von Gipfeln und Tälern.'
        ),
        'params': {
            'left': (
                'Wie viele Kerzen links vom Gipfel niedriger sein müssen. Mehr Kerzen heißt: '
                'nur noch größere Gipfel zählen, es gibt weniger Pivots.'
            ),
            'right': (
                'Wie viele Kerzen rechts vom Gipfel niedriger sein müssen. Dieselbe Wirkung '
                'wie links — und zugleich die Wartezeit: um so viele Kerzen später steht der '
                'Pivot fest.'
            ),
        },
        'outputs': {
            'high_level': 'Das zuletzt bestätigte Pivot-Hoch, waagerecht fortgeschrieben bis zum nächsten.',
            'low_level': 'Dasselbe für das zuletzt bestätigte Pivot-Tief.',
            'high_age': 'Kerzen seit der Bestätigung des Hochs. 0 an der Kerze, an der es feststand.',
            'low_age': 'Dasselbe für das Tief.',
        },
    },

    'dwsSignumLevel': {
        'was': (
            'Ein einzelner Gipfel ist Zufall. Wenn der Kurs aber in den letzten 80 Tagen '
            'dreimal oder öfter an ungefähr derselben Höhe abgeprallt ist, mit 5 Prozent '
            'Toleranz, dann ist das eine Mauer. Die rote Linie ist die nächste Mauer über '
            'dem Kurs, der Widerstand. Die grüne Linie die nächste Mauer unter dem Kurs, die '
            'Unterstützung. Gibt es über dem Kurs keine Mauer mit drei Tests, ist die rote '
            'Linie leer.'
        ),
        'wie': (
            'Gemessen wird gegen den Schlusskurs der Vorkerze, nicht gegen den laufenden. '
            'Sonst läge der Widerstand per Konstruktion immer über dem Kurs und ein Ausbruch '
            'wäre nie messbar.'
        ),
        'params': {
            'left': 'Kerzen links des Gipfels — bestimmt, welche Gipfel überhaupt als Test zählen.',
            'right': 'Kerzen rechts des Gipfels. Zugleich die Wartezeit, bis ein Test mitzählt.',
            'window': (
                'Wie weit zurückgeschaut wird. Kürzer heißt: nur frische Mauern zählen, '
                'sie verschwinden schneller wieder.'
            ),
            'tolerance': (
                'Wie weit zwei Gipfel auseinanderliegen dürfen und trotzdem als dieselbe Mauer '
                'gelten, als Anteil. 0.05 sind 5 Prozent. Größer heißt: mehr Gipfel fallen '
                'zusammen, es gibt schneller drei Tests.'
            ),
            'min_tests': (
                'Wie oft die Mauer angelaufen worden sein muss. Höher heißt: weniger, dafür '
                'härtere Niveaus.'
            ),
        },
        'outputs': {
            'resistance': 'Die nächste Mauer über dem Kurs. Leer, wenn es keine mit genug Tests gibt.',
            'support': 'Die nächste Mauer unter dem Kurs.',
            'res_tests': 'Wie viele Gipfel den Widerstand getestet haben.',
            'sup_tests': 'Dasselbe für die Unterstützung.',
        },
    },

    'dwsSignumRange': {
        'was': (
            'Widerstand oben, Unterstützung unten — zusammen ist das eine Seitwärtsspanne. '
            'Als handelbare Formation zählt sie erst, wenn sie flach genug ist (Vorgabe: '
            'höchstens 30 Prozent zwischen Deckel und Boden) und lange genug steht (Vorgabe: '
            'mindestens 14 Kerzen seit dem ersten Test). Dann ist valid gleich 1 und der '
            'Chart färbt die Zone ein. Der klassische Einsatz: warten, bis der Kurs aus einer '
            'gültigen Range ausbricht.'
        ),
        'params': {
            'left': 'Kerzen links des Gipfels — wie bei den Pivots.',
            'right': 'Kerzen rechts des Gipfels, zugleich die Wartezeit bis zur Bestätigung.',
            'window': 'Wie weit für Deckel und Boden zurückgeschaut wird.',
            'tolerance': 'Wie weit Gipfel auseinanderliegen dürfen und trotzdem dieselbe Kante bilden.',
            'min_tests': 'Wie oft Deckel und Boden angelaufen sein müssen.',
            'max_height': (
                'Wie hoch die Spanne höchstens sein darf, als Anteil. 0.30 sind 30 Prozent '
                'zwischen Boden und Deckel. Kleiner heißt: nur enge Konsolidierungen zählen.'
            ),
            'min_duration': (
                'Wie viele Kerzen die Formation schon steht, bevor sie gilt. Größer heißt: '
                'weniger, dafür ausgereiftere Ranges.'
            ),
        },
        'outputs': {
            'top': 'Der Deckel der Spanne.',
            'bottom': 'Der Boden der Spanne.',
            'valid': '1, solange die Spanne flach und alt genug ist, sonst 0.',
            'height': 'Höhe der Spanne als Anteil: 0.12 heißt 12 Prozent zwischen Boden und Deckel.',
            'duration': 'Kerzen seit dem ersten Test der Formation.',
        },
    },

    'dwsGaussianChannel': {
        'was': (
            'Eine stark geglättete Trendlinie mit einem Band darum. Die Breite des Bandes '
            'folgt der Schwankung: in ruhigen Phasen wird es eng, in bewegten weit. Ein Kurs '
            'über der oberen Kante heißt also nicht nur "gestiegen", sondern "stärker '
            'gestiegen, als es zuletzt üblich war".'
        ),
        'wie': (
            'Die gewählte Preisreihe läuft durch einen mehrstufigen Glättungsfilter — das '
            'ergibt die Mittellinie. Dieselbe Glättung läuft über die typische Kerzenspanne. '
            'Der Abstand der beiden Kanten zur Mittellinie ist diese geglättete Spanne mal '
            'Faktor.'
        ),
        'params': {
            'source': 'Welche Preisreihe geglättet wird. hlc3 ist der Mittelwert aus Hoch, Tief und Schluss.',
            'poles': (
                'Zahl der Glättungsstufen, 1 bis 9. Mehr Stufen glätten stärker, laufen dem '
                'Kurs aber weiter hinterher.'
            ),
            'period': (
                'Länge der Glättung. Größer heißt träger — große Bewegungen bleiben stehen, '
                'kleine verschwinden.'
            ),
            'mult': (
                'Wie weit die Kanten von der Mittellinie wegliegen, als Vielfaches der '
                'geglätteten Spanne. Größer heißt: seltener Ausbrüche.'
            ),
            'reduced_lag': (
                'Zieht die Glättung näher an den aktuellen Kurs. Reagiert früher, dafür unruhiger.'
            ),
            'fast_response': (
                'Mischt eine schnellere Glättung dazu. Gleiche Wirkung wie oben, schwächer dosiert.'
            ),
        },
        'outputs': {
            'filt': 'Die Mittellinie, also der geglättete Kurs.',
            'hband': 'Obere Kante des Kanals.',
            'lband': 'Untere Kante des Kanals.',
            'width': (
                'Bandbreite in Prozent der Mittellinie. Kleiner Wert heißt Kompression '
                '(der Markt steht still), großer Wert heißt gelaufene Bewegung.'
            ),
        },
    },

    'dwsFVG': {
        'was': (
            'Eine Fair Value Gap ist ein Preisbereich, den der Markt übersprungen hat. Drei '
            'Kerzen: springt das Tief der dritten Kerze über das Hoch der ersten, blieb '
            'dazwischen eine Lücke, in der nicht gehandelt wurde — eine bullische Zone. '
            'Umgekehrt für eine bärische. Die Idee dahinter: solche Lücken werden später oft '
            'wieder angelaufen. Die Zone bleibt im Chart stehen, bis ein Schlusskurs durch '
            'ihre ferne Kante läuft; dann gilt sie als abgearbeitet und verschwindet.'
        ),
        'wie': (
            'Erkannt wird an der dritten Kerze des Musters — dort steht die Lücke fest, ohne '
            'dass in die Zukunft geschaut wird.'
        ),
        'params': {
            'threshold': (
                'Wie groß die Lücke mindestens sein muss, als Anteil. 0.01 sind 1 Prozent. '
                'Größer heißt: nur noch deutliche Lücken zählen.'
            ),
            'auto': (
                'Statt des festen Mindestabstands die durchschnittliche Kerzenspanne des '
                'bisherigen Verlaufs als Schwelle nehmen. Passt sich damit von selbst an, wie '
                'bewegt das Symbol ist.'
            ),
        },
        'outputs': {
            'signal': '+1 an der Kerze, an der eine bullische Lücke entsteht, -1 bei einer bärischen, sonst 0.',
            'bull_top': 'Obere Kante der jüngsten offenen bullischen Lücke, sonst leer.',
            'bull_bottom': 'Untere Kante derselben Lücke.',
            'bear_top': 'Obere Kante der jüngsten offenen bärischen Lücke, sonst leer.',
            'bear_bottom': 'Untere Kante derselben Lücke.',
        },
    },

    'dwsSMI': {
        'was': (
            'Ein Oszillator, der misst, wo der Schlusskurs innerhalb der Spanne der letzten '
            'Kerzen steht — oben, unten oder in der Mitte. Die Skala läuft etwa von -100 bis '
            '+100: über +40 gilt der Markt als überkauft, unter -40 als überverkauft. Ruhiger '
            'als der klassische Stochastik-Oszillator, weil doppelt geglättet.'
        ),
        'wie': (
            'Gemessen wird der Abstand des Schlusskurses zur Mitte zwischen höchstem Hoch und '
            'tiefstem Tief der letzten k_length Kerzen, ins Verhältnis gesetzt zur halben '
            'Spanne und zweifach geglättet.'
        ),
        'params': {
            'k_length': (
                'Über wie viele Kerzen die Spanne gemessen wird. Größer heißt: der Oszillator '
                'urteilt über einen längeren Abschnitt und schwingt langsamer.'
            ),
            'smooth1': 'Erste Glättung. Größer heißt ruhiger, aber später.',
            'smooth2': 'Zweite Glättung, gleiche Wirkung.',
            'signal': 'Länge der Signallinie über dem Oszillator. Kreuzungen dienen als Auslöser.',
        },
        'outputs': {
            'smi': 'Der Oszillator selbst, etwa zwischen -100 und +100.',
            'signal': 'Geglättete Signallinie darüber.',
        },
    },

    'dwsVWMA': {
        'was': (
            'Ein Durchschnitt, in dem Kerzen mit viel Umsatz stärker zählen als ruhige — und '
            'zwar um einen festen Prozentsatz nach unten versetzt. Die Linie liegt also '
            'immer unter dem eigentlichen Durchschnitt. Gedacht als Einstiegsschwelle: fällt '
            'der Kurs unter diese Linie, ist er deutlich unter seinen umsatzgewichteten '
            'Durchschnitt gerutscht.'
        ),
        'params': {
            'length': 'Über wie viele Kerzen gemittelt wird. Größer heißt träger.',
            'below_pct': (
                'Wie weit die Linie unter dem Durchschnitt liegt, in Prozent. 3 heißt drei '
                'Prozent darunter. Größer heißt: der Kurs muss tiefer fallen, bis er sie erreicht.'
            ),
        },
        'outputs': {
            'result': 'Der umsatzgewichtete Durchschnitt, um below_pct nach unten versetzt.',
        },
    },

    'dwsVWMABand': {
        'was': (
            'Dasselbe wie dwsVWMA, aber der Abstand nach unten ist keine feste Prozentzahl, '
            'sondern eine eigene Zeitreihe. Damit kann der Abstand mitatmen — zum Beispiel '
            'aus einer Schwankungsmessung wie ATR gespeist, sodass die Schwelle in ruhigen '
            'Phasen eng am Durchschnitt liegt und in wilden Phasen weiter weg.'
        ),
        'inputs': {
            'below_series': (
                'Die Reihe, die den Abstand vorgibt — in Kurseinheiten, nicht in Prozent. '
                'Hier hängt man üblicherweise die Ausgabe eines anderen Indikators ein.'
            ),
        },
        'params': {
            'length': 'Über wie viele Kerzen der umsatzgewichtete Durchschnitt gemittelt wird.',
        },
        'outputs': {
            'result': 'Der umsatzgewichtete Durchschnitt minus der Abstandsreihe.',
        },
    },

    'dwsFastSMA': {
        'was': (
            'Ein gleitender Durchschnitt, dem eine Steigungskorrektur aufaddiert wird: läuft '
            'der Kurs, schiebt die Korrektur die Linie in Laufrichtung vor. Sie klebt dadurch '
            'enger am Kurs als ein normaler Durchschnitt derselben Länge, um den Preis für '
            'mehr Fehlsignale in Seitwärtsphasen.'
        ),
        'params': {
            'length': 'Über wie viele Kerzen gemittelt wird. Größer heißt träger.',
            'multiplier': (
                'Wie stark die Steigungskorrektur wirkt. Größer heißt: die Linie läuft dem '
                'Kurs weiter voraus und überschießt eher.'
            ),
        },
        'outputs': {
            'result': 'Die korrigierte Durchschnittslinie.',
        },
    },

    'dwsVolumeRatio': {
        'was': (
            'Das Volumen der aktuellen Kerze geteilt durch das durchschnittliche Volumen der '
            'letzten Kerzen. 1.0 heißt "ganz normaler Umsatz", 2.0 heißt "doppelt so viel wie '
            'üblich", 0.5 heißt "halb so viel". Typischer Einsatz als Bestätigung: einsteigen '
            'nur, wenn hinter der Bewegung auch Umsatz steht.'
        ),
        'params': {
            'window': (
                'Über wie viele Kerzen der Vergleichsdurchschnitt läuft. Kürzer heißt: der '
                'Vergleich richtet sich nach den letzten Tagen und schlägt schneller aus.'
            ),
        },
        'outputs': {
            'result': 'Verhältnis zum Durchschnitt. Über 1 ist überdurchschnittlicher Umsatz.',
        },
    },

    'dwsAssetDD': {
        'was': (
            'Wie weit der Kurs unter seinem höchsten Stand der letzten Kerzen liegt. 0 heißt '
            '"gerade auf Höchststand", -0.30 heißt "30 Prozent darunter". Der Wert ist nie '
            'positiv. Gedacht als Regime-Filter: nur handeln, solange das Symbol nicht zu '
            'weit von seinem Hoch entfernt ist.'
        ),
        'params': {
            'window': (
                'Über wie viele Kerzen das Hoch gesucht wird. Größer heißt: der Bezugspunkt '
                'ist ein echtes Mehrmonatshoch, der Wert bleibt länger tief negativ.'
            ),
        },
        'outputs': {
            'result': 'Abstand zum Hoch als Anteil, immer 0 oder negativ.',
        },
    },

    'dwsCrossover': {
        'was': (
            'Meldet, wenn zwei Linien sich kreuzen — in beide Richtungen. An der Kerze, an '
            'der die Kreuzung passiert, steht 1, sonst 0. Man hängt zwei Reihen an, '
            'üblicherweise den Kurs und eine Schwelle, und fragt in der Regel dann '
            'schlicht ab, ob der Wert über 0.5 liegt.'
        ),
        'inputs': {
            'series_a': 'Die erste Reihe, üblicherweise der Kurs.',
            'series_b': 'Die zweite Reihe, üblicherweise die Schwelle, an der gekreuzt wird.',
        },
        'outputs': {
            'result': '1 an der Kerze der Kreuzung, sonst 0. Die erste Kerze ist immer 0.',
        },
    },

    'dwsConst': {
        'was': (
            'Liefert auf jeder Kerze denselben Wert — mehr nicht. Der Zweck ist ein anderer: '
            'eine feste Zahl in einer Regel ("ADX über 20") lässt sich nicht durchsweepen. '
            'Schreibt man stattdessen "ADX über const", wird aus der Zahl ein Parameter, den '
            'ein Multiparameter-Lauf über einen Wertebereich schicken kann.'
        ),
        'inputs': {
            'source': 'Nur als Längenvorlage. Der Inhalt der Reihe geht nicht in die Rechnung ein.',
        },
        'params': {
            'value': 'Der Wert, den jede Kerze bekommt. Genau der ist im Lauf sweepbar.',
        },
        'outputs': {
            'result': 'Die Konstante auf jeder Kerze.',
        },
    },

    'dwsRandomEntry': {
        'was': (
            'Würfelt Einstiegssignale, ohne den Markt anzusehen. Das ist kein Handelsbaustein, '
            'sondern die Nullmessung: eine Strategie, deren Einstieg reines Rauschen ist, '
            'zeigt, welche Kennzahlen allein durch Zufall zustande kommen. Erst wer sich '
            'davon abhebt, hat überhaupt etwas gefunden.'
        ),
        'inputs': {
            'source': 'Nur als Längenvorlage. Die Kurse gehen nicht in die Rechnung ein.',
        },
        'params': {
            'seed': (
                'Startwert des Zufallsgenerators. Derselbe Seed liefert exakt dieselben '
                'Signale; über einen Wertebereich wird jeder Seed zu einem eigenen Versuch.'
            ),
            'prob': (
                'Wie wahrscheinlich pro Kerze ein Signal fällt. 0.05 heißt: im Schnitt jede '
                'zwanzigste Kerze. Damit stellt man die Handelsfrequenz auf die der echten '
                'Strategie ein.'
            ),
        },
        'outputs': {
            'result': '1 an Signal-Kerzen, sonst 0.',
        },
    },

    'dwsLookaheadOracle': {
        'was': (
            'Schaut absichtlich in die Zukunft und gehört niemals in eine Handelsstrategie. '
            'Das Gegenstück zum Zufalls-Einstieg: dort ein Einstieg ohne jede Information, '
            'hier einer, der die Antwort kennt. Beide dienen nur der Eichung von '
            'Signifikanzmaßen — der Zufall zeigt, was reines Rauschen an Kennzahlen erzeugt, '
            'das Orakel, ob ein echter Vorteil überhaupt erkannt wird.'
        ),
        'wie': (
            'Pro Kerze wird gewürfelt, ob das Signal aus der Zukunft kommt oder aus dem '
            'Zufall. Kommt es aus der Zukunft, feuert es, wenn der Kurs in lookahead Kerzen '
            'um mehr als threshold höher steht. Bei skill 0 ist das Ergebnis identisch zum '
            'reinen Zufalls-Einstieg, bei skill 1 ein perfektes Orakel.'
        ),
        'params': {
            'seed': 'Startwert des Zufallsgenerators — steuert Würfel und Auswahl der Zukunftskerzen.',
            'prob': 'Signalrate des Zufallsanteils, wie beim Zufalls-Einstieg.',
            'skill': 'Anteil der Kerzen, deren Signal aus der Zukunft stammt, von 0 bis 1.',
            'lookahead': 'Wie viele Kerzen weit in die Zukunft geschaut wird.',
            'threshold': (
                'Wie stark der Kurs in diesem Fenster steigen muss, als Anteil. 0.2 sind 20 '
                'Prozent. Darüber stellt man die Signalrate des Zukunftsanteils auf die des '
                'Zufallsanteils ein, damit beide gleich oft handeln.'
            ),
        },
        'outputs': {
            'result': '1 an Signal-Kerzen, sonst 0. Die letzten lookahead Kerzen liefern kein Zukunftssignal.',
        },
    },
}

#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright (C) 2010 Hans Maerk, Maerki Informatik
# License: LGPL (http://www.gnu.org/licenses/lgpl.html)
#
# Siehe http://www.maerki.com/hans/orux
#
# Dieses Script erstellt verschiedene Karten
# welche in OruxMaps verwendet werden kann.
# Die resultierende Karten sind etwa 1.5 GBytes
# gross. Dies ist eine Groesse, die von Android
# und Orux noch vernünftig verarbeitet werden kann.
#
# Die Aufteilung der Kartenblaetter entspricht den
# 1:100'000er Zusammenfassungen der Landestopographie:
# http://www.swisstopo.admin.ch/internet/swisstopo/de/home/products/accessories/brochures.parsys.000100.DownloadFile.tmp/blattuebersichtena4.pdf
# Seite 3: Landeskarte der Schweiz und Zusammensetzungen 1:100'000
#
import programm

listZusammensetzungen = (
    (((600000.0, 140000.0), (730000.0, 220000.0)), 101, "Thunersee_Zentralschweiz"),
    (((570000.0, 200000.0), (690000.0, 280000.0)), 102, "Basel_Luzern"),
    (((670000.0, 230000.0), (780000.0, 300000.0)), 103, "Zuerich_StGallen"),
    (((500000.0, 140000.0), (600000.0, 220000.0)), 104, "Lausanne_Bern"),
    (((550000.0, 70000.0), (670000.0, 140000.0)), 105, "Wallis"),
    (((680000.0, 70000.0), (750000.0, 190000.0)), 107, "Tessin"),
    (((480000.0, 100000.0), (580000.0, 170000.0)), 108, "LaGruyere_LeLeman"),
    (((760000.0, 110000.0), (840000.0, 230000.0)), 109, "Praettigau_Engadin"),
    (((690000.0, 110000.0), (760000.0, 230000.0)), 110, "Vorderrhein_Hinterrhein"),
    (((530000.0, 160000.0), (600000.0, 270000.0)), 111, "Ajoie-Fribourg"),
)

fSwissgridSchweiz = (480000.0, 60000.0), (865000.0, 302000.0)

for fSwissgridKarte, oruxmap, strKarteName in listZusammensetzungen:
    oruxmap = programm.OruxMap("CH_%d_%s" % (oruxmap, strKarteName), strTopFolder="Schweiz_Zusammensetzungen")
    for iLayer in (1000000, 500000, 200000):
        # Für grosse Masstäbe: ...
        if False:
            # ... die gesamte Schweiz
            oruxmap.createLayer(None, iLayer, fSwissgridSchweiz)
        else:
            # ... das entsprechende Gebiet
            oruxmap.createLayer(None, iLayer, fSwissgridKarte)

    for iLayer in (100000, 50000, 25000):
        # Kleinere Masstäge: Nur noch das entsprechende Gebiet
        oruxmap.createLayer(None, iLayer, fSwissgridKarte)

    oruxmap.done()

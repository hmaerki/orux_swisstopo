#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright (C) 2010 Hans Maerk, Maerki Informatik
# License: LGPL (http://www.gnu.org/licenses/lgpl.html)
#
# Siehe http://www.maerki.com/hans/orux
#
# Dieses Script erstellt eine Karte welche Zürich,
# Winterthur und Chur umfasst.
# Die Karte kann in OruxMaps verwendet werden kann.
# Die resultierende Karte ist gut 1 GBytes gross.
#
# Würde die gesamte Schweiz in allen Masstäben erstellt
# werden, so würde dies etwa 5 GBytes beanspruchen!
#
import programm

fSwissgridSchweiz = (480000.0, 60000.0), (865000.0, 302000.0)
fSwissgridKantonZH = (660000.0, 180000.0), (718000.0, 280000.0)
fSwissgridZuercherOberland = (660000.0, 180000.0), (800000.0, 270000.0)

oruxmap = programm.OruxMap(__file__)

for iMasstab in (1000000, 500000):
    # Für grosse Masstäbe: die gesamte Schweiz
    oruxmap.createLayer(None, iMasstab, fSwissgridSchweiz)

for iMasstab in (200000, 100000):
    # Mittlere Masstäbe: Nur den Kanton Zürich
    oruxmap.createLayer(None, iMasstab, fSwissgridKantonZH)

for iMasstab in (50000, 25000):
    # Kleinere Masstäge: Nur noch das Zürcher Oberland
    oruxmap.createLayer(None, iMasstab, fSwissgridZuercherOberland)

oruxmap.done()

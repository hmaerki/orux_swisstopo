#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright (C) 2010 Hans Maerk, Maerki Informatik
# License: LGPL (http://www.gnu.org/licenses/lgpl.html)
#
# Siehe http://www.maerki.com/hans/orux
#
# Dieses Script erstellt eine Karte vom Zürcher Oberland
# welche in OruxMaps verwendet werden kann.
# Die resultierende Karte ist etwa 125 MBytes gross.
#
# Würde die gesamte Schweiz in allen Masstäben erstellt
# werden, so würde dies etwa 5 GBytes beanspruchen!
#
import programm

fSwissgridSchweiz = (480000.0, 60000.0), (865000.0, 302000.0)
fSwissgridKantonZH = (666100.0, 225000.0), (718000.0, 280000.0)
fSwissgridZuercherOberland = (676520.0, 251187.0), (717520.0, 230137.0)
fSwissgridLuetzelsee = (701000.0, 237000.0), (699000.0, 234000.0)

map = programm.OruxMap(__file__, bCopyReferenceTiles=True)

for iLayer in (5000000, 2000000, 1000000, 500000):
    # Für grosse Masstäbe: die gesamte Schweiz
    map.createLayer(iLayer, fSwissgridSchweiz)

for iLayer in (200000, 100000):
    # Mittlere Masstäbe: Nur den Kanton Zürich
    map.createLayer(iLayer, fSwissgridKantonZH)

for iLayer in (50000, 25000):
    # Kleinere Masstäbe: Nur noch das Zürcher Oberland
    map.createLayer(iLayer, fSwissgridZuercherOberland)

for iLayer in (10000,):
    # Kleinere Masstäbe: Nur noch den Lützelsee
    map.createLayer(iLayer, fSwissgridLuetzelsee)

map.done()

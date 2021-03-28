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

fSwissgridKarte = (480000.0, 70000.0),  (840000.0, 300000.0)

for strTopFolder, strKartenName, listLayer in (
      # 1.9 GByte
      ('Schweiz_4GByte', '25000_only', (25000,)),
      # 4.0 GByte
      ('Schweiz_4GByte', '50000_and_up', (5000000, 2000000, 1000000, 500000, 200000, 100000, 50000)),
      # 5.9 GByte
      ('Schweiz', '25000', (5000000, 2000000, 1000000, 500000, 200000, 100000, 50000, 25000)),
    ):
  map = programm.OruxMap('CH_%s' % strKartenName, strTopFolder=strTopFolder, bSqlite=True, bDrawTileBorders=False, bCopyReferenceTiles=True, bJustDownloadTiles=False)

  for iLayer in listLayer:
    map.createLayer(iLayer, fSwissgridKarte)

  map.done()

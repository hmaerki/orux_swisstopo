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
from programm.context import Context

fSwissgridKarte = (480000.0, 70000.0), (840000.0, 300000.0)

context = Context()
# context.skip_optimize_png = False
context.only_tiffs = ("swiss-map-raster200_2019_2002_krel_10_2056.tif",)
context.only_tiles_border = 5
with programm.OruxMap(f"CH_Schweiz", context=context) as oruxmap:
    oruxmap.createLayers(iMasstabMin=200, iMasstabMax=1000)

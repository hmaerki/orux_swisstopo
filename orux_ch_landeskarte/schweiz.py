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

tif_0010_wetzikon = "swiss-map-raster10_2020_1112-2_krel_0.5_2056.tif"
tif_0010_luetzelsee = "swiss-map-raster10_2020_1112-4_krel_0.5_2056.tif"
tif_0025_wetzikon = "swiss-map-raster25_2013_1112_komb_1.25_2056.tif"
tif_0050_wetzikon = "swiss-map-raster50_2013_226_komb_2.5_2056.tif"
tif_0100_wetzikon = "swiss-map-raster100_2013_33_komb_5_2056.tif"
tif_0200_wetzikon = "swiss-map-raster200_2019_2002_krel_10_2056.tif"

tiffs_wetzikon = (tif_0010_wetzikon, tif_0010_luetzelsee, tif_0025_wetzikon, tif_0050_wetzikon, tif_0100_wetzikon, tif_0200_wetzikon)

context = Context()
# context.skip_optimize_png = True
context.only_tiffs = tiffs_wetzikon
# context.only_tiles_border = 5
# context.only_tiles_modulo = 10
# context.skip_tiff_read = True
# context.skip_png_write = True
with programm.OruxMap(f"CH_Schweiz", context=context) as oruxmap:
    oruxmap.createLayers(iMasstabMin=25, iMasstabMax=200)

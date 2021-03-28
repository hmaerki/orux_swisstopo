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
import rasterio
import PIL.Image

import programm

filename = "/home/maerki/versuche_orux/orux/swiss-map-raster25_2013_1112_komb_1.25_2056.tif"

with rasterio.open(filename, "r") as dataset:
    print(dataset.count, dataset.width, dataset.height)
    print(dataset.bounds)
    print(dataset.shape)
    print(dataset.transform)
    print(dataset.crs)
    print(dataset.crs.wkt)
    print(dataset.meta)

    with PIL.Image.open(filename) as img:


        left = dataset.bounds.left
        right = dataset.bounds.right
        bottom = dataset.bounds.bottom
        top = dataset.bounds.top
        fASwissgrid = (left, top)
        fBSwissgrid = (right, bottom)

        fSwissgridCurrentImage = fASwissgrid, fBSwissgrid
        # ((690000.0, 230000.0), (707500.0, 242000.0))


        oruxmap = programm.OruxMap(__file__)

        for iMasstab in (25000,):
            # Kleinere Masstäbe: Nur noch das Zürcher Oberland
            oruxmap.createLayer(img, iMasstab, fSwissgridCurrentImage)

        oruxmap.done()

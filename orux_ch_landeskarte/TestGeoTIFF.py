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

        fSwissgridSchweiz = (480000.0, 60000.0), (865000.0, 302000.0)
        fSwissgridKantonZH = (666100.0, 225000.0), (718000.0, 280000.0)
        fSwissgridZuercherOberland = (676520.0, 251187.0), (717520.0, 230137.0)
        fSwissgridLuetzelsee = (701000.0, 237000.0), (699000.0, 234000.0)

        # top, left = programm.transformCH1903_to_WGS84(fY=dataset.bounds.top, fX=dataset.bounds.left)
        # bottom, right = programm.transformCH1903_to_WGS84(fY=dataset.bounds.bottom, fX=dataset.bounds.right)
        # fSwissgridCurrentImage = (left, top), (bottom, right)

        # Forch/Tobelmühli
        # CH1903+ / LV95	2'690'002.0, 1'241'997.0
        # CH1903 / LV03	690'001.16, 241'997.16
        # WGS 84 (lat/lon)	47.32270, 8.62919
        #

        # ((690000.0, 242000.0), (707500.0, 230000.0))
        # fRSwissgrid = (dataset.bounds.right-2000000, dataset.bounds.top-1000000)
        # fSSwissgrid = (dataset.bounds.left-2000000, dataset.bounds.bottom-1000000)
        # fSwissgridCurrentImage = fRSwissgrid, fSSwissgrid

        left = dataset.bounds.left - 2000000
        right = dataset.bounds.right - 2000000
        bottom = dataset.bounds.bottom - 1000000
        top = dataset.bounds.top - 1000000
        fRSwissgrid = (left, bottom)
        fSSwissgrid = (right, top)

        fSwissgridCurrentImage = fRSwissgrid, fSSwissgrid
        # ((690000.0, 230000.0), (707500.0, 242000.0))

        if False:
            # Take one tile off from the top right
            right = right + (left - right) / 35
            top = top + (bottom - top) / 24
            fRSwissgrid = (left, bottom)
            fSSwissgrid = (right, top)
            fSwissgridCurrentImage = fRSwissgrid, fSSwissgrid
            # ((690000.0, 230000.0), (707000.0, 241500.0))

        oruxmap = programm.OruxMap(__file__, bCopyReferenceTiles=False)

        for iLayer in (25000,):
            # Kleinere Masstäbe: Nur noch das Zürcher Oberland
            oruxmap.createLayer(img, iLayer, fSwissgridCurrentImage)

        oruxmap.done()

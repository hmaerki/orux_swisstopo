#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2010-2021 Hans Maerk, Maerki Informatik
# License: LGPL (http://www.gnu.org/licenses/lgpl.html)
#
# Siehe http://www.maerki.com/hans/orux
#
# Version: 1.0.5
# History:
#   2010-06-22, Hans Maerki, Implementiert
#   2010-06-23, Hans Maerki, Koordinaten der Karte Massstab 1:50000 angepasst.
#   2011-01-17, Hans Maerki, Neu koennen Karten in Unterordner gruppiert werden.
#   2011-02-16, Hans Maerki, Swisstopo hat die Server gewechselt: Neue Url angepasst.
#   2013-09-06, Hans Maerki, Swisstopo hat die Server gewechselt: Neue Url angepasst.
#   2018-04-24, Hans Maerki, Swisstopo hat die Server gewechselt: Neue Logik angepasst.
#   2019-06-03, Hans Maerki, Angepasst an Python 3.7.2.
#   2021-03-28, Hans Maerki, Massive cleanup.
"""
http://map.geo.admin.ch

http://gpso.de/navigation/utm.html
  UTM- Koordinatensystem, WGS84- Kartendatum
http://de.wikipedia.org/wiki/Kartendatum
  Geodaetisches Datum
http://www.swisstopo.admin.ch/internet/swisstopo/de/home/topics/survey/sys/refsys/projections.html
  Schweizerische Kartenprojektionen
http://www.swisstopo.admin.ch/internet/swisstopo/de/home/apps/calc/navref.html
  Umrechnung von Schweizer Landeskoordinaten in ellipsoidische WGS84-Koordinaten
http://de.wikipedia.org/wiki/WGS_84
  World Geodetic System 1984 (WGS 84)
http://www.ahnungslos.ch/android-screenshots-in-5-schritten/
  Android Screen Capture
"""
import os
import io
import math
import time
import shutil
import pathlib
import sqlite3
import collections
from dataclasses import dataclass
from typing import List

import geotiff

from programm import projections
from programm.projections import LON, LAT

fSwissgridSchweiz = (480000.0, 60000.0), (865000.0, 302000.0)

@dataclass
class LayerParams:
    iMasstab: int
    iBaseLayer: int


listLayers = (
    LayerParams(
        iMasstab=5000000,
        iBaseLayer=15,
    ),
    LayerParams(
        iMasstab=2000000,
        iBaseLayer=16,
    ),
    LayerParams(
        iMasstab=1000000,
        iBaseLayer=17,
    ),
    LayerParams(
        iMasstab=500000,
        iBaseLayer=18,
    ),
    LayerParams(
        iMasstab=200000,
        iBaseLayer=19,
    ),
    LayerParams(
        iMasstab=100000,
        iBaseLayer=20,
    ),
    LayerParams(
        iMasstab=50000,
        iBaseLayer=21,
    ),
    LayerParams(
        iMasstab=25000,
        iBaseLayer=22,
    ),
    LayerParams(
        iMasstab=10000,
        iBaseLayer=25,
    ),
)

strTemplateLayerBegin = """    <OruxTracker xmlns="http://oruxtracker.com/app/res/calibration" versionCode="2.1">
      <MapCalibration layers="false" layerLevel="{id}">
        <MapName><![CDATA[{strMapName} {id:d}]]></MapName>
        <MapChunks xMax="{xMax}" yMax="{yMax}" datum="CH-1903:Swiss@WGS 1984:Global Definition" projection="(SUI) Swiss Grid" img_height="{iTILE_SIZE}" img_width="{iTILE_SIZE}" file_name="{strMapName}" />
        <MapDimensions height="{height}" width="{width}" />
        <MapBounds minLat="{minLat:2.6f}" maxLat="{maxLat:2.6f}" minLon="{minLon:2.6f}" maxLon="{maxLon:2.6f}" />
        <CalibrationPoints>
"""

strTemplateLayerEnd = """        </CalibrationPoints>
      </MapCalibration>
    </OruxTracker>
"""


strTemplateMainStart = """<?xml version="1.0" encoding="UTF-8"?>
<OruxTracker xmlns="http://oruxtracker.com/app/res/calibration" versionCode="3.0">
  <MapCalibration layers="true" layerLevel="0">
    <MapName><![CDATA[{strMapName}]]></MapName>
"""

strTemplateMainEnd = """  </MapCalibration>
</OruxTracker>"""

# Wir unterstützen im Moment nur eine Tile-Grösse:
iTILE_SIZE = 400

# Der Layer 22 der Landestopographie entspricht Layer 15 in 'Mobile Atlase Creator'.
# Der Unterschied ist also:
iLAYER_OFFSET = 7

strFOLDER_ORUX_CH_LANDESKARTE = pathlib.Path(__file__).absolute().parent
strFOLDER_CACHE = strFOLDER_ORUX_CH_LANDESKARTE / "../../orux_ch_landeskarte_cache"
strFOLDER_MAPS = strFOLDER_ORUX_CH_LANDESKARTE / "../../orux_ch_landeskarte_maps"
strFOLDER_REFERENCE_TILES = strFOLDER_ORUX_CH_LANDESKARTE / "reference_tiles"
strFOLDER_CACHE_TILES = strFOLDER_CACHE / "tiles"



class OruxMap:
    def __init__(self, strMapName, bSqlite=True, bCopyReferenceTiles=False, strTopFolder=strFOLDER_ORUX_CH_LANDESKARTE):
        assert isinstance(strTopFolder, pathlib.Path)
        if strMapName.endswith(".py"):
            # Es wurde der Parameter __file__ uebergeben, strMapName sieht also etwa so aus: C:\data\...\Hombrechtikon.py
            strMapName = os.path.basename(strMapName).replace(".py", "")
        self.strMapName = strMapName
        self.bCopyReferenceTiles = bCopyReferenceTiles
        self.strTopFolder = strTopFolder
        self.strMapFolder = strFOLDER_MAPS / strMapName
        self.bSqlite = bSqlite

        print("===== ", self.strMapName)

        if self.strMapFolder.exists():
            shutil.rmtree(self.strMapFolder)
            time.sleep(1.0)
        self.strMapFolder.mkdir(parents=True, exist_ok=True)

        if self.bCopyReferenceTiles:
            if (strTopFolder / strFOLDER_REFERENCE_TILES).exists():
                shutil.rmtree(strTopFolder / strFOLDER_REFERENCE_TILES)
                time.sleep(1.0)
            (strTopFolder / strFOLDER_REFERENCE_TILES).mkdir(parents=True, exist_ok=True)

        if self.bSqlite:
            strFilenameSqlite = self.strMapFolder / "OruxMapsImages.db"
            if strFilenameSqlite.exists():
                strFilenameSqlite.unlink()
            self.db = sqlite3.connect(strFilenameSqlite)
            self.db.execute("""CREATE TABLE tiles (x int, y int, z int, image blob, PRIMARY KEY (x,y,z))""")
            self.db.execute("""CREATE TABLE android_metadata (locale TEXT)""")
            self.db.execute("""INSERT INTO "android_metadata" VALUES ("de_CH");""")

        self.fXml = (self.strMapFolder / f"{strMapName}.otrk2.xml").open("w")
        self.fXml.write(strTemplateMainStart.format(strMapName=strMapName))

    def createLayer(self, img, iMasstab, l):
        projections.assertOrientation(l)
        (fASwissgrid, fBSwissgrid) = l
        objLayer = Layer(self, img, iMasstab, fASwissgrid, fBSwissgrid)
        objLayer.create()

    def done(self):
        self.fXml.write(strTemplateMainEnd)
        self.fXml.close()

        if self.bSqlite:
            self.db.commit()
            self.db.close()
        print("----- Fertig")
        if self.bCopyReferenceTiles:
            print(f'bCopyReferenceTiles ist eingeschaltet: Die Referenztiles liegen im Ordner "{strFOLDER_REFERENCE_TILES}". Beachte das rote Kreuz!')
        print(f'Die Karte liegt nun bereit im Ordner "{self.strMapName}".')
        print("Dieser Ordner muss jetzt 'von Hand' in den Ordner \"oruxmaps\\mapfiles\" kopiert werden.")
        # sys.stdin.readline()


class Layer:
    def __init__(self, objOrux, img, iMasstab, fASwissgrid, fBSwissgrid):  # pylint: disable=too-many-arguments
        # TODO
        assert img is not None
        self.objOrux = objOrux
        self.img = img
        self.iMasstab = iMasstab
        self.verifyInput(fASwissgrid, fBSwissgrid)
        projections.assertSwissgridIsNorthWest(fASwissgrid, fBSwissgrid)
        self.fASwissgrid, self.fBSwissgrid = fASwissgrid, fBSwissgrid
        self.objLayerParams: LayerParams = self.findLayer(iMasstab)
        self.strFolderCacheTiles = strFOLDER_CACHE_TILES / f"{self.objLayerParams.iBaseLayer}"
        if not self.strFolderCacheTiles.exists():
            self.strFolderCacheTiles.mkdir(parents=True, exist_ok=True)

        listFiles = os.listdir(self.strFolderCacheTiles)
        listFiles = filter(lambda filename: filename.endswith(".jpg"), listFiles)
        self.setTilesFiles = set(listFiles)

    def findLayer(self, iMasstab) -> LayerParams:
        for layerParam in listLayers:
            if layerParam.iMasstab == iMasstab:
                return layerParam
        raise Exception(f"Layer mit Masstab {iMasstab} existiert nicht.")

    def verifyInput(self, fUSwissgrid_, fVSwissgrid_):
        def verifyDatatype(pt):
            assert isinstance(pt[0], float)
            assert isinstance(pt[1], float)

        verifyDatatype(fUSwissgrid_)
        verifyDatatype(fVSwissgrid_)
        projections.assertOrientation((fUSwissgrid_, fVSwissgrid_))

        # Referenzpunkte R und S ordnen: R ist 'oben links', S ist 'unten rechts'
        # untenLinks = min_(fUSwissgrid_, fVSwissgrid_)
        # obenRechts = max_(fUSwissgrid_, fVSwissgrid_)
        # fASwissgrid = untenLinks[0], obenRechts[1]
        # fBSwissgrid = obenRechts[0], untenLinks[1]

        # return fASwissgrid, fBSwissgrid

    def is_white_data(self, image_data):
        try:
            import PIL.Image
        except ModuleNotFoundError:
            return False
        if len(image_data) > 1000:
            return False
        imTile = PIL.Image.open(io.BytesIO(image_data))
        extrema = imTile.convert("L").getextrema()
        white = extrema == (255, 255)
        del imTile
        return white

    def extractTile(self, x, y):
        im_crop = self.img.crop((x * iTILE_SIZE, y * iTILE_SIZE, (x + 1) * iTILE_SIZE, (y + 1) * iTILE_SIZE))
        fOut = io.BytesIO()
        geotiff.save_purge_palette(fOut, im_crop)
        return fOut.getvalue()

    def create(self):  # pylint: disable=too-many-statements,too-many-branches
        fTlWGS84 = projections.CH1903_to_WGS84(self.fASwissgrid)
        fBrWGS84 = projections.CH1903_to_WGS84(self.fBSwissgrid)
        fBlWGS84 = projections.CH1903_to_WGS84((self.fASwissgrid[LON], self.fBSwissgrid[LAT]))
        fTrWGS84 = projections.CH1903_to_WGS84((self.fBSwissgrid[LON], self.fASwissgrid[LAT]))
        projections.assertWGS84IsNorthWest(fTlWGS84, fBrWGS84)

        #
        # Die Tiles fuer die Karte zusammenkopieren
        #
        if not self.objOrux.bSqlite:
            strFolder = self.objOrux.strTopFolder / self.objOrux.strMapName / f"{self.objOrux.strMapName}_{self.objLayerParams.iBaseLayer - iLAYER_OFFSET}"
            if not strFolder.exists():
                strFolder.mkdir(xy=True)
            if not (strFolder / "set").exists():
                (strFolder / "set").mkdir(parents=True, exist_ok=True)

        xCount = self.img.width // iTILE_SIZE
        yCount = self.img.height // iTILE_SIZE
        for y in range(yCount):
            for x in range(xCount):
                # TODO: Remove
                continue
                if self.objOrux.bSqlite:
                    rawImagedata = self.extractTile(x, y)
                    b = sqlite3.Binary(rawImagedata)
                    self.objOrux.db.execute("insert or replace into tiles values (?,?,?,?)", (x, y, self.objLayerParams.iBaseLayer - iLAYER_OFFSET, b))
                else:
                    try:
                        strFilenameTileFull = self.strFolderCacheTiles / strFilenameTile
                        strFilename2 = f"{self.objOrux.strMapName}_{self.objLayerParams.iBaseLayer - iLAYER_OFFSET}_{x}_{yCount - y - 1}.omc2"
                        strFilename2Full = self.objOrux.strTopFolder / ".." / strFolder / "set" / strFilename2
                        shutil.copyfile(strFilenameTileFull, strFilename2Full)
                        with strFilenameTileFull.open("rb") as fIn:
                            fOut = io.BytesIO()
                    except IOError as e:
                        shutil.copyfile(strFOLDER_ORUX_CH_LANDESKARTE / "not_found.jpg", strFilename2Full)
                        print("Error:", e)

        if self.objOrux.bSqlite:
            f = self.objOrux.fXml
        else:
            f = (self.objOrux.strMapFolder / f"{self.objOrux.strMapName} {self.objLayerParams.iBaseLayer - iLAYER_OFFSET}.otrk2.xml").open("w")
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n')

        projections.assertWGS84IsNorthWest(fTlWGS84, fBrWGS84)

        f.write(
            strTemplateLayerBegin.format(
                iTILE_SIZE=iTILE_SIZE,
                strMapName=self.objOrux.strMapName,
                id=self.objLayerParams.iBaseLayer - iLAYER_OFFSET,
                xMax=xCount,
                yMax=yCount,
                height=yCount * iTILE_SIZE,
                width=xCount * iTILE_SIZE,
                minLat=fBrWGS84[LAT],
                maxLat=fTlWGS84[LAT],
                minLon=fTlWGS84[LON],
                maxLon=fBrWGS84[LON],
            )
        )
        for strPoint, fLon, fLat in (
            ("TL", fTlWGS84[LON], fTlWGS84[LAT]),
            ("BR", fBrWGS84[LON], fBrWGS84[LAT]),
            ("TR", fTrWGS84[LON], fTrWGS84[LAT]),
            ("BL", fBlWGS84[LON], fBlWGS84[LAT]),
        ):
            f.write(f'          <CalibrationPoint corner="{strPoint}" lon="{fLon:2.6f}" lat="{fLat:2.6f}" />\n')

        f.write(strTemplateLayerEnd)
        if not self.objOrux.bSqlite:
            f.close()


if False:
    oruxmap = OruxMap("Hombrechtikon")
    for iBaseLayer in (22,):
        oruxmap.createLayerPlusMinus(iBaseLayer, (701000.0, 235000.0), 4000.0)

if False:
    oruxmap = OruxMap("Hombrechtikon")
    for iBaseLayer in (17, 18, 19):
        oruxmap.createLayerPlusMinus(iBaseLayer, (701000.0, 235000.0), 10000.0)
    for iBaseLayer in (20, 21, 22):
        oruxmap.createLayerPlusMinus(iBaseLayer, (701000.0, 235000.0), 4000.0)

if False:
    oruxmap = OruxMap("RefBl")
    for iBaseLayer in (22,):  # (17, 18, 19, 20, 21, 22):
        oruxmap.createLayerPlusMinus(iBaseLayer, (481000.0, 110000.0), 2000.0)

    oruxmap = OruxMap("RefTr")
    for iBaseLayer in (22,):  # (17, 18, 19, 20, 21, 22):
        oruxmap.createLayerPlusMinus(iBaseLayer, (776000.0, 276000.0), 2000.0)

if False:
    oruxmap = OruxMap("RefLuetzel")
    for iBaseLayer in (16,):
        oruxmap.createLayerPlusMinus(iBaseLayer, (700000.0, 236000.0), 2000.0)

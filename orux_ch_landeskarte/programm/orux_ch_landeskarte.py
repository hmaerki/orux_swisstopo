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

fSwissgridSchweiz = (480000.0, 60000.0), (865000.0, 302000.0)
LON = 0
LAT = 1
LON_OFFSET = 2000000.0
LAT_OFFSET = 1000000.0
LAT_BERN = 600000.0
LON_BERN = 200000.0

def assertOrientation(fSwissgrid):
    fA, fB = fSwissgrid
    assert fA[0] > 2000000
    assert fB[0] > 2000000
    assert 1000000 < fA[1] < 2000000
    assert 1000000 < fB[1] < 2000000
    assert fA[0] < fB[0] # lon
    assert fA[1] > fB[1] # lat


@dataclass
class LayerParams:
    iMasstab: int
    iBaseLayer: int
    iABaseTiles: List[int]
    iATilePixels: List[int]
    fASwissgrid: List[float]
    iBBaseTiles: List[int]
    iBTilePixels: List[int]
    fBSwissgrid: List[float]


listLayers = (
    LayerParams(
        iMasstab=5000000,
        iBaseLayer=15,
        # Chaumont
        iABaseTiles=(0, 0),
        iATilePixels=(65, 192),
        fASwissgrid=(2452000.0, 1254750.0),
        # Verona
        iBBaseTiles=(3, 2),
        iBTilePixels=(88, 98),
        fBSwissgrid=(2848500.0, 1045250.1),
    ),
    LayerParams(
        iMasstab=2000000,
        iBaseLayer=16,
        # Chaumont
        iABaseTiles=(0, 0),
        iATilePixels=(0, 0),
        fASwissgrid=(2420000.0, 1350250.0),
        # Verona
        iBBaseTiles=(7, 4),
        iBTilePixels=(128, 256),
        fBSwissgrid=(2900000.0, 1030750.0),
    ),
    LayerParams(
        iMasstab=1000000,
        iBaseLayer=17,
        # Chaumont
        iABaseTiles=(0, 0),
        iATilePixels=(0, 0),
        fASwissgrid=(2420000.0, 1350300.0),
        # Verona
        iBBaseTiles=(18, 12),
        iBTilePixels=(0, 0),
        fBSwissgrid=(2880900.0, 1042900.0),
    ),
    LayerParams(
        iMasstab=500000,
        iBaseLayer=18,
        # Chaumont
        iABaseTiles=(4, 3),
        iATilePixels=(177, 192),
        fASwissgrid=(2480000.0, 1302000.0),
        # Verona
        iBBaseTiles=(34, 22),
        iBTilePixels=(0, 0),
        fBSwissgrid=(2855300.0, 1068400.0),
    ),
    LayerParams(
        iMasstab=200000,
        iBaseLayer=19,
        # Chaumont
        iABaseTiles=(8, 6),
        iATilePixels=(113, 175),
        fASwissgrid=(2463200.0, 1315800.0),
        # Verona
        iBBaseTiles=(83, 58),
        iBTilePixels=(93, 243),
        fBSwissgrid=(2846760.0, 1048220.0),
    ),
    LayerParams(
        iMasstab=100000,
        iBaseLayer=20,
        # Chaumont
        iABaseTiles=(50, 18),
        iATilePixels=(200, 193),
        fASwissgrid=(2550000.0, 1302000.0),
        # Verona
        iBBaseTiles=(132, 112),
        iBTilePixels=(207, 128),
        fBSwissgrid=(2760000.0, 1062000.0),
    ),
    LayerParams(
        iMasstab=50000,
        iBaseLayer=21,
        # Chaumont
        iABaseTiles=(101, 56),
        iATilePixels=(144, 64),
        fASwissgrid=(2550000.0, 1278000.0),
        # Verona
        iBBaseTiles=(265, 224),
        iBTilePixels=(159, 255),
        fBSwissgrid=(2760000.0, 1062000.0),
    ),
    LayerParams(
        iMasstab=25000,
        iBaseLayer=22,
        # Chaumont
        iABaseTiles=(203, 131),
        iATilePixels=(33, 64),
        fASwissgrid=(2550000.0, 1266000.0),
        # Verona
        iBBaseTiles=(613, 356),
        iBTilePixels=(72, 64),
        fBSwissgrid=(2812500.0, 1122000.0),
    ),
    LayerParams(
        iMasstab=10000,
        iBaseLayer=25,
        # Chaumont
        iABaseTiles=(574, 347),
        iATilePixels=(55, 168),
        fASwissgrid=(2567000.0, 1261000.0),
        # Verona
        iBBaseTiles=(1195, 1046),
        iBTilePixels=(80, 225),
        fBSwissgrid=(2726000.0, 182000.0),
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

"""
  http://www.swisstopo.ch/data/geo/naeherung_d.pdf
  http://www.swisstopo.ch/data/geo/refsysd.pdf

                  SwissGrid ???	 WGS 84
                  N    E
  Meilen          691  237       47.26954 8.64375
  Hombrechtikon   700  234       47.25052 8.76696
"""
def transformCH1903_to_WGS84(fLon, fLat):
    """
    E entspricht Lambda (8.x), y (7xx)
    N entspricht Phi (46.x), x (2xx)
    """
    assert isinstance(fLat, float)
    assert isinstance(fLon, float)
    assert fLon > LON_OFFSET
    assert LAT_OFFSET < fLat < LON_OFFSET
    fLat -= LAT_OFFSET
    fLon -= LON_OFFSET

    y = (fLon - LAT_BERN) / 1000000.0
    x = (fLat - LON_BERN) / 1000000.0
    fLambda = 2.6779094 + 4.728982 * y + 0.791484 * y * x + 0.1306 * y * x * x - 0.0436 * y * y * y
    fPhi = 16.9023892 + 3.238272 * x - 0.270978 * y * y - 0.002528 * x * x - 0.0447 * y * y * x - 0.0140 * x * x * x
    return fLambda * 100.0 / 36.0, fPhi * 100.0 / 36.0


def CH1903_to_WGS84(a):
    return transformCH1903_to_WGS84(a[LON], a[LAT])


def add(a, b):
    if not isinstance(a, collections.Iterable):
        a = (a, a)
    if not isinstance(b, collections.Iterable):
        b = (b, b)
    return a[0] + b[0], a[1] + b[1]


def diff(a, b):
    if not isinstance(a, collections.Iterable):
        a = (a, a)
    if not isinstance(b, collections.Iterable):
        b = (b, b)
    return a[0] - b[0], a[1] - b[1]


def mult(a, b):
    if not isinstance(a, collections.Iterable):
        a = (a, a)
    if not isinstance(b, collections.Iterable):
        b = (b, b)
    return (a[0] * b[0], a[1] * b[1])


def div(a, b):
    if not isinstance(a, collections.Iterable):
        a = a, a
    if not isinstance(b, collections.Iterable):
        b = b, b
    return float(a[0]) / b[0], float(a[1]) / b[1]


def floor(a):
    return int(math.floor(a[0])), int(math.floor(a[1]))


def ceil(a):
    return -int(math.floor(-a[0])), -int(math.floor(-a[1]))


def min_(a, b):
    if not isinstance(a, collections.Iterable):
        a = a, a
    if not isinstance(b, collections.Iterable):
        b = b, b
    return min(a[0], b[0]), min(a[1], b[1])


def max_(a, b):
    if not isinstance(a, collections.Iterable):
        a = a, a
    if not isinstance(b, collections.Iterable):
        b = b, b
    return max(a[0], b[0]), max(a[1], b[1])


# a is north west of b
def assertSwissgridIsNorthWest(a, b):
    assert a[0] < b[0]
    assert a[1] > b[1]


# a is north west of b
def assertTilesIsNorthWest(a, b):
    assert a[0] < b[0]
    assert a[1] < b[1]


# a is north west of b
def assertPixelsIsNorthWest(a, b):
    assert a[0] < b[0]
    assert a[1] < b[1]


def assertWGS84IsNorthWest(a, b):
    assert a[LON] < b[LON]
    assert a[LAT] > b[LON]


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

    def createLayerPlusMinus(self, iMasstab, fTargetCenterSwissgrid, fTargetSizeM):
        fRSwissgrid = add(fTargetCenterSwissgrid, (-fTargetSizeM, fTargetSizeM))
        fSSwissgrid = add(fTargetCenterSwissgrid, (fTargetSizeM, -fTargetSizeM))
        assertSwissgridIsNorthWest(fRSwissgrid, fSSwissgrid)
        self.createLayer(None, iMasstab, (fRSwissgrid, fSSwissgrid))

    def createLayer(self, img, iMasstab, l):
        assertOrientation(l)
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
        assertSwissgridIsNorthWest(fASwissgrid, fBSwissgrid)
        self.fASwissgrid, self.fBSwissgrid = fASwissgrid, fBSwissgrid
        self.objLayerParams: LayerParams = self.findLayer(iMasstab)
        self.strFolderCacheTiles = strFOLDER_CACHE_TILES / f"{self.objLayerParams.iBaseLayer}"
        if not self.strFolderCacheTiles.exists():
            self.strFolderCacheTiles.mkdir(parents=True, exist_ok=True)

        listFiles = os.listdir(self.strFolderCacheTiles)
        listFiles = filter(lambda filename: filename.endswith(".jpg"), listFiles)
        self.setTilesFiles = set(listFiles)

        for layerParam in listLayers:
            assertSwissgridIsNorthWest(layerParam.fASwissgrid, layerParam.fBSwissgrid)
            assertTilesIsNorthWest(layerParam.iABaseTiles, layerParam.iBBaseTiles)

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
        assertOrientation((fUSwissgrid_, fVSwissgrid_))

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
        #
        # Aufgrund der Referenzpunkte A und B bestimmen:
        # fBaseSwissgrid: Koordinaten oben/links von Base
        # fMPerPixel: M pro Pixel
        #
        # fABasePixels = add(mult(iTILE_SIZE, self.objLayerParams.iABaseTiles), self.objLayerParams.iATilePixels)
        # fBBasePixels = add(mult(iTILE_SIZE, self.objLayerParams.iBBaseTiles), self.objLayerParams.iBTilePixels)

        # fMPerPixel = div(diff(self.objLayerParams.fBSwissgrid, self.objLayerParams.fASwissgrid), diff(fBBasePixels, fABasePixels))
        # assert fMPerPixel[0] > 0.0
        # assert fMPerPixel[1] < 0.0
        # torsion = (fMPerPixel[0] + fMPerPixel[1]) / fMPerPixel[0]
        # assert torsion < 0.01

        # # BaseSwissgrid ist oben/links.
        # fBaseSwissgrid = diff(self.objLayerParams.fASwissgrid, mult(fMPerPixel, fABasePixels))
        # assert fBaseSwissgrid[0] > 0.0
        # assert fBaseSwissgrid[1] > 0.0

        #
        # Bestimmen, auf welchen Tiles die zu erstellende Karte (Target)
        # zu liegen kommt.
        # Die Punkte Bl und Tr werden bestimmt in den Koordinatensystemen
        # iBlBasePixel: Pixel
        # fBlSwissgrid: Swissgrid
        # fBlWGS84: WGS84
        #
        # fRBasePixels = div(diff(self.fRSwissgrid, fBaseSwissgrid), fMPerPixel)
        # fSBasePixels = div(diff(self.fSSwissgrid, fBaseSwissgrid), fMPerPixel)
        # assertPixelsIsNorthWest(fRBasePixels, fSBasePixels)

        # iTlBaseTiles = floor(div(fRBasePixels, iTILE_SIZE))
        # iBrBaseTiles = ceil(div(fSBasePixels, iTILE_SIZE))
        # assertTilesIsNorthWest(iTlBaseTiles, iBrBaseTiles)

        # iTlBasePixel = mult(iTlBaseTiles, iTILE_SIZE)
        # iBrBasePixel = mult(iBrBaseTiles, iTILE_SIZE)
        # assertPixelsIsNorthWest(iTlBasePixel, iBrBasePixel)

        # fTlSwissgrid = add(mult(iTlBasePixel, fMPerPixel), fBaseSwissgrid)
        # fBrSwissgrid = add(mult(iBrBasePixel, fMPerPixel), fBaseSwissgrid)
        # assertSwissgridIsNorthWest(fTlSwissgrid, fBrSwissgrid)

        # fTlWGS84 = CH1903_to_WGS84(fTlSwissgrid)
        # fBrWGS84 = CH1903_to_WGS84(fBrSwissgrid)
        # fBlWGS84 = CH1903_to_WGS84((fTlSwissgrid[0], fBrSwissgrid[1]))
        # fTrWGS84 = CH1903_to_WGS84((fBrSwissgrid[0], fTlSwissgrid[1]))
        fTlWGS84 = CH1903_to_WGS84(self.fASwissgrid)
        fBrWGS84 = CH1903_to_WGS84(self.fBSwissgrid)
        fBlWGS84 = CH1903_to_WGS84((self.fASwissgrid[LON], self.fBSwissgrid[LAT]))
        fTrWGS84 = CH1903_to_WGS84((self.fBSwissgrid[LON], self.fASwissgrid[LAT]))
        assertWGS84IsNorthWest(fTlWGS84, fBrWGS84)

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

        assertWGS84IsNorthWest(fTlWGS84, fBrWGS84)

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

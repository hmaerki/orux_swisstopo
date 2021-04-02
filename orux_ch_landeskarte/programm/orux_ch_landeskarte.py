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
http://www.swisstopo.admin.ch/internet/swisstopo/de/home/topics/survey/sys/refsys/projection.html
  Schweizerische Kartenprojektionen
http://www.swisstopo.admin.ch/internet/swisstopo/de/home/apps/calc/navref.html
  Umrechnung von Schweizer Landeskoordinaten in ellipsoidische WGS84-Koordinaten
http://de.wikipedia.org/wiki/WGS_84
  World Geodetic System 1984 (WGS 84)
http://www.ahnungslos.ch/android-screenshots-in-5-schritten/
  Android Screen Capture
"""
import io
import time
import shutil
import pathlib
import sqlite3
from dataclasses import dataclass

import requests
import PIL.Image
import rasterio

from programm import projection
from programm.projection import CH1903, BoundsCH1903
from programm.context import Context

fSwissgridSchweiz = (480000.0, 60000.0), (865000.0, 302000.0)


strFOLDER_ORUX_CH_LANDESKARTE = pathlib.Path(__file__).absolute().parent.parent
strFOLDER_BASE = strFOLDER_ORUX_CH_LANDESKARTE.parent
strFOLDER_CACHE = strFOLDER_BASE / "orux_ch_landeskarte_cache"
strFOLDER_MAPS = strFOLDER_BASE / "orux_ch_landeskarte_maps"
strFOLDER_RESOURCES = strFOLDER_ORUX_CH_LANDESKARTE / "resources"

strFOLDER_CACHE.mkdir(exist_ok=True)
strFOLDER_MAPS.mkdir(exist_ok=True)
assert strFOLDER_MAPS.exists()

PIL.Image.MAX_IMAGE_PIXELS = None


@dataclass
class LayerParams:
    iMasstab: int
    iBaseLayer: int
    strTiffFilename: str = None

    @property
    def name(self):
        return f"{self.iMasstab:04d}"

    @property
    def folder_resources(self):
        return strFOLDER_RESOURCES / self.name

    @property
    def folder_cache(self):
        return strFOLDER_CACHE / self.name

    @property
    def filename_url_tiffs(self):
        return self.folder_resources / "url_tiffs.txt"


listLayers = (
    # LayerParams(
    #     iMasstab=5000,
    #     iBaseLayer=15,
    # ),
    # LayerParams(
    #     iMasstab=2000,
    #     iBaseLayer=16,
    # ),
    LayerParams(iMasstab=1000, iBaseLayer=17, strTiffFilename="SMR1000_KREL.tif"),
    LayerParams(iMasstab=500, iBaseLayer=18, strTiffFilename="SMR500_KREL.tif"),
    LayerParams(
        iMasstab=200,
        iBaseLayer=19,
    ),
    LayerParams(
        iMasstab=100,
        iBaseLayer=20,
    ),
    LayerParams(
        iMasstab=50,
        iBaseLayer=21,
    ),
    LayerParams(
        iMasstab=25,
        iBaseLayer=22,
    ),
    LayerParams(
        iMasstab=10,
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


class OruxMap:
    def __init__(self, strMapName, context):
        assert isinstance(context, Context)
        self.strMapName = strMapName
        self.context = context
        self.strMapFolder = strFOLDER_MAPS / strMapName

        print("===== ", self.strMapName)

        if self.strMapFolder.exists():
            shutil.rmtree(self.strMapFolder)
            time.sleep(1.0)
        self.strMapFolder.mkdir(parents=True, exist_ok=True)

        strFilenameSqlite = self.strMapFolder / "OruxMapsImages.db"
        if strFilenameSqlite.exists():
            strFilenameSqlite.unlink()
        self.db = sqlite3.connect(strFilenameSqlite)
        self.db.execute("""CREATE TABLE tiles (x int, y int, z int, image blob, PRIMARY KEY (x,y,z))""")
        self.db.execute("""CREATE TABLE android_metadata (locale TEXT)""")
        self.db.execute("""INSERT INTO "android_metadata" VALUES ("de_CH");""")

        self.fXml = (self.strMapFolder / f"{strMapName}.otrk2.xml").open("w")
        self.fXml.write(strTemplateMainStart.format(strMapName=strMapName))

    def createLayers(self, iMasstabMin: int = 25, iMasstabMax: int = 500):
        for layerParam in listLayers:
            if iMasstabMin <= layerParam.iMasstab <= iMasstabMax:
                self.createLayer(layerParam=layerParam)

    def createLayer(self, layerParam):
        objLayer2 = Layer2(self, layerParam)
        objLayer2.downloadTiffs()
        objLayer2.createMap()

    # def createLayer_(self, img, iMasstab, boundsCH1903: BoundsCH1903):
    #     assert isinstance(boundsCH1903, BoundsCH1903)
    #     objLayer = Layer(self, img, iMasstab, boundsCH1903)
    #     objLayer.create()

    def done(self):
        self.fXml.write(strTemplateMainEnd)
        self.fXml.close()

        self.db.commit()
        self.db.close()
        print("----- Fertig")
        print(f'Die Karte liegt nun bereit im Ordner "{self.strMapName}".')
        print("Dieser Ordner muss jetzt 'von Hand' in den Ordner \"oruxmaps\\mapfiles\" kopiert werden.")
        # sys.stdin.readline()


class Layer2:
    def __init__(self, oruxMaps, layerParam):
        self.oruxMaps = oruxMaps
        self.layerParam = layerParam
        assert self.layerParam.folder_resources.exists()

    @property
    def _tiffs(self):
        if self.layerParam.strTiffFilename:
            # For big scales, the image is stored in git
            yield self.layerParam.folder_resources / self.layerParam.strTiffFilename
            return

        filename_url_tiffs = self.layerParam.folder_resources / "url_tiffs.txt"
        yield from self._download_tiffs(filename_url_tiffs)

    def _download_tiffs(self, filename_url_tiffs):
        assert filename_url_tiffs.exists()
        self.layerParam.folder_cache.mkdir(exist_ok=True)
        with self.layerParam.filename_url_tiffs.open("r") as f:
            for url in sorted(f.readlines()):
                url = url.strip()
                name = url.split("/")[-1]
                filename = self.layerParam.folder_cache / name
                if self.oruxMaps.context.only_tiffs is not None:
                    if filename.name not in self.oruxMaps.context.only_tiffs:
                        continue
                if not filename.exists():
                    print(f"Downloading {filename.relative_to(strFOLDER_BASE)}")
                    r = requests.get(url)
                    filename.write_bytes(r.content)
                yield filename

    def downloadTiffs(self):
        for filename in self._tiffs:
            pass

    def createMap(self):
        tiffs = list(self._tiffs)
        for i, filename in enumerate(tiffs):
            with rasterio.open(filename, "r") as dataset:
                if dataset.crs is None:
                    print(f"WARNING: No position found in {filename.relative_to(strFOLDER_ORUX_CH_LANDESKARTE)}")
                    continue
                boundsCH1903 = BoundsCH1903(CH1903(dataset.bounds.left, dataset.bounds.top), CH1903(dataset.bounds.right, dataset.bounds.bottom))
                with PIL.Image.open(filename) as img:
                    strLabel = f"{filename.relative_to(strFOLDER_BASE)} {i}({len(tiffs)})"
                    objLayer = Layer(objOrux=self.oruxMaps, strLabel=strLabel, img=img, iMasstab=self.layerParam.iMasstab, boundsCH1903=boundsCH1903)
                    objLayer.create()


class Layer:
    def __init__(self, objOrux, img, strLabel, iMasstab, boundsCH1903: BoundsCH1903):  # pylint: disable=too-many-arguments
        # TODO
        assert img is not None
        self.objOrux = objOrux
        self.img = img
        self.iMasstab = iMasstab
        self.strLabel = strLabel
        projection.assertSwissgridIsNorthWest(boundsCH1903)
        self.boundsCH1903 = boundsCH1903
        self.objLayerParams: LayerParams = self.findLayer(iMasstab)

    def findLayer(self, iMasstab) -> LayerParams:
        for layerParam in listLayers:
            if layerParam.iMasstab == iMasstab:
                return layerParam
        raise Exception(f"Layer mit Masstab {iMasstab} existiert nicht.")

    def is_white_data(self, image_data):
        if len(image_data) > 1000:
            return False
        imTile = PIL.Image.open(io.BytesIO(image_data))
        extrema = imTile.convert("L").getextrema()
        white = extrema == (255, 255)
        del imTile
        return white

    def _save_purge_palette(self, fOut, img):
        if self.objOrux.context.skip_optimize_png:
            img.save(fOut, format="PNG")
            return

        img = img.convert("RGB")

        # TODO: Go through the color palette and prune similar colors
        threshold = 10
        data = list(img.getdata())
        for i, v in enumerate(data):
            if sum(v) < threshold:
                data[i] = (0, 0, 0)
        img.putdata(data)

        img = img.convert("P", palette=PIL.Image.ADAPTIVE)
        # Now the palette is reordered: At the beginning are used colors
        colors = -1
        for v in img.histogram():
            if v > 0:
                colors += 1
        bits = colors.bit_length()
        # Only store the part of the palette which is used
        img.save(fOut, format="PNG", optimize=True, compress_level=9, bits=bits)

    def extractTile(self, x, y):
        im_crop = self.img.crop((x * iTILE_SIZE, y * iTILE_SIZE, (x + 1) * iTILE_SIZE, (y + 1) * iTILE_SIZE))
        fOut = io.BytesIO()
        self._save_purge_palette(fOut, im_crop)
        return fOut.getvalue()

    def create(self):  # pylint: disable=too-many-statements,too-many-branches
        boundsWGS84 = self.boundsCH1903.to_WGS84()

        #
        # Die Tiles fuer die Karte zusammenkopieren
        #
        xCount = self.img.width // iTILE_SIZE
        yCount = self.img.height // iTILE_SIZE
        total = self.objOrux.context.skip_count(xCount) * self.objOrux.context.skip_count(yCount)
        start_s = time.perf_counter()
        size = 0
        count = 0
        for y in range(yCount):
            if self.objOrux.context.skip_border(i=y, count=yCount):
                continue
            for x in range(xCount):
                if self.objOrux.context.skip_border(i=x, count=xCount):
                    continue
                rawImagedata = self.extractTile(x, y)
                size += len(rawImagedata)
                b = sqlite3.Binary(rawImagedata)
                self.objOrux.db.execute("insert or replace into tiles values (?,?,?,?)", (x, y, self.objLayerParams.iBaseLayer - iLAYER_OFFSET, b))
                count += 1
            ms_per_tile = 1000.0 * (time.perf_counter() - start_s) / count
            print(f"{self.strLabel}. Image {count}({total}). Per tile: {ms_per_tile:0.0f}ms {size/count/1000:0.1f}kbytes")

        f = self.objOrux.fXml

        f.write(
            strTemplateLayerBegin.format(
                iTILE_SIZE=iTILE_SIZE,
                strMapName=self.objOrux.strMapName,
                id=self.objLayerParams.iBaseLayer - iLAYER_OFFSET,
                xMax=xCount,
                yMax=yCount,
                height=yCount * iTILE_SIZE,
                width=xCount * iTILE_SIZE,
                minLat=boundsWGS84.southEast.lat,
                maxLat=boundsWGS84.northWest.lat,
                minLon=boundsWGS84.northWest.lon,
                maxLon=boundsWGS84.southEast.lon,
            )
        )
        for strPoint, lon, lat in (
            ("TL", boundsWGS84.northWest.lon, boundsWGS84.northWest.lat),
            ("BR", boundsWGS84.southEast.lon, boundsWGS84.southEast.lat),
            ("TR", boundsWGS84.northEast.lon, boundsWGS84.northEast.lat),
            ("BL", boundsWGS84.southWest.lon, boundsWGS84.southWest.lat),
        ):
            f.write(f'          <CalibrationPoint corner="{strPoint}" lon="{lon:2.6f}" lat="{lat:2.6f}" />\n')

        f.write(strTemplateLayerEnd)


# if False:
#     oruxmap = OruxMap("Hombrechtikon")
#     for iBaseLayer in (22,):
#         oruxmap.createLayerPlusMinus(iBaseLayer, (701000.0, 235000.0), 4000.0)

# if False:
#     oruxmap = OruxMap("Hombrechtikon")
#     for iBaseLayer in (17, 18, 19):
#         oruxmap.createLayerPlusMinus(iBaseLayer, (701000.0, 235000.0), 10000.0)
#     for iBaseLayer in (20, 21, 22):
#         oruxmap.createLayerPlusMinus(iBaseLayer, (701000.0, 235000.0), 4000.0)

# if False:
#     oruxmap = OruxMap("RefBl")
#     for iBaseLayer in (22,):  # (17, 18, 19, 20, 21, 22):
#         oruxmap.createLayerPlusMinus(iBaseLayer, (481000.0, 110000.0), 2000.0)

#     oruxmap = OruxMap("RefTr")
#     for iBaseLayer in (22,):  # (17, 18, 19, 20, 21, 22):
#         oruxmap.createLayerPlusMinus(iBaseLayer, (776000.0, 276000.0), 2000.0)

# if False:
#     oruxmap = OruxMap("RefLuetzel")
#     for iBaseLayer in (16,):
#         oruxmap.createLayerPlusMinus(iBaseLayer, (700000.0, 236000.0), 2000.0)

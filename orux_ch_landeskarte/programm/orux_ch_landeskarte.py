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
from programm.projection import CH1903, BoundsCH1903, create_boundsCH1903_extrema
from programm.context import Context

fSwissgridSchweiz = (480000.0, 60000.0), (865000.0, 302000.0)


DIRECTORY_ORUX_CH_LANDESKARTE = pathlib.Path(__file__).absolute().parent.parent
DIRECTORY_BASE = DIRECTORY_ORUX_CH_LANDESKARTE.parent
DIRECTORY_CACHE = DIRECTORY_BASE / "orux_ch_landeskarte_cache"
DIRECTORY_MAPS = DIRECTORY_BASE / "orux_ch_landeskarte_maps"
DIRECTORY_RESOURCES = DIRECTORY_ORUX_CH_LANDESKARTE / "resources"

DIRECTORY_CACHE.mkdir(exist_ok=True)
DIRECTORY_MAPS.mkdir(exist_ok=True)
assert DIRECTORY_MAPS.exists()

PIL.Image.MAX_IMAGE_PIXELS = None


@dataclass
class LayerParams:
    scale: int
    orux_layer: int
    m_per_pixel: float
    tiff_filename: str = None

    @property
    def name(self):
        return f"{self.scale:04d}"

    @property
    def folder_resources(self):
        return DIRECTORY_RESOURCES / self.name

    @property
    def folder_cache(self):
        return DIRECTORY_CACHE / self.name

    @property
    def filename_url_tiffs(self):
        return self.folder_resources / "url_tiffs.txt"

    def verify_m_per_pixel(self, imageTiff):
        assert isinstance(imageTiff, ImageTiff)
        assert abs((imageTiff.m_per_pixel_lon / self.m_per_pixel) - 1.0) < 0.01
        assert abs((imageTiff.m_per_pixel_lat / self.m_per_pixel) - 1.0) < 0.01


LIST_LAYERS = (
    # LayerParams(
    #     scale=5000,
    #     orux_layer=8,
    # ),
    # LayerParams(
    #     scale=2000,
    #     orux_layer=8,
    # ),
    LayerParams(scale=1000, orux_layer=10, tiff_filename="SMR1000_KREL.tif", m_per_pixel=1.0),
    LayerParams(scale=500, orux_layer=11, tiff_filename="SMR500_KREL.tif", m_per_pixel=1.0),
    LayerParams(scale=200, orux_layer=12, m_per_pixel=10.0),
    LayerParams(scale=100, orux_layer=13, m_per_pixel=1.0),
    LayerParams(scale=50, orux_layer=14, m_per_pixel=1.0),
    LayerParams(scale=25, orux_layer=15, m_per_pixel=1.0),
    LayerParams(scale=10, orux_layer=16, m_per_pixel=1.0),
)

TEMPLATE_LAYER_BEGIN = """    <OruxTracker xmlns="http://oruxtracker.com/app/res/calibration" versionCode="2.1">
      <MapCalibration layers="false" layerLevel="{id}">
        <MapName><![CDATA[{map_name} {id:d}]]></MapName>
        <MapChunks xMax="{xMax}" yMax="{yMax}" datum="CH-1903:Swiss@WGS 1984:Global Definition" projection="(SUI) Swiss Grid" img_height="{TILE_SIZE}" img_width="{TILE_SIZE}" file_name="{map_name}" />
        <MapDimensions height="{height}" width="{width}" />
        <MapBounds minLat="{minLat:2.6f}" maxLat="{maxLat:2.6f}" minLon="{minLon:2.6f}" maxLon="{maxLon:2.6f}" />
        <CalibrationPoints>
"""

TEMPLATE_LAYER_END = """        </CalibrationPoints>
      </MapCalibration>
    </OruxTracker>
"""


TEMPLATE_MAIN_START = """<?xml version="1.0" encoding="UTF-8"?>
<OruxTracker xmlns="http://oruxtracker.com/app/res/calibration" versionCode="3.0">
  <MapCalibration layers="true" layerLevel="0">
    <MapName><![CDATA[{map_name}]]></MapName>
"""

TEMPLATE_MAIN_END = """  </MapCalibration>
</OruxTracker>"""

# Wir unterstützen im Moment nur eine Tile-Grösse:
TILE_SIZE = 400

class SkipException(Exception):
    pass


class OruxMap:
    def __init__(self, map_name, context):
        assert isinstance(context, Context)
        self.map_name = map_name
        self.context = context
        self.directory_map = DIRECTORY_MAPS / map_name

        print("===== ", self.map_name)

        if self.directory_map.exists():
            shutil.rmtree(self.directory_map)
            time.sleep(1.0)
        self.directory_map.mkdir(parents=True, exist_ok=True)

        strFilenameSqlite = self.directory_map / "OruxMapsImages.db"
        if strFilenameSqlite.exists():
            strFilenameSqlite.unlink()
        self.db = sqlite3.connect(strFilenameSqlite)
        self.db.execute("""CREATE TABLE tiles (x int, y int, z int, image blob, PRIMARY KEY (x,y,z))""")
        self.db.execute("""CREATE TABLE android_metadata (locale TEXT)""")
        self.db.execute("""INSERT INTO "android_metadata" VALUES ("de_CH");""")

        self.fXml = (self.directory_map / f"{map_name}.otrk2.xml").open("w")
        self.fXml.write(TEMPLATE_MAIN_START.format(map_name=map_name))

    def __enter__(self):
        return self

    def __exit__(self, _type, value, tb):
        self.fXml.write(TEMPLATE_MAIN_END)
        self.fXml.close()

        self.db.commit()
        self.db.close()
        print("----- Fertig")
        print(f'Die Karte liegt nun bereit im Ordner "{self.directory_map.relative_to(DIRECTORY_BASE)}".')
        print("Dieser Ordner muss jetzt 'von Hand' in den Ordner \"oruxmaps\\mapfiles\" kopiert werden.")

    def createLayers(self, iMasstabMin: int = 25, iMasstabMax: int = 500):
        for layerParam in LIST_LAYERS:
            if iMasstabMin <= layerParam.scale <= iMasstabMax:
                self.createLayer(layerParam=layerParam)

    def createLayer(self, layerParam):
        try:
            objLayer2 = MapScale(self, layerParam)
        except SkipException as ex:
            print(f"SKIPPED: {ex}")
            return
        objLayer2.createMap()


class MapScale:
    """
    This object represents one scale. For example 1:25'000, 1:50'000.
    """

    def __init__(self, oruxMaps, layerParam):
        self.oruxMaps = oruxMaps
        self.layerParam = layerParam
        assert self.layerParam.folder_resources.exists()

        self.imageTiffs = []
        for filename in self._tiffs:
            try:
                imageTiff = ImageTiff(objMapScale=self, filename=filename)
                self.imageTiffs.append(imageTiff)
            except SkipException as ex:
                print(f"SKIPPED: {ex}")
                continue

        if len(self.imageTiffs) == 0:
            raise SkipException(f"No valid tiff for this scale {self.layerParam.scale} found")

        self.boundsCH1903_extrema = create_boundsCH1903_extrema()
        for imageTiff in self.imageTiffs:
            self.layerParam.verify_m_per_pixel(imageTiff)
            self.boundsCH1903_extrema.extend(imageTiff.boundsCH1903)
        print(f'{self.layerParam.scale}: {len(self.imageTiffs)}tif {self.boundsCH1903_extrema.lon_m/1000.0:0.3f}x{self.boundsCH1903_extrema.lat_m/1000.0:0.3f}km')

        width_pixel = int(self.boundsCH1903_extrema.lon_m/self.layerParam.m_per_pixel)
        height_pixel = int(self.boundsCH1903_extrema.lat_m/self.layerParam.m_per_pixel)
        # assert width_pixel % TILE_SIZE == 0
        # assert height_pixel % TILE_SIZE == 0

        boundsWGS84 = self.boundsCH1903_extrema.to_WGS84()

        f = self.oruxMaps.fXml

        f.write(
            TEMPLATE_LAYER_BEGIN.format(
                TILE_SIZE=TILE_SIZE,
                map_name=self.oruxMaps.map_name,
                id=self.layerParam.orux_layer,
                xMax=width_pixel // TILE_SIZE,
                yMax=height_pixel // TILE_SIZE,
                height=height_pixel,
                width=width_pixel,
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

        f.write(TEMPLATE_LAYER_END)

    @property
    def _tiffs(self):
        if self.layerParam.tiff_filename:
            # For big scales, the image is stored in git
            yield self.layerParam.folder_resources / self.layerParam.tiff_filename
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
                    print(f"Downloading {filename.relative_to(DIRECTORY_BASE)}")
                    r = requests.get(url)
                    filename.write_bytes(r.content)
                yield filename

    def downloadTiffs(self):
        for filename in self._tiffs:
            pass

    def createMap(self):
        tiffs = list(self._tiffs)
        for i, filename in enumerate(tiffs):
            try:
                imageTiff = ImageTiff(objMapScale=self, filename=filename)
            except SkipException:
                continue
            label = f"{filename.relative_to(DIRECTORY_BASE)} {i}({len(tiffs)})"
            imageTiff.create(label=label)


class ImageTiff:
    def __init__(self, objMapScale, filename):
        self.oruxMaps = objMapScale.oruxMaps
        self.filename = filename
        self.scale = objMapScale
        self.context = self.oruxMaps.context
        self.layerParam = objMapScale.layerParam
        with rasterio.open(filename, "r") as dataset:
            if dataset.crs is None:
                raise SkipException(f"No position found in {filename.relative_to(DIRECTORY_ORUX_CH_LANDESKARTE)}")
            boundsCH1903 = BoundsCH1903(CH1903(dataset.bounds.left, dataset.bounds.top), CH1903(dataset.bounds.right, dataset.bounds.bottom))
            self.m_per_pixel_lon = boundsCH1903.lon_m / dataset.shape[1]
            self.m_per_pixel_lat = boundsCH1903.lat_m / dataset.shape[0]
        projection.assertSwissgridIsNorthWest(boundsCH1903)
        self.boundsCH1903 = boundsCH1903

    def is_white_data(self, image_data):
        if len(image_data) > 1000:
            return False
        imTile = PIL.Image.open(io.BytesIO(image_data))
        extrema = imTile.convert("L").getextrema()
        white = extrema == (255, 255)
        del imTile
        return white

    def _save_purge_palette(self, fOut, img):
        if self.context.skip_optimize_png:
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

    def extractTile_obsolete(self, img, x, y):
        topleft_x = x * TILE_SIZE
        topleft_y = y * TILE_SIZE
        assert 0 <= topleft_x < img.width
        assert 0 <= topleft_y < img.height
        bottomright_x = topleft_x + TILE_SIZE
        bottomright_y = topleft_y + TILE_SIZE
        assert TILE_SIZE <= bottomright_x <= img.width
        assert TILE_SIZE <= bottomright_y <= img.height
        im_crop = img.crop((topleft_x, topleft_y, bottomright_x, bottomright_y))
        fOut = io.BytesIO()
        self._save_purge_palette(fOut, im_crop)
        return fOut.getvalue()

    def extractTile(self, img, topleft_x, topleft_y):
        assert 0 <= topleft_x < img.width
        assert 0 <= topleft_y < img.height
        bottomright_x = topleft_x + TILE_SIZE
        bottomright_y = topleft_y + TILE_SIZE
        assert TILE_SIZE <= bottomright_x <= img.width
        assert TILE_SIZE <= bottomright_y <= img.height
        im_crop = img.crop((topleft_x, topleft_y, bottomright_x, bottomright_y))
        fOut = io.BytesIO()
        self._save_purge_palette(fOut, im_crop)
        return fOut.getvalue()

    def create(self, label):  # pylint: disable=too-many-statements,too-many-branches
        x_base_pixel = int((self.boundsCH1903.a.lon - self.scale.boundsCH1903_extrema.a.lon) / self.layerParam.m_per_pixel)
        y_base_pixel = int((self.scale.boundsCH1903_extrema.a.lat - self.boundsCH1903.a.lat) / self.layerParam.m_per_pixel)
        assert x_base_pixel >= 0
        assert y_base_pixel >= 0
        x_offset_pixel = x_base_pixel % TILE_SIZE
        x_offset_tile = 0
        if x_offset_pixel != 0:
            x_offset_tile = 1
            print(f'WARNING: {self.filename.relative_to(DIRECTORY_BASE)}: odd offset x_offset_pixel={x_offset_pixel}px')
        y_offset_pixel = y_base_pixel % TILE_SIZE
        y_offset_tile = 0
        if y_base_pixel % TILE_SIZE != 0:
            y_offset_tile = 1
            print(f'WARNING: {self.filename.relative_to(DIRECTORY_BASE)}: odd offset y_offset_pixel={y_offset_pixel}px')
        x_base_tiles = (x_base_pixel-x_offset_pixel) // TILE_SIZE
        y_base_tiles = (y_base_pixel-y_offset_pixel) // TILE_SIZE

        if self.context.skip_png:
            return

        with PIL.Image.open(self.filename) as img:
            #
            # Die Tiles fuer die Karte zusammenkopieren
            #
            width = img.width-x_offset_pixel
            height = img.height-y_offset_pixel
            xCount = width // TILE_SIZE
            yCount = height // TILE_SIZE
            total = self.context.skip_count(xCount) * self.context.skip_count(yCount)
            start_s = time.perf_counter()
            size = 0
            count = 0
            for y in range(y_offset_tile, yCount):
                if self.context.skip_border(i=y, count=yCount):
                    continue
                for x in range(x_offset_tile, xCount):
                    if self.context.skip_border(i=x, count=xCount):
                        continue
                    rawImagedata = self.extractTile(img, x*TILE_SIZE-x_offset_pixel, y*TILE_SIZE-y_offset_pixel)
                    size += len(rawImagedata)
                    b = sqlite3.Binary(rawImagedata)
                    self.oruxMaps.db.execute("insert or replace into tiles values (?,?,?,?)", (x + x_base_tiles, y + y_base_tiles, self.layerParam.orux_layer, b))
                    count += 1
                ms_per_tile = 1000.0 * (time.perf_counter() - start_s) / count
                print(f"{label}. Image {count}({total}). Per tile: {ms_per_tile:0.0f}ms {size/count/1000:0.1f}kbytes")

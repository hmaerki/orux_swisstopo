#!/usr/bin/python
#
# Copyright (C) 2010-2021 Hans Maerk, Maerki Informatik
# License: Apache License v2
#
# Siehe http://www.maerki.com/hans/orux
#
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
https://www.swisstopo.admin.ch/de/wissen-fakten/geodaesie-vermessung/bezugsysteme/kartenprojektionen.html
  Schweizerische Kartenprojektionen
https://www.swisstopo.admin.ch/de/karten-daten-online/calculation-services/navref.html
https://www.swisstopo.admin.ch/content/swisstopo-internet/de/online/calculation-services/_jcr_content/contentPar/tabs/items/dokumente_und_publik/tabPar/downloadlist/downloadItems/8_1467103085694.download/refsys_d.pdf
  Umrechnung von Schweizer Landeskoordinaten in ellipsoidische WGS84-Koordinaten
http://de.wikipedia.org/wiki/WGS_84
  World Geodetic System 1984 (WGS 84)
"""
import io
import time
import shutil
import pathlib
import pickle
import sqlite3

from dataclasses import dataclass

import requests
import PIL.Image
import rasterio
import rasterio.plot

from oruxmap.utils import projection
from oruxmap.utils.projection import CH1903, BoundsCH1903, create_boundsCH1903_extrema
from oruxmap.utils.context import Context
from oruxmap.utils.orux_xml_otrk2 import OruxXmlOtrk2
from oruxmap.utils.download_zip_and_extract import DownloadZipAndExtractTiff

DIRECTORY_ORUX_SWISSTOPO = pathlib.Path(__file__).absolute().parent
DIRECTORY_RESOURCES = DIRECTORY_ORUX_SWISSTOPO / "resources"
DIRECTORY_BASE = DIRECTORY_ORUX_SWISSTOPO.parent
DIRECTORY_CACHE_TIF = DIRECTORY_BASE / "target_cache_tif"
DIRECTORY_CACHE_PNG = DIRECTORY_BASE / "target_cache_png"
DIRECTORY_LOGS = DIRECTORY_BASE / "target_logs"
DIRECTORY_MAPS = DIRECTORY_BASE / "target_maps"

DIRECTORY_CACHE_TIF.mkdir(exist_ok=True)
DIRECTORY_CACHE_PNG.mkdir(exist_ok=True)
DIRECTORY_LOGS.mkdir(exist_ok=True)
DIRECTORY_MAPS.mkdir(exist_ok=True)
assert DIRECTORY_MAPS.exists()

PIL.Image.MAX_IMAGE_PIXELS = None


@dataclass
class LayerParams:
    scale: int
    orux_layer: int
    m_per_pixel: float
    tiff_filename: str = None
    url: str = None
    align_CH1903: CH1903 = CH1903(lon=0.0, lat=0.0, valid_data=False)

    @property
    def name(self):
        return f"{self.scale:04d}"

    @property
    def folder_resources(self):
        return DIRECTORY_RESOURCES / self.name

    @property
    def folder_cache(self):
        return DIRECTORY_CACHE_TIF / self.name

    @property
    def filename_url_tiffs(self):
        return self.folder_resources / "url_tiffs.txt"

    @property
    def m_per_tile(self) -> float:
        return self.pixel_per_tile * self.m_per_pixel

    @property
    def pixel_per_tile(self) -> float:
        return 400

    def verify_m_per_pixel(self, tiff_images):
        assert isinstance(tiff_images, TiffImage)
        assert abs((tiff_images.m_per_pixel / self.m_per_pixel) - 1.0) < 0.001


LIST_LAYERS = (
    # LayerParams(
    #     scale=5000,
    #     orux_layer=8,
    # ),
    # LayerParams(
    #     scale=2000,
    #     orux_layer=8,
    #     m_per_pixel=32.0,
    # ),
    LayerParams(
        scale=1000,
        orux_layer=10,
        url='https://data.geo.admin.ch/ch.swisstopo.pixelkarte-farbe-pk1000.noscale/data.zip',
        tiff_filename="SMR1000_KREL.tif",
        m_per_pixel=50.0,
    ),
    LayerParams(
        scale=500,
        orux_layer=11,
        url='https://data.geo.admin.ch/ch.swisstopo.pixelkarte-farbe-pk500.noscale/data.zip',
        tiff_filename="SMR500_KREL.tif",
        m_per_pixel=25.0,
    ),
    LayerParams(
        scale=200,
        orux_layer=12,
        m_per_pixel=10.0,
        align_CH1903=CH1903(lon=3000.0, lat=2000.0, valid_data=False),
    ),
    LayerParams(scale=100, orux_layer=13, m_per_pixel=5.0),
    LayerParams(scale=50, orux_layer=14, m_per_pixel=2.5),
    LayerParams(scale=25, orux_layer=15, m_per_pixel=1.25),
    LayerParams(scale=10, orux_layer=16, m_per_pixel=0.5),
)


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

        filename_sqlite = self.directory_map / "OruxMapsImages.db"
        if filename_sqlite.exists():
            filename_sqlite.unlink()
        self.db = sqlite3.connect(filename_sqlite)
        self.db.execute(
            """CREATE TABLE tiles (x int, y int, z int, image blob, PRIMARY KEY (x,y,z))"""
        )
        self.db.execute("""CREATE TABLE android_metadata (locale TEXT)""")
        self.db.execute("""INSERT INTO "android_metadata" VALUES ("de_CH");""")

        self.xml_otrk2 = OruxXmlOtrk2(
            filename=self.directory_map / f"{map_name}.otrk2.xml", map_name=map_name
        )

    def __enter__(self):
        return self

    def __exit__(self, _type, value, tb):
        self.xml_otrk2.close()

        self.db.commit()
        self.db.close()
        print("----- Ready")
        print(
            f'The map now is ready in "{self.directory_map.relative_to(DIRECTORY_BASE)}".'
        )
        print(
            "This directory must be copied 'by Hans' onto your android into 'oruxmaps/mapfiles'."
        )

    def create_layers(self, iMasstabMin: int = 25, iMasstabMax: int = 500):
        start_s = time.perf_counter()
        for layer_param in LIST_LAYERS:
            if iMasstabMin <= layer_param.scale <= iMasstabMax:
                self._create_layer(layer_param=layer_param)
        print(f"Duration for this layer {time.perf_counter() - start_s:0.0f}s")

    def _create_layer(self, layer_param):
        map_scale = MapScale(self, layer_param)
        map_scale.create_map()


@dataclass
class DebugPng:
    tiff_filename: str
    x_tile: int
    y_tile: int
    x_tif_pixel: int
    y_tif_pixel: int

    @staticmethod
    def csv_header():
        return "tiff_filename,x_tile,y_tile,x_tif_pixel,y_tif_pixel"

    @property
    def csv(self):
        return f"{self.tiff_filename},{self.x_tile},{self.y_tile},{self.x_tif_pixel},{self.y_tif_pixel}"


class DebugLogger:
    def __init__(self, map_scale):
        self.map_scale = map_scale

    def report(self):
        def fopen(extension):
            filename_base = f"debug_log_{self.map_scale.layer_param.name}"
            filename = DIRECTORY_LOGS / (filename_base + extension)
            return filename.open("w")

        with fopen("_tiff.csv") as f:
            f.write(f"filename,{BoundsCH1903.csv_header('boundsCH1903')}\n")
            for tiff_image in self.map_scale.imageTiffs:
                bounds = tiff_image.boundsCH1903
                f.write(f"{tiff_image.filename.name},{tiff_image.boundsCH1903.csv}\n")
            f.write(f"all,{self.map_scale.boundsCH1903_extrema.csv}\n")

        with fopen("_png.csv") as f:
            f.write(
                f"{DebugPng.csv_header()},{BoundsCH1903.csv_header('boundsCH1903')}\n"
            )
            for tiff_image in self.map_scale.imageTiffs:
                for debug_png in tiff_image.debug_pngs:
                    f.write(f"{debug_png.csv},{tiff_image.boundsCH1903.csv}\n")


class MapScale:
    """
    This object represents one scale. For example 1:25'000, 1:50'000.
    """

    def __init__(self, orux_maps, layer_param):
        self.orux_maps = orux_maps
        self.layer_param = layer_param
        # self.tile_list = TileList()
        self.debug_logger = DebugLogger(self)
        assert self.layer_param.folder_resources.exists()

        self.imageTiffs = []
        for filename in self._tiffs:
            tiff_images = TiffImage(scale=self, filename=filename)
            self.imageTiffs.append(tiff_images)

        if len(self.imageTiffs) == 0:
            raise Exception(
                f"No valid tiff for this scale {self.layer_param.scale} found"
            )

        for tiff_images in self.imageTiffs:
            self.layer_param.verify_m_per_pixel(tiff_images)

        self.boundsCH1903_extrema = create_boundsCH1903_extrema()
        for tiff_images in self.imageTiffs:
            # Align the tiff and shrink it to complete tiles
            bounds_shrinkedCH1903 = tiff_images.boundsCH1903.minus(
                self.layer_param.align_CH1903
            )
            bounds_shrinkedCH1903.shrink_tilesize_m(self.layer_param.m_per_tile)
            bounds_shrinkedCH1903 = bounds_shrinkedCH1903.plus(
                self.layer_param.align_CH1903
            )
            self.boundsCH1903_extrema.extend(bounds_shrinkedCH1903)
            if False:
                print(
                    tiff_images.filename.name,
                    bounds_shrinkedCH1903.a.lon % self.layer_param.m_per_tile,
                    bounds_shrinkedCH1903.a.lat % self.layer_param.m_per_tile,
                    bounds_shrinkedCH1903.b.lon % self.layer_param.m_per_tile,
                    bounds_shrinkedCH1903.b.lat % self.layer_param.m_per_tile,
                )

        print(
            f"{self.layer_param.scale}: {len(self.imageTiffs)}tif {self.boundsCH1903_extrema.lon_m/1000.0:0.3f}x{self.boundsCH1903_extrema.lat_m/1000.0:0.3f}km"
        )

        width_pixel = int(
            self.boundsCH1903_extrema.lon_m / self.layer_param.m_per_pixel
        )
        height_pixel = int(
            self.boundsCH1903_extrema.lat_m / self.layer_param.m_per_pixel
        )
        # assert width_pixel % self.layer_param.pixel_per_tile == 0
        # assert height_pixel % self.layer_param.pixel_per_tile == 0

        boundsWGS84 = self.boundsCH1903_extrema.to_WGS84()

        self.orux_maps.xml_otrk2.write_layer(
            calib=boundsWGS84,
            TILE_SIZE=self.layer_param.pixel_per_tile,
            map_name=self.orux_maps.map_name,
            id=self.layer_param.orux_layer,
            xMax=width_pixel // self.layer_param.pixel_per_tile,
            yMax=height_pixel // self.layer_param.pixel_per_tile,
            height=height_pixel,
            width=width_pixel,
            minLat=boundsWGS84.southEast.lat,
            maxLat=boundsWGS84.northWest.lat,
            minLon=boundsWGS84.northWest.lon,
            maxLon=boundsWGS84.southEast.lon,
        )

    @property
    def _tiffs(self):
        if self.layer_param.tiff_filename:
            # For big scales, the image has to be extracted form a zip file
            tiff_filename = self.layer_param.folder_resources / self.layer_param.tiff_filename
            d = DownloadZipAndExtractTiff(url=self.layer_param.url, tiff_filename=tiff_filename)
            d.download()
            yield tiff_filename
            return

        filename_url_tiffs = self.layer_param.folder_resources / "url_tiffs.txt"
        yield from self._download_tiffs(filename_url_tiffs)

    def _download_tiffs(self, filename_url_tiffs):
        assert filename_url_tiffs.exists()
        self.layer_param.folder_cache.mkdir(exist_ok=True)
        with self.layer_param.filename_url_tiffs.open("r") as f:
            for url in sorted(f.readlines()):
                url = url.strip()
                name = url.split("/")[-1]
                filename = self.layer_param.folder_cache / name
                if self.orux_maps.context.only_tiffs is not None:
                    if filename.name not in self.orux_maps.context.only_tiffs:
                        continue
                if not filename.exists():
                    print(f"Downloading {filename.relative_to(DIRECTORY_BASE)}")
                    r = requests.get(url)
                    filename.write_bytes(r.content)
                yield filename

    def download_tiffs(self):
        for filename in self._tiffs:
            pass

    def create_map(self):
        for i, image_tiff in enumerate(self.imageTiffs):
            label = f"{image_tiff.filename.relative_to(DIRECTORY_BASE)} {i}({len(self.imageTiffs)})"
            image_tiff.create_tiles(label=label)

        for image_tiff in self.imageTiffs:
            image_tiff.append_sqlite()

        self.debug_logger.report()


@dataclass
class PngCache:
    x_tile: int
    y_tile: int
    orux_layer: int
    raw_png: bytes


class TiffImage:
    def __init__(self, scale, filename):
        self.orux_maps = scale.orux_maps
        self.filename = filename
        self.scale = scale
        self.context = self.orux_maps.context
        self.layer_param = scale.layer_param
        with rasterio.open(filename, "r") as dataset:
            pixel_lon = dataset.width
            pixel_lat = dataset.height

            t = dataset.get_transform()
            northwest_lon = t[0]
            northwest_lat = t[3]
            self.m_per_pixel = t[1]
            assert t[1] == -t[5]
            northwest = CH1903(lon=t[0], lat=t[3])
            southeast = CH1903(
                lon=northwest.lon + pixel_lon * self.m_per_pixel,
                lat=northwest.lat - pixel_lat * self.m_per_pixel,
            )
            self.boundsCH1903 = BoundsCH1903(a=northwest, b=southeast)

        self.layer_param.verify_m_per_pixel(self)
        projection.assertSwissgridIsNorthWest(self.boundsCH1903)
        self.debug_pngs = []

    def _load_image(self):
        with rasterio.open(self.filename, "r") as dataset:
            if len(dataset.indexes) == 3:
                # https://rasterio.readthedocs.io/en/latest/topics/image_processing.html
                # rasterio: (bands, rows, columns)
                # PIL: rows, columns, bands)
                data = dataset.read()
                img_arr = rasterio.plot.reshape_as_image(data)
                img = PIL.Image.fromarray(img_arr, mode="RGB")
                del data
                del img_arr
                assert dataset.width == img.width
                assert dataset.height == img.height
            else:
                img = PIL.Image.open(self.filename, mode="r")
            return img

    @property
    def _filename_pickle_png_cache(self):
        return (
            DIRECTORY_CACHE_PNG
            / f"{self.layer_param.name}_{self.filename.stem}{self.context.parts_png}.pickle"
        )

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

    def _extract_tile(self, img, topleft_x, topleft_y):
        assert 0 <= topleft_x < img.width
        assert 0 <= topleft_y < img.height
        bottomright_x = topleft_x + self.layer_param.pixel_per_tile
        bottomright_y = topleft_y + self.layer_param.pixel_per_tile
        assert self.layer_param.pixel_per_tile <= bottomright_x <= img.width
        assert self.layer_param.pixel_per_tile <= bottomright_y <= img.height
        im_crop = img.crop((topleft_x, topleft_y, bottomright_x, bottomright_y))
        fOut = io.BytesIO()
        self._save_purge_palette(fOut, im_crop)
        return fOut.getvalue()

    def create_tiles(self, label):
        if self._filename_pickle_png_cache.exists():
            # The tile have already been created
            return

        self._create_tiles2(label)

    def _create_tiles2(self, label):
        # We might not start at the top left -> We have to align the tiles
        # --> Offset pixel_x/pixel_y
        # --> Offset x, y
        lon_offset_m = self.boundsCH1903.a.lon - self.scale.boundsCH1903_extrema.a.lon
        lat_offset_m = self.boundsCH1903.a.lat - self.scale.boundsCH1903_extrema.a.lat
        # offset is typically positiv, but the first tile may be negative
        assert lon_offset_m >= -self.layer_param.m_per_tile
        # offset is typically negative, but the first tile may be positive
        assert lat_offset_m <= self.layer_param.m_per_tile

        x_offset_tile = int(lon_offset_m / self.layer_param.m_per_tile)
        y_offset_tile = int(-lat_offset_m / self.layer_param.m_per_tile)
        assert x_offset_tile >= 0
        assert y_offset_tile >= 0

        x_base_pixel = (
            int(lon_offset_m / self.layer_param.m_per_pixel)
            % self.layer_param.pixel_per_tile
        )
        y_base_pixel = (
            int(lat_offset_m / self.layer_param.m_per_pixel)
            % self.layer_param.pixel_per_tile
        )
        assert x_base_pixel >= 0
        assert y_base_pixel >= 0

        if self.context.skip_tiff_read:
            return

        list_png = []
        with self._load_image() as img:
            #
            # Die Tiles fuer die Karte zusammenkopieren
            #
            width = img.width - x_base_pixel
            height = img.height - y_base_pixel
            x_count = width // self.layer_param.pixel_per_tile
            y_count = height // self.layer_param.pixel_per_tile
            assert x_count > 0
            assert y_count > 0
            total = self.context.skip_count(x_count) * self.context.skip_count(y_count)
            start_s = time.perf_counter()
            size_bytes = 0
            png_count = 0
            # for y in range(y_count):
            for y in self.context.range(y_count):
                y_tile = y + y_offset_tile
                for x in self.context.range(x_count):
                    x_tile = x + x_offset_tile
                    x_tif_pixel = x * self.layer_param.pixel_per_tile + x_base_pixel
                    y_tif_pixel = y * self.layer_param.pixel_per_tile + y_base_pixel
                    self.debug_pngs.append(
                        DebugPng(
                            tiff_filename=self.filename.name,
                            x_tile=x_tile,
                            y_tile=y_tile,
                            x_tif_pixel=x_tif_pixel,
                            y_tif_pixel=y_tif_pixel,
                        )
                    )
                    png_count += 1
                    if self.context.skip_png_write:
                        continue
                    raw_png = self._extract_tile(img, x_tif_pixel, y_tif_pixel)
                    size_bytes += len(raw_png)
                    list_png.append(
                        PngCache(
                            x_tile=x_tile,
                            y_tile=y_tile,
                            orux_layer=self.layer_param.orux_layer,
                            raw_png=raw_png,
                        )
                    )
                duration_s = time.perf_counter() - start_s
                ms_per_tile = 1000.0 * duration_s / png_count
                print(
                    f"{label}. Image {png_count}({total}). Per tile: {ms_per_tile:0.0f}ms {size_bytes/png_count/1000:0.1f}kbytes"
                )

        statistics = f"{self.layer_param.name} {self.filename.name}, Total: {png_count}tiles {duration_s:0.0f}s {size_bytes/1000000:0.1f}Mbytes, Per tile: {ms_per_tile:0.0f}ms {size_bytes/png_count/1000:0.1f}kbytes"
        with self._filename_pickle_png_cache.open("wb") as f:
            pickle.dump(list_png, f)
        self._filename_pickle_png_cache.with_suffix(".txt").write_text(statistics)

    def append_sqlite(self):  # pylint: disable=too-many-statements,too-many-branches
        with self._filename_pickle_png_cache.open("rb") as f:
            list_png = pickle.load(f)

        for png in list_png:
            b = sqlite3.Binary(png.raw_png)
            self.orux_maps.db.execute(
                "insert or replace into tiles values (?,?,?,?)",
                (png.x_tile, png.y_tile, png.orux_layer, b),
            )

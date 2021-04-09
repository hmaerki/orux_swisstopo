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
from oruxmap.layers_switzerland import LIST_LAYERS

DIRECTORY_ORUX_SWISSTOPO = pathlib.Path(__file__).absolute().parent
DIRECTORY_RESOURCES = DIRECTORY_ORUX_SWISSTOPO / "resources"
DIRECTORY_BASE = DIRECTORY_ORUX_SWISSTOPO.parent
DIRECTORY_TARGET = DIRECTORY_BASE / "target"
DIRECTORY_CACHE_TIF = DIRECTORY_TARGET / "cache_tif"
DIRECTORY_CACHE_PNG = DIRECTORY_TARGET / "cache_png"
DIRECTORY_LOGS = DIRECTORY_TARGET / "logs"
DIRECTORY_MAPS = DIRECTORY_TARGET / "maps"

DIRECTORY_TARGET.mkdir(exist_ok=True)
DIRECTORY_CACHE_TIF.mkdir(exist_ok=True)
DIRECTORY_CACHE_PNG.mkdir(exist_ok=True)
DIRECTORY_LOGS.mkdir(exist_ok=True)
DIRECTORY_MAPS.mkdir(exist_ok=True)
assert DIRECTORY_MAPS.exists()

PIL.Image.MAX_IMAGE_PIXELS = None


class DurationLogger:
    def __init__(self, step: str):
        self.step = step
        self.start_s = time.perf_counter()

    def __enter__(self):
        return self

    def __exit__(self, _type, value, tb):
        print(f"{self.step} took {time.perf_counter() - self.start_s:0.0f}s")


class OruxMap:
    def __init__(self, map_name, context):
        assert isinstance(context, Context)
        self.map_name = context.append_version(map_name)
        self.context = context
        self.directory_map = DIRECTORY_MAPS / self.map_name

        print("===== ", self.map_name)

        # Remove zip file
        filename_zip = self.directory_map.with_suffix(".zip")
        if filename_zip.exists():
            filename_zip.unlink()

        # Create empty directory
        for filename in self.directory_map.glob("*.*"):
            filename.unlink()
        self.directory_map.mkdir(parents=True, exist_ok=True)

        filename_sqlite = self.directory_map / "OruxMapsImages.db"
        if filename_sqlite.exists():
            filename_sqlite.unlink()
        self.db = sqlite3.connect(filename_sqlite, isolation_level=None)
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

        with DurationLogger("sqlite.execute('VACUUM')") as duration:
            self.db.commit()
            if not self.context.skip_sqlite_vacuum:
                self.db.execute("VACUUM")
            self.db.close()

        if not self.context.skip_map_zip:
            with DurationLogger("zip") as duration:
                filename_zip = shutil.make_archive(
                    base_name=str(self.directory_map),
                    root_dir=str(self.directory_map.parent),
                    base_dir=self.directory_map.name,
                    format="zip",
                )
        print("----- Ready")
        print(
            f'The map now is ready in "{self.directory_map.relative_to(DIRECTORY_BASE)}".'
        )
        print(
            "This directory must be copied 'by Hans' onto your android into 'oruxmaps/mapfiles'."
        )

    def create_layers(self, iMasstabMin: int = 25, iMasstabMax: int = 500):
        with DurationLogger(f"Layer {self.map_name}") as duration:
            start_s = time.perf_counter()
            for layer_param in LIST_LAYERS:
                if iMasstabMin <= layer_param.scale <= iMasstabMax:
                    self._create_layer(layer_param=layer_param)

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
        self.directory_resources = DIRECTORY_RESOURCES / self.layer_param.name
        assert self.directory_resources.exists()

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
            # lat_m = tiff_images.boundsCH1903_floor.a.lat % layer_param.m_per_tile
            # lon_m = tiff_images.boundsCH1903_floor.a.lon % layer_param.m_per_tile
            self.boundsCH1903_extrema.extend(tiff_images.boundsCH1903_floor)

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
            minLat=boundsWGS84.southEast.lat_m,
            maxLat=boundsWGS84.northWest.lat_m,
            minLon=boundsWGS84.northWest.lon_m,
            maxLon=boundsWGS84.southEast.lon_m,
        )

    @property
    def _tiffs(self):
        if self.layer_param.tiff_filename:
            # For big scales, the image has to be extracted form a zip file
            tiff_filename = (
                DIRECTORY_CACHE_TIF
                / self.layer_param.name
                / self.layer_param.tiff_filename
            )
            d = DownloadZipAndExtractTiff(
                url=self.layer_param.tiff_url, tiff_filename=tiff_filename
            )
            d.download()
            yield tiff_filename
            return

        filename_url_tiffs = self.directory_resources / "url_tiffs.txt"
        yield from self._download_tiffs(filename_url_tiffs)

    def _download_tiffs(self, filename_url_tiffs):
        assert filename_url_tiffs.exists()
        directory_cache = DIRECTORY_CACHE_TIF / self.layer_param.name
        directory_cache.mkdir(exist_ok=True)
        with filename_url_tiffs.open("r") as f:
            for url in sorted(f.readlines()):
                url = url.strip()
                name = url.split("/")[-1]
                filename = directory_cache / name
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
            northwest = CH1903(lon_m=t[0], lat_m=t[3])
            southeast = CH1903(
                lon_m=northwest.lon_m + pixel_lon * self.m_per_pixel,
                lat_m=northwest.lat_m - pixel_lat * self.m_per_pixel,
            )
            self.boundsCH1903 = BoundsCH1903(nw=northwest, se=southeast)
            self.boundsCH1903_floor = self.boundsCH1903.floor(
                self.layer_param.m_per_tile
            )

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
            / self.context.append_version("png")
            / self.layer_param.name
            / self.filename.with_suffix(".pickle").name
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
        self._filename_pickle_png_cache.parent.mkdir(exist_ok=True, parents=True)

        self._create_tiles2(label)

    def _create_tiles2(self, label):
        lon_offset_m = (
            self.boundsCH1903.nw.lon_m - self.scale.boundsCH1903_extrema.nw.lon_m
        )
        lat_offset_m = (
            self.boundsCH1903.nw.lat_m - self.scale.boundsCH1903_extrema.nw.lat_m
        )
        assert lon_offset_m >= 0
        assert lat_offset_m <= 0

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

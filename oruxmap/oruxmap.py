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
import math
import time
import shutil
import pathlib
import pickle
import sqlite3

from dataclasses import dataclass
from multiprocessing import Pool

import requests
import PIL.Image
import rasterio
import rasterio.plot

from oruxmap.utils import projection
from oruxmap.utils.projection import CH1903, BoundsCH1903, create_boundsCH1903_extrema
from oruxmap.utils.context import Context
from oruxmap.utils.orux_xml_otrk2 import OruxXmlOtrk2
from oruxmap.utils.download_zip_and_extract import DownloadZipAndExtractTiff
from oruxmap.layers_switzerland import LIST_LAYERS, LayerParams
from oruxmap.utils.img_png import extract_tile

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


def directory_png_cache(layer_param: LayerParams, context: Context):
    return DIRECTORY_CACHE_PNG / context.append_version("png") / layer_param.name


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

        self.filename_sqlite = self.directory_map / "OruxMapsImages.db"
        if self.filename_sqlite.exists():
            self.filename_sqlite.unlink()
        self.db = sqlite3.connect(self.filename_sqlite, isolation_level=None)
        self.db.execute("pragma journal_mode=OFF")
        self.db.execute(
            """CREATE TABLE tiles (x int, y int, z int, image blob, PRIMARY KEY (x,y,z))"""
        )
        self.db.execute("""CREATE TABLE "android_metadata" (locale TEXT)""")
        self.db.execute("""INSERT INTO "android_metadata" VALUES ("de_CH");""")

        self.xml_otrk2 = OruxXmlOtrk2(
            filename=self.directory_map / f"{self.map_name}.otrk2.xml",
            map_name=self.map_name,
        )

    def __enter__(self):
        return self

    def __exit__(self, _type, value, tb):
        self.xml_otrk2.close()

        self.db.commit()
        if not self.context.skip_sqlite_vacuum:
            with DurationLogger("sqlite.execute('VACUUM')") as duration:
                before_bytes = self.filename_sqlite.stat().st_size
                self.db.execute("VACUUM")
                after_bytes = self.filename_sqlite.stat().st_size
                print(
                    f"Vaccum by {100.0*(before_bytes-after_bytes)/before_bytes:0.0f}%"
                )
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
            "This directory must be copied 'by Hand' onto your android into 'oruxmaps/mapfiles'."
        )

    def create_layers(self, iMasstabMin: int = 25, iMasstabMax: int = 500):
        with DurationLogger(f"Layer {self.map_name}") as duration:
            start_s = time.perf_counter()
            for layer_param in LIST_LAYERS:
                if iMasstabMin <= layer_param.scale <= iMasstabMax:
                    self._create_layer(layer_param=layer_param)

    def _create_layer(self, layer_param):
        map_scale = MapScale(self, layer_param)
        map_scale.create_boundsCH1903_pickle()
        map_scale.create_png_pickle()
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

    def report(self, list_tiff_attrs, boundsCH1903_extrema):
        assert isinstance(list_tiff_attrs, list)
        assert isinstance(boundsCH1903_extrema, BoundsCH1903)

        boundsCH1903_extrema.assertIsNorthWest()
        for tiff_attrs in list_tiff_attrs:
            tiff_attrs.boundsCH1903.assertIsNorthWest()

        def fopen(extension):
            filename_base = f"debug_log_{self.map_scale.layer_param.name}"
            filename = DIRECTORY_LOGS / (filename_base + extension)
            return filename.open("w")

        with fopen("_tiff.csv") as f:
            f.write(f"filename,{BoundsCH1903.csv_header('boundsCH1903')}\n")
            for tiff_attrs in list_tiff_attrs:
                assert isinstance(tiff_attrs, TiffImageAttributes)
                f.write(f"{tiff_attrs.filename.name},{tiff_attrs.boundsCH1903.csv}\n")
            f.write(f"all,{boundsCH1903_extrema.csv}\n")

        # No access to list  'debug_pngs'
        # with fopen("_png.csv") as f:
        #     f.write(
        #         f"{DebugPng.csv_header()},{BoundsCH1903.csv_header('boundsCH1903')}\n"
        #     )
        #     for tiff_filename, tiff_boundsCH1903 in list_filename_boundsCH1903:
        #         for debug_png in tiff_image.debug_pngs:
        #             f.write(f"{debug_png.csv},{tiff_image.boundsCH1903.csv}\n")


@dataclass
class CacheTiffBoundsCH1903:
    layer_param: LayerParams
    context: Context

    @property
    def filename(self):
        return (
            directory_png_cache(layer_param=self.layer_param, context=self.context)
            / f"list_filename_boundsCH1903.pickle"
        )

    def _check(self, list_attrs):
        for attrs in list_attrs:
            assert isinstance(attrs, TiffImageAttributes)

    def dump(self, list_attrs: list):
        self.filename.parent.mkdir(parents=True, exist_ok=True)
        self._check(list_attrs=list_attrs)
        with self.filename.open("wb") as f:
            pickle.dump(list_attrs, f)

    def load(self) -> list:
        with self.filename.open("rb") as f:
            list_attrs = pickle.load(f)
            self._check(list_attrs=list_attrs)
            return list_attrs


class MapScale:
    """
    This object represents one scale. For example 1:25'000, 1:50'000.
    """

    def __init__(self, orux_maps, layer_param):
        self.orux_maps = orux_maps
        self.layer_param = layer_param
        self.debug_logger = DebugLogger(self)
        self.directory_resources = DIRECTORY_RESOURCES / self.layer_param.name
        assert self.directory_resources.exists()

    def create_boundsCH1903_pickle(self):
        c = CacheTiffBoundsCH1903(
            layer_param=self.layer_param, context=self.orux_maps.context
        )
        if c.filename.exists():
            return

        def iter_download_tiffs(filename_url_tiffs):
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

        def iter_filename_tiff():
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
            yield from iter_download_tiffs(filename_url_tiffs)

        tiff_image_attributes = []
        for filename in iter_filename_tiff():
            tiff_attributes = TiffImageAttributes.create(
                layer_param=self.layer_param,
                filename=filename,
            )
            tiff_image_attributes.append(tiff_attributes)

        if len(tiff_image_attributes) == 0:
            raise Exception(
                f"No valid tiff for this scale {self.layer_param.scale} found"
            )

        for tiff in tiff_image_attributes:
            self.layer_param.verify_m_per_pixel(tiff.m_per_pixel)

        c.dump(list_attrs=tiff_image_attributes)

    def create_png_pickle(self):
        """
        This takes all tiffs for one scale and creates for each tiff a pickle file with all pngs
        """
        c = CacheTiffBoundsCH1903(
            layer_param=self.layer_param, context=self.orux_maps.context
        )
        assert c.filename.exists()
        list_tiff_attrs = c.load()

        arguments = [
            dict(
                context=self.orux_maps.context,
                tiff_attrs=tiff_attrs,
                i=i,
                total=len(list_tiff_attrs),
            )
            for i, tiff_attrs in enumerate(list_tiff_attrs)
        ]

        if self.orux_maps.context.multiprocessing:
            with Pool(8) as p:
                p.map(multiprocess_create_tiles2, arguments, chunksize=1)
            return
        for args in arguments:
            multiprocess_create_tiles(**args)

    def create_map(self):
        if not self.orux_maps.context.skip_tiff_read:
            c = CacheTiffBoundsCH1903(
                layer_param=self.layer_param, context=self.orux_maps.context
            )
            assert c.filename.exists()
            list_tiff_attrs = c.load()

            boundsCH1903_extrema = create_boundsCH1903_extrema()
            for tiff_attrs in list_tiff_attrs:
                # Align the tiff and shrink it to complete tiles
                # lat_m = tiff_images.boundsCH1903_floor.a.lat % layer_param.m_per_tile
                # lon_m = tiff_images.boundsCH1903_floor.a.lon % layer_param.m_per_tile
                boundsCH1903_extrema.extend(tiff_attrs.boundsCH1903_floor)

            print(
                f"{self.layer_param.scale}: {len(list_tiff_attrs)}tifs {boundsCH1903_extrema.lon_m/1000.0:0.0f}x{boundsCH1903_extrema.lat_m/1000.0:0.0f}km"
            )

            boundsCH1903_extrema.assertIsNorthWest()

            boundsWGS84 = boundsCH1903_extrema.to_WGS84(valid_data=self.layer_param.valid_data)

            width_pixel = int(boundsCH1903_extrema.lon_m / self.layer_param.m_per_pixel)
            height_pixel = int(
                boundsCH1903_extrema.lat_m / self.layer_param.m_per_pixel
            )
            # assert width_pixel % self.layer_param.pixel_per_tile == 0
            # assert height_pixel % self.layer_param.pixel_per_tile == 0

            self.orux_maps.xml_otrk2.write_layer(
                calib=boundsWGS84,
                TILE_SIZE=self.layer_param.pixel_per_tile,
                map_name=self.orux_maps.map_name,
                id=self.layer_param.orux_layer,
                xMax=width_pixel // self.layer_param.pixel_per_tile,
                yMax=height_pixel // self.layer_param.pixel_per_tile,
                height=height_pixel,
                width=width_pixel,
                minLat=boundsWGS84.southEast.lat_deg,
                maxLat=boundsWGS84.northWest.lat_deg,
                minLon=boundsWGS84.northWest.lon_deg,
                maxLon=boundsWGS84.southEast.lon_deg,
            )

            for tiff_attrs in list_tiff_attrs:
                tiff_image_converter = TiffImageConverter(
                    context=self.orux_maps.context,
                    tiff_attrs=tiff_attrs,
                )
                tiff_image_converter.append_sqlite(
                    db=self.orux_maps.db, boundsCH1903_extrema=boundsCH1903_extrema
                )

        self.debug_logger.report(
            list_tiff_attrs=list_tiff_attrs, boundsCH1903_extrema=boundsCH1903_extrema
        )


def multiprocess_create_tiles2(argument):
    multiprocess_create_tiles(**argument)


def multiprocess_create_tiles(context, tiff_attrs, i, total):
    assert isinstance(context, Context)
    assert isinstance(tiff_attrs, TiffImageAttributes)
    assert isinstance(i, int)
    assert isinstance(total, int)
    label = f"{tiff_attrs.filename.relative_to(DIRECTORY_BASE)} {i+1}({total})"
    tiff_image_converter = TiffImageConverter(context=context, tiff_attrs=tiff_attrs)
    tiff_image_converter.create_tiles(label=label)


@dataclass
class PngCache:
    x_tile: int
    y_tile: int
    raw_png: bytes


@dataclass
class TiffCache:
    list_png: list
    orux_layer: int
    nw: CH1903

    def __init__(self, nw: CH1903, orux_layer: int):
        assert isinstance(nw, CH1903)
        assert isinstance(orux_layer, int)
        self.nw = nw
        self.orux_layer = orux_layer
        self.list_png = []

    def append(self, png_cache: PngCache):
        assert isinstance(png_cache, PngCache)
        self.list_png.append(png_cache)


@dataclass
class TiffImageAttributes:
    filename: pathlib.Path
    m_per_pixel: float
    layer_param: LayerParams
    boundsCH1903: BoundsCH1903
    boundsCH1903_floor: BoundsCH1903

    @staticmethod
    def create(filename: pathlib.Path, layer_param: LayerParams):
        assert isinstance(filename, pathlib.Path)
        assert isinstance(layer_param, LayerParams)

        with rasterio.open(filename, "r") as dataset:
            pixel_lon = dataset.width
            pixel_lat = dataset.height
            calculated_pixel_per_tile = math.gcd(pixel_lon, pixel_lat)
            if layer_param.pixel_per_tile != calculated_pixel_per_tile:
                print(
                    f"{filename.relative_to(DIRECTORY_BASE)}: pixel_per_tile: expected {layer_param.pixel_per_tile}, calculated {calculated_pixel_per_tile}"
                )

            t = dataset.get_transform()
            northwest_lon_m = t[0]
            northwest_lat_m = t[3]
            m_per_pixel = t[1]
            assert t[1] == -t[5]

            northwest = CH1903(
                lon_m=northwest_lon_m,
                lat_m=northwest_lat_m,
                valid_data=layer_param.valid_data,
            )
            southeast = CH1903(
                lon_m=northwest.lon_m + pixel_lon * m_per_pixel,
                lat_m=northwest.lat_m - pixel_lat * m_per_pixel,
                valid_data=layer_param.valid_data,
            )
            boundsCH1903 = BoundsCH1903(nw=northwest, se=southeast)
            boundsCH1903.assertIsNorthWest()
            boundsCH1903_floor = boundsCH1903.floor(
                floor_m=layer_param.m_per_tile, valid_data=layer_param.valid_data
            )
            boundsCH1903_floor.assertIsNorthWest()
            if not boundsCH1903.equals(boundsCH1903_floor):
                print(f"{filename.relative_to(DIRECTORY_BASE)}: cropped")

        layer_param.verify_m_per_pixel(m_per_pixel)
        projection.assertSwissgridIsNorthWest(boundsCH1903)
        return TiffImageAttributes(
            filename=filename,
            m_per_pixel=m_per_pixel,
            layer_param=layer_param,
            boundsCH1903=boundsCH1903,
            boundsCH1903_floor=boundsCH1903_floor,
        )


class TiffImageConverter:
    def __init__(self, context, tiff_attrs):
        assert isinstance(context, Context)
        assert isinstance(tiff_attrs, TiffImageAttributes)
        self.context = context
        self.tiff_attrs = tiff_attrs
        self.layer_param = tiff_attrs.layer_param
        self.filename = tiff_attrs.filename
        self.boundsCH1903 = tiff_attrs.boundsCH1903
        self.boundsCH1903_floor = tiff_attrs.boundsCH1903_floor
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
                img = img.convert("RGB")
            return img

    @property
    def _filename_pickle_png_cache(self):
        return (
            directory_png_cache(layer_param=self.layer_param, context=self.context)
            / self.filename.with_suffix(".pickle").name
        )

    def create_tiles(self, label):
        if self._filename_pickle_png_cache.exists():
            # The tile have already been created
            return
        self._filename_pickle_png_cache.parent.mkdir(exist_ok=True, parents=True)
        if self.context.save_diskspace:
            self.filename.unlink()

        self._create_tiles2(label)

    def _create_tiles2(self, label):
        lon_offset_m = round(
            self.boundsCH1903_floor.nw.lon_m - self.boundsCH1903.nw.lon_m
        )
        lat_offset_m = round(
            self.boundsCH1903_floor.nw.lat_m - self.boundsCH1903.nw.lat_m
        )
        assert lon_offset_m >= 0
        assert lat_offset_m <= 0

        x_first_tile_pixel = round(lon_offset_m // self.layer_param.m_per_pixel)
        y_first_tile_pixel = round(-lat_offset_m // self.layer_param.m_per_pixel)

        assert 0 <= x_first_tile_pixel < self.layer_param.pixel_per_tile
        assert 0 <= y_first_tile_pixel < self.layer_param.pixel_per_tile

        if self.context.skip_tiff_read:
            return

        tiff_cache = TiffCache(
            orux_layer=self.layer_param.orux_layer, nw=self.boundsCH1903_floor.nw
        )
        with self._load_image() as img:
            #
            # Die Tiles fuer die Karte zusammenkopieren
            #
            width = img.width - x_first_tile_pixel
            height = img.height - y_first_tile_pixel
            x_count = width // self.layer_param.pixel_per_tile
            y_count = height // self.layer_param.pixel_per_tile
            assert x_count > 0
            assert y_count > 0
            total = self.context.skip_count(x_count) * self.context.skip_count(y_count)
            start_s = time.perf_counter()
            size_bytes = 0
            png_count = 0
            # for y in range(y_count):
            for y_tile in self.context.range(y_count):
                for x_tile in self.context.range(x_count):
                    x_tif_pixel = (
                        x_tile * self.layer_param.pixel_per_tile + x_first_tile_pixel
                    )
                    y_tif_pixel = (
                        y_tile * self.layer_param.pixel_per_tile + y_first_tile_pixel
                    )
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
                    raw_png = extract_tile(
                        img=img,
                        topleft_x=x_tif_pixel,
                        topleft_y=y_tif_pixel,
                        pixel_per_tile=self.layer_param.pixel_per_tile,
                        skip_optimize_png=self.context.skip_optimize_png,
                    )
                    size_bytes += len(raw_png)
                    tiff_cache.append(
                        PngCache(
                            x_tile=x_tile,
                            y_tile=y_tile,
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
            pickle.dump(tiff_cache, f)
        self._filename_pickle_png_cache.with_suffix(".txt").write_text(statistics)

    def append_sqlite(
        self, db, boundsCH1903_extrema
    ):  # pylint: disable=too-many-statements,too-many-branches
        assert isinstance(boundsCH1903_extrema, BoundsCH1903)
        with self._filename_pickle_png_cache.open("rb") as f:
            tiff_cache: TiffCache = pickle.load(f)

        lon_offset_m = tiff_cache.nw.lon_m - boundsCH1903_extrema.nw.lon_m
        lat_offset_m = boundsCH1903_extrema.nw.lat_m - tiff_cache.nw.lat_m
        lon_offset_m = round(lon_offset_m)
        lat_offset_m = round(lat_offset_m)
        assert lon_offset_m >= 0
        assert lat_offset_m >= 0

        x_tile_offset = round(lon_offset_m // self.layer_param.m_per_tile)
        y_tile_offset = round(lat_offset_m // self.layer_param.m_per_tile)
        assert x_tile_offset >= 0
        assert y_tile_offset >= 0

        for png in tiff_cache.list_png:
            b = sqlite3.Binary(png.raw_png)
            db.execute(
                "insert or replace into tiles values (?,?,?,?)",
                (
                    png.x_tile + x_tile_offset,
                    png.y_tile + y_tile_offset,
                    tiff_cache.orux_layer,
                    b,
                ),
            )

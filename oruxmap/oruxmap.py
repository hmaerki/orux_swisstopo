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
from typing import Iterable

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
from oruxmap.utils.img_png import convert_to_png_raw
from oruxmap.utils.sqlite_titles import SqliteTilesPng, SqliteTilesRaw
from oruxmap.utils.constants_directories import (
    DIRECTORY_MAPS,
    DIRECTORY_BASE,
    DIRECTORY_RESOURCES,
    DIRECTORY_CACHE_TILES,
    DIRECTORY_CACHE_TIF,
)

PIL.Image.MAX_IMAGE_PIXELS = None

PIXEL_PER_SUBTILE = 100


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
        self.db = sqlite3.connect(self.filename_sqlite)
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
        map_scale.sqlite_fill_subtiles()
        # map_scale.create_png_pickle()
        map_scale.sqlite_subtiles_to_tiles()
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
class _Subtiles:
    m_per_tile: int
    subtiles: list = None
    east_m: int = None
    north_m: int = None
    tile_east_idx: int = None

    @property
    def is_reset(self):
        return self.subtiles is None

    def append_if_same_tile(self, row) -> bool:
        east_m, _north_m, _ = row
        same_tile = self.tile_east_idx == east_m // self.m_per_tile
        if same_tile:
            self.subtiles.append(row)
        return same_tile

    def start_tile(self, row) -> None:
        east_m, north_m, _ = row
        self.tile_east_idx = east_m // self.m_per_tile
        self.east_m = east_m
        self.north_m = north_m
        self.subtiles = [row]

    def image(
        self, subtiles_per_tile: int, pixel_per_tile: int, m_per_subtile: int
    ) -> PIL.Image.Image:
        assert len(self.subtiles) == subtiles_per_tile * subtiles_per_tile
        img_tile = PIL.Image.new(
            mode="RGB",
            size=(
                pixel_per_tile,
                pixel_per_tile,
            ),
            color=0,
        )
        for east_m, north_m, img in self.subtiles:
            pixel_east = int(PIXEL_PER_SUBTILE * (east_m - self.east_m) / m_per_subtile)
            pixel_north = int(
                PIXEL_PER_SUBTILE * (north_m - self.north_m) / m_per_subtile
            )
            pixel_south = (subtiles_per_tile - 1) * PIXEL_PER_SUBTILE - pixel_north
            assert 0 <= pixel_east < pixel_per_tile
            assert 0 <= pixel_south < pixel_per_tile
            img_tile.paste(
                im=img,
                box=(pixel_east, pixel_south),
            )
        return img_tile


class MapScale:
    """
    This object represents one scale. For example 1:25'000, 1:50'000.
    """

    def __init__(self, orux_maps: OruxMap, layer_param: LayerParams):
        self.orux_maps = orux_maps
        self.layer_param = layer_param
        self.debug_logger = DebugLogger(self)
        self.directory_resources = DIRECTORY_RESOURCES / self.layer_param.name
        assert self.directory_resources.exists()

    @property
    def filename_subtiles_sqlite(self) -> pathlib.Path:
        return self._filename_tiles_sqlite("subtiles")

    @property
    def filename_tiles_sqlite(self) -> pathlib.Path:
        return self._filename_tiles_sqlite("tiles")

    def _filename_tiles_sqlite(self, db_name: str) -> pathlib.Path:
        filebase = (
            DIRECTORY_CACHE_TILES
            / self.orux_maps.context.append_version(db_name)
            / self.layer_param.name
        )
        return filebase.with_suffix(".db")

    def sqlite_fill_subtiles(self):
        if self.filename_subtiles_sqlite.exists():
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

        with SqliteTilesRaw(
            filename_sqlite=self.filename_subtiles_sqlite,
            pixel_per_tile=PIXEL_PER_SUBTILE,
            create=True,
        ) as db:
            db.remove()
            db.create_db()

            for filename in iter_filename_tiff():
                tiff_attrs = TiffImageAttributes.create(
                    layer_param=self.layer_param,
                    filename=filename,
                )
                # print(
                #     f"Create subtiles {filename.name} {tiff_attrs.boundsCH1903.nw.lon_m}/{tiff_attrs.boundsCH1903.nw.lat_m}"
                # )

                # with DurationLogger(f"Create subtiles {filename.name}"):
                tiff_image_converter = TiffImageConverter(
                    context=self.orux_maps.context, tiff_attrs=tiff_attrs
                )
                tiff_image_converter.create_subtiles(db=db)


    def sqlite_subtiles_to_tiles(self):
        if self.filename_tiles_sqlite.exists():
            return

        layer_param = self.layer_param

        with SqliteTilesPng(
            filename_sqlite=self.filename_tiles_sqlite,
            pixel_per_tile=layer_param.pixel_per_tile,
            create=True,
        ) as db_tiles:
            db_tiles.remove()
            db_tiles.create_db()

            with SqliteTilesRaw(
                filename_sqlite=self.filename_subtiles_sqlite,
                pixel_per_tile=PIXEL_PER_SUBTILE,
            ) as db_subtiles:
                db_subtiles.connect()

                assert layer_param.pixel_per_tile % PIXEL_PER_SUBTILE == 0
                subtiles_per_tile = layer_param.pixel_per_tile // PIXEL_PER_SUBTILE
                m_per_subtile = int(layer_param.m_per_pixel * PIXEL_PER_SUBTILE)
                m_per_tile = int(layer_param.m_per_tile)

                def get_rounded(north: bool, max: bool):
                    oper = "max" if max else "min"
                    sign = 1 if max else -1
                    direccion = "north_m" if north else "east_m"
                    m = db_subtiles.select_int(select=f"{oper}({direccion})")
                    return sign * m_per_tile * (sign * m // m_per_tile)

                # min_north_m = db_subtiles.select_int(select="min(north_m)")
                # min_north_m_rounded = -m_per_tile * (-min_north_m // m_per_tile)
                min_north_m_rounded = get_rounded(north=True, max=False)
                max_north_m_rounded = get_rounded(north=True, max=True)
                min_east_m_rounded = get_rounded(north=False, max=False)
                max_east_m_rounded = get_rounded(north=False, max=True)

                def iter_horizontal(top_north_m: int) -> Iterable[_Subtiles]:
                    # We loop over a horizontal strip which has the height of one tile
                    limit_vertical_stripe = f"north_m <= {top_north_m} and north_m > {top_north_m-m_per_tile}"
                    limit_horizontal_boundries = f"east_m <= {max_east_m_rounded} and east_m >= {min_east_m_rounded}"
                    iter_subtile = db_subtiles.select(
                        where=limit_vertical_stripe
                        + " and "
                        + limit_horizontal_boundries,
                        order="east_m, north_m",
                    )
                    subtiles = _Subtiles(m_per_tile=m_per_tile)

                    while True:
                        try:
                            row = next(iter_subtile)
                        except StopIteration:
                            return
                        if subtiles.is_reset:
                            # The very first time
                            subtiles.start_tile(row)
                            continue
                        if subtiles.append_if_same_tile(row):
                            continue
                        if (
                            len(subtiles.subtiles)
                            == subtiles_per_tile * subtiles_per_tile
                        ):
                            yield subtiles
                        subtiles.start_tile(row)

                # We loop over a horizontal strip which has the height of one tile
                for top_north_m in range(
                    min_north_m_rounded, max_north_m_rounded, m_per_tile
                ):
                    for subtiles in iter_horizontal(top_north_m=top_north_m):
                        if False:
                            # img_tile.show("Hallo")
                            import io

                            img_tile_png = PIL.Image.open(io.BytesIO(img_tile_png_raw))
                            img_tile_png.show("PNG")
                        img = subtiles.image(
                            subtiles_per_tile=subtiles_per_tile,
                            pixel_per_tile=layer_param.pixel_per_tile,
                            m_per_subtile=m_per_subtile,
                        )
                        db_tiles.add_subtile(
                            img=img,
                            east_m=subtiles.east_m,
                            north_m=subtiles.north_m,
                            skip_optimize_png=self.orux_maps.context.skip_optimize_png,
                        )

    def create_map(self):
        layer_param = self.layer_param

        with SqliteTilesPng(
            filename_sqlite=self.filename_tiles_sqlite,
            pixel_per_tile=layer_param.pixel_per_tile,
        ) as db_tiles:
            db_tiles.connect()

            min_east_m = db_tiles.select_int(select="min(east_m)")
            max_east_m = db_tiles.select_int(select="max(east_m)")
            min_north_m = db_tiles.select_int(select="min(north_m)")
            max_north_m = db_tiles.select_int(select="max(north_m)")

            m_per_tile = int(layer_param.m_per_tile)
            assert (max_east_m - min_east_m) % m_per_tile == 0
            assert (max_north_m - min_north_m) % m_per_tile == 0

            nw = CH1903(lon_m=float(min_east_m), lat_m=float(max_north_m))
            se = CH1903(lon_m=float(max_east_m), lat_m=float(min_north_m))
            boundsCH1903_extrema = BoundsCH1903(nw=nw, se=se, valid_data=True)

            boundsCH1903_extrema.assertIsNorthWest()

            boundsWGS84 = boundsCH1903_extrema.to_WGS84(
                valid_data=self.layer_param.valid_data
            )

            width_pixel = int(boundsCH1903_extrema.lon_m / self.layer_param.m_per_pixel)
            height_pixel = int(
                boundsCH1903_extrema.lat_m / self.layer_param.m_per_pixel
            )
            assert width_pixel % self.layer_param.pixel_per_tile == 0
            assert height_pixel % self.layer_param.pixel_per_tile == 0

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

            for east_m, north_m, img in db_tiles.select(
                where="true", order="east_m, north_m desc", raw=True
            ):

                lon_offset_m = east_m - boundsCH1903_extrema.nw.lon_m
                lat_offset_m = boundsCH1903_extrema.nw.lat_m - north_m
                lon_offset_m = round(lon_offset_m)
                lat_offset_m = round(lat_offset_m)
                assert lon_offset_m >= 0
                assert lat_offset_m >= 0

                x_tile_offset = round(lon_offset_m // self.layer_param.m_per_tile)
                y_tile_offset = round(lat_offset_m // self.layer_param.m_per_tile)
                assert x_tile_offset >= 0
                assert y_tile_offset >= 0

                b = sqlite3.Binary(img)
                self.orux_maps.db.execute(
                    "insert into tiles values (?,?,?,?)",
                    (
                        x_tile_offset,  # png.x_tile + x_tile_offset,
                        y_tile_offset,  # png.y_tile + y_tile_offset,
                        layer_param.orux_layer,
                        b,
                    ),
                )

@dataclass
class PngCache:
    x_tile: int
    y_tile: int
    raw_png: bytes

# TODO(hans): remove?
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


# TODO(hans): remove?
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

            if (pixel_lon % PIXEL_PER_SUBTILE != 0) or (
                pixel_lat % PIXEL_PER_SUBTILE != 0
            ):
                print(
                    f"{filename.relative_to(DIRECTORY_BASE)}: size={pixel_lon}/{pixel_lat} does not fit in PIXEL_PER_SUBTILE={PIXEL_PER_SUBTILE}"
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
            # TODO(hans): Remove
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

# TODO(hans): remove?
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

    # TODO(hans): remove
    @property
    def _filename_pickle_png_cache(self):
        return (
            directory_png_cache(layer_param=self.layer_param, context=self.context)
            / self.filename.with_suffix(".pickle").name
        )

    def create_subtiles(self, db: SqliteTilesRaw) -> None:
        with self._load_image() as img:
            if (img.width % PIXEL_PER_SUBTILE != 0) or (
                img.height % PIXEL_PER_SUBTILE != 0
            ):
                print(
                    f"{self.filename.relative_to(DIRECTORY_BASE)}: WARNING: Strange image size {img.width}/{img.height}"
                )
            m_per_pixel = self.layer_param.m_per_pixel
            lon_m = int(self.tiff_attrs.boundsCH1903.nw.lon_m)
            lat_m = int(self.tiff_attrs.boundsCH1903.nw.lat_m)
            # print(f"{self.filename.name}: {lon_m}/{lat_m}")
            for x_pixel in range(0, img.width, PIXEL_PER_SUBTILE):
                east_m = int(m_per_pixel * x_pixel) + lon_m
                for y_pixel in range(0, img.height, PIXEL_PER_SUBTILE):
                    north_m = lat_m - int(m_per_pixel * y_pixel)
                    img_subtile = img.crop(
                        (
                            x_pixel,
                            y_pixel,
                            x_pixel + PIXEL_PER_SUBTILE,
                            y_pixel + PIXEL_PER_SUBTILE,
                        )
                    )
                    db.add_subtile(img=img_subtile, east_m=east_m, north_m=north_m)

    # TODO(hans): remove?
    def append_sqlite(
        self, db, boundsCH1903_extrema
    ): 
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

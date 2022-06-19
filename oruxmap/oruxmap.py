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
import time
import shutil
import pathlib

from dataclasses import dataclass
from typing import Iterable

import requests
import PIL.Image
import rasterio
import rasterio.plot

from oruxmap.utils import projection
from oruxmap.utils.projection import CH1903, BoundsCH1903
from oruxmap.utils.context import Context
from oruxmap.utils.orux_xml_otrk2 import OruxXmlOtrk2
from oruxmap.utils.download_zip_and_extract import DownloadZipAndExtractTiff
from oruxmap.layers_switzerland import LIST_LAYERS, LayerParams
from oruxmap.utils.sqlite_titles import SqliteTilesPng, SqliteTilesRaw
from oruxmap.utils.sqlite_orux import SqliteOrux
from oruxmap.utils.constants_directories import (
    DIRECTORY_MAPS,
    DIRECTORY_BASE,
    DIRECTORY_RESOURCES,
    DIRECTORY_CACHE_TILES,
    DIRECTORY_CACHE_TIF,
    DIRECTORY_LOGS,
    DIRECTORY_TESTRESULTS,
)

PIL.Image.MAX_IMAGE_PIXELS = None

PIXEL_PER_SUBTILE = 100


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
        for filename in DIRECTORY_TESTRESULTS.glob("*.*"):
            filename.unlink()
        self.directory_map.mkdir(parents=True, exist_ok=True)

        self.db = SqliteOrux(filename_sqlite=self.directory_map / "OruxMapsImages.db")

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
                self.db.vacuum()
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


@dataclass
class Subtiles:
    m_per_tile: int
    subtiles: list = None
    nw_east_m: int = None
    nw_north_m: int = None
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
        self.nw_east_m = east_m
        self.nw_north_m = north_m
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
        for nw_east_m, nw_north_m, img in self.subtiles:
            pixel_east = int(
                PIXEL_PER_SUBTILE * (nw_east_m - self.nw_east_m) / m_per_subtile
            )
            pixel_north = int(
                PIXEL_PER_SUBTILE * (nw_north_m - self.nw_north_m) / m_per_subtile
            )
            pixel_south = -pixel_north
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

    def sqlite_fill_subtiles(self) -> None:
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
                tiff_attrs.unittest_dump()
                # print(
                #     f"Create subtiles {filename.name} {tiff_attrs.boundsCH1903.nw.lon_m}/{tiff_attrs.boundsCH1903.nw.lat_m}"
                # )

                # with DurationLogger(f"Create subtiles {filename.name}"):
                tiff_image_converter = TiffImageConverter(
                    context=self.orux_maps.context, tiff_attrs=tiff_attrs
                )
                tiff_image_converter.create_subtiles(db=db)

    def sqlite_subtiles_to_tiles(self) -> None:
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

                def get_rounded(north: bool, select_max: bool):
                    oper = "max" if select_max else "min"
                    sign = 1 if select_max else -1
                    direccion = "nw_north_m" if north else "nw_east_m"
                    m = db_subtiles.select_int(select=f"{oper}({direccion})")
                    return sign * m_per_tile * (sign * m // m_per_tile)

                min_nw_north_m_rounded = get_rounded(north=True, select_max=False)
                max_nw_north_m_rounded = get_rounded(north=True, select_max=True)
                min_nw_east_m_rounded = get_rounded(north=False, select_max=False)
                max_nw_east_m_rounded = get_rounded(north=False, select_max=True)

                def iter_horizontal(top_nw_north_m: int) -> Iterable[Subtiles]:
                    # We loop over a horizontal strip which has the height of one tile
                    limit_vertical_stripe = f"nw_north_m <= {top_nw_north_m} and nw_north_m > {top_nw_north_m-m_per_tile}"
                    limit_horizontal_boundries = f"nw_east_m <= {max_nw_east_m_rounded} and nw_east_m >= {min_nw_east_m_rounded}"
                    iter_subtile = db_subtiles.select(
                        where=limit_vertical_stripe
                        + " and "
                        + limit_horizontal_boundries,
                        order="nw_east_m, nw_north_m desc",
                    )
                    subtiles = Subtiles(m_per_tile=m_per_tile)

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
                for top_nw_north_m in range(
                    min_nw_north_m_rounded, max_nw_north_m_rounded, m_per_tile
                ):
                    for subtiles in iter_horizontal(top_nw_north_m=top_nw_north_m):
                        img = subtiles.image(
                            subtiles_per_tile=subtiles_per_tile,
                            pixel_per_tile=layer_param.pixel_per_tile,
                            m_per_subtile=m_per_subtile,
                        )
                        db_tiles.add_subtile(
                            img=img,
                            nw_east_m=subtiles.nw_east_m,
                            nw_north_m=subtiles.nw_north_m,
                            skip_optimize_png=self.orux_maps.context.skip_optimize_png,
                        )
                        self.unittest_dump(subtiles=subtiles, img=img)

    def unittest_dump(  # pylint: disable=too-many-arguments
        self,
        subtiles: Subtiles,
        img=PIL.Image.Image,
    ) -> None:
        for probe_layer, probe_nw_east_m, probe_nw_north_m in (
            ("0100", 2690000, 1250000),  # Does never trigger...
            ("0100", 2690000, 1245000),
            ("0100", 2690000, 1215000),
        ):
            if (
                probe_nw_east_m == subtiles.nw_east_m
                and probe_nw_north_m == subtiles.nw_north_m
                and probe_layer == self.layer_param.name
            ):
                filename = (
                    DIRECTORY_TESTRESULTS
                    / f"{self.layer_param.name}-tiles-{subtiles.nw_east_m}_{subtiles.nw_north_m}.txt"
                )

                with filename.open("w") as f:
                    f.write(f"  nw_east_m={subtiles.nw_east_m}\n")
                    f.write(f"  nw_north_m={subtiles.nw_north_m}\n")
                img.save(filename.with_suffix(".png"))

    def create_map(self) -> None:
        layer_param = self.layer_param

        with SqliteTilesPng(
            filename_sqlite=self.filename_tiles_sqlite,
            pixel_per_tile=layer_param.pixel_per_tile,
        ) as db_tiles:
            db_tiles.connect()
            m_per_tile = int(layer_param.m_per_tile)

            min_nw_east_m = db_tiles.select_int(select="min(nw_east_m)")
            max_nw_north_m = db_tiles.select_int(select="max(nw_north_m)")

            max_se_east_m = db_tiles.select_int(select="max(nw_east_m)") + m_per_tile
            min_se_north_m = db_tiles.select_int(select="min(nw_north_m)") - m_per_tile

            assert (max_se_east_m - min_nw_east_m) % m_per_tile == 0
            assert (max_nw_north_m - min_se_north_m) % m_per_tile == 0

            nw = CH1903(lon_m=float(min_nw_east_m), lat_m=float(max_nw_north_m))
            se = CH1903(lon_m=float(max_se_east_m), lat_m=float(min_se_north_m))
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

            for nw_east_m, nw_north_m, img in db_tiles.select(
                where="true", order="nw_east_m, nw_north_m", raw=True
            ):
                lon_offset_m = nw_east_m - boundsCH1903_extrema.nw.lon_m
                lat_offset_m = boundsCH1903_extrema.nw.lat_m - nw_north_m
                lon_offset_m = round(lon_offset_m)
                lat_offset_m = round(lat_offset_m)
                assert lon_offset_m >= 0
                assert lat_offset_m >= 0

                x_tile_offset = round(lon_offset_m // self.layer_param.m_per_tile)
                y_tile_offset = round(lat_offset_m // self.layer_param.m_per_tile)
                assert x_tile_offset >= 0
                assert y_tile_offset >= 0

                self.orux_maps.db.insert(
                    x_tile_offset=x_tile_offset,  # png.x_tile + x_tile_offset,
                    y_tile_offset=y_tile_offset,  # png.y_tile + y_tile_offset,
                    orux_layer=layer_param.orux_layer,
                    img=img,
                )


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

    def unittest_dump(self):
        if self.filename.name in ("swiss-map-raster100_2013_33_komb_5_2056.tif",):
            filename_unittest = (
                DIRECTORY_TESTRESULTS
                / f"{self.layer_param.name}-{self.filename.stem}.txt"
            )
            with filename_unittest.open("w") as f:
                f.write(f"{self.filename.relative_to(DIRECTORY_BASE)}\n")
                f.write(f"  boundsCH1903.nw.lon_m={self.boundsCH1903.nw.lon_m}\n")
                f.write(f"  boundsCH1903.nw.lat_m={self.boundsCH1903.nw.lat_m}\n")
                f.write(f"  boundsCH1903.se.lon_m={self.boundsCH1903.se.lon_m}\n")
                f.write(f"  boundsCH1903.se.lat_m={self.boundsCH1903.se.lat_m}\n")
                f.write(f"  scale={self.layer_param.scale}\n")
                f.write(f"  m_per_pixel={self.layer_param.m_per_pixel}\n")
                f.write(f"  m_per_tile={self.layer_param.m_per_tile}\n")
                f.write(
                    f"  m_per_subtile={PIXEL_PER_SUBTILE*self.layer_param.m_per_pixel}\n"
                )
                f.write(f"  pixel_per_tile={self.layer_param.pixel_per_tile}\n")
                f.write(f"  pixel_per_subtile={PIXEL_PER_SUBTILE}\n")
                f.write(f"  scale={self.layer_param.scale}\n")


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
                nw_east_m = int(m_per_pixel * x_pixel) + lon_m
                for y_pixel in range(0, img.height, PIXEL_PER_SUBTILE):
                    nw_north_m = lat_m - int(m_per_pixel * y_pixel)
                    img_subtile = img.crop(
                        (
                            x_pixel,
                            y_pixel,
                            x_pixel + PIXEL_PER_SUBTILE,
                            y_pixel + PIXEL_PER_SUBTILE,
                        )
                    )
                    self.unittest_dump(
                        x_pixel=x_pixel,
                        y_pixel=y_pixel,
                        nw_east_m=nw_east_m,
                        nw_north_m=nw_north_m,
                        img=img_subtile,
                    )
                    db.add_subtile(
                        img=img_subtile, nw_east_m=nw_east_m, nw_north_m=nw_north_m
                    )

    def unittest_dump(  # pylint: disable=too-many-arguments
        self,
        x_pixel: int,
        y_pixel: int,
        nw_east_m: int,
        nw_north_m: int,
        img=PIL.Image.Image,
    ) -> None:
        for probe_filename, probe_x_pixel, probe_y_pixel in (
            ("swiss-map-raster100_2013_33_komb_5_2056.tif", 0, 0),
            (
                "swiss-map-raster100_2013_33_komb_5_2056.tif",
                PIXEL_PER_SUBTILE,
                0,
            ),
            (
                "swiss-map-raster100_2013_33_komb_5_2056.tif",
                0,
                PIXEL_PER_SUBTILE,
            ),
        ):
            if (
                probe_x_pixel == x_pixel
                and probe_y_pixel == y_pixel
                and probe_filename == self.filename.name
            ):
                filename = (
                    DIRECTORY_TESTRESULTS
                    / f"{self.layer_param.name}-subtiles-{self.filename.stem}_{x_pixel}_{y_pixel}.txt"
                )

                with filename.open("w") as f:
                    f.write(f"{self.filename}\n")
                    f.write(f"  x_pixel={x_pixel}\n")
                    f.write(f"  y_pixel={y_pixel}\n")
                    f.write(f"  nw_east_m={nw_east_m}\n")
                    f.write(f"  nw_north_m={nw_north_m}\n")
                img.save(filename.with_suffix(".png"))

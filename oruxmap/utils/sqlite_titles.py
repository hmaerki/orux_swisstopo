import io
import pathlib
import sqlite3
import PIL.Image

from oruxmap.utils.img_png import convert_to_png_raw


class _SqliteTilesBase:
    def __init__(
        self, filename_sqlite: pathlib.Path, pixel_per_tile: int, create=False
    ):
        self.filename_sqlite = filename_sqlite
        self.filename_sqlite_tmp = filename_sqlite.with_suffix(".tmp")
        self.pixel_per_tile = pixel_per_tile
        self.create = create
        self.db = None

    def __enter__(self):
        return self

    def __exit__(self, _type, value, tb):
        assert self.db is not None
        self.db.commit()
        # print(f"{self.filename_sqlite.relative_to(DIRECTORY_BASE)}: {self.select_int('count(*)')} records.")
        self.db.close()
        self.db = None
        if self.create:
            if tb is None:
                self.filename_sqlite_tmp.rename(self.filename_sqlite)

    def _tobytes(self, img: PIL.Image.Image, skip_optimize_png: bool) -> bytes:
        raise NotImplementedError()

    def _frombytes(self, data: bytes) -> PIL.Image.Image:
        raise NotImplementedError()

    def remove(self) -> None:
        for filename in (self.filename_sqlite, self.filename_sqlite_tmp):
            if filename.exists():
                filename.unlink()
        self.db = None

    def connect(self) -> None:
        if self.create:
            self.filename_sqlite.parent.mkdir(exist_ok=True, parents=True)
            filename = self.filename_sqlite_tmp
        else:
            filename = self.filename_sqlite
            assert filename.exists()
        self.db = sqlite3.connect(filename)

    def create_db(self) -> None:
        assert self.create
        self.connect()

        self.db.execute("pragma journal_mode=OFF")
        self.db.execute(
            """CREATE TABLE tiles (nw_east_m int, nw_north_m int, image blob, PRIMARY KEY (nw_east_m, nw_north_m))"""
        )

    def add_subtile(
        self,
        img: PIL.Image.Image,
        nw_east_m: int,
        nw_north_m: int,
        skip_optimize_png=False,
    ) -> None:
        b = sqlite3.Binary(self._tobytes(img=img, skip_optimize_png=skip_optimize_png))
        self.db.execute(
            "insert into tiles values (?,?,?)",
            (
                nw_east_m,
                nw_north_m,
                b,
            ),
        )

    def select_int(self, select: str) -> int:
        c = self.db.cursor()
        c.execute(f"select {select} from tiles")
        row = next(c)
        value = row[0]
        assert isinstance(value, int)
        c.close()
        return value

    def select(self, where: str, order: str, raw=False):
        c = self.db.cursor()
        c.execute(
            f"select nw_east_m, nw_north_m, image from tiles where {where} order by {order}"
        )
        for row in c:
            img = row[2]
            if not raw:
                img = self._frombytes(data=img)
            yield row[0], row[1], img
        c.close()


class SqliteTilesRaw_obsolete(_SqliteTilesBase):
    def _tobytes(self, img: PIL.Image.Image, skip_optimize_png: bool) -> bytes:
        return img.tobytes()

    def _frombytes(self, data: bytes) -> PIL.Image.Image:
        return PIL.Image.frombytes(
            mode="RGB", size=(self.pixel_per_tile, self.pixel_per_tile), data=data
        )


class SqliteTilesPng(_SqliteTilesBase):
    def _tobytes(self, img: PIL.Image.Image, skip_optimize_png: bool) -> bytes:
        assert img.width == self.pixel_per_tile
        assert img.height == self.pixel_per_tile
        img_tile_png_raw = convert_to_png_raw(
            img=img,
            skip_optimize_png=skip_optimize_png,
        )
        return img_tile_png_raw

    def _frombytes(self, data: bytes) -> PIL.Image.Image:
        return PIL.Image.open(io.BytesIO(data))

SqliteTilesRaw = SqliteTilesPng

import pathlib
import sqlite3


class SqliteOrux:
    def __init__(self, filename_sqlite: pathlib.Path):
        self.filename_sqlite = filename_sqlite
        if self.filename_sqlite.exists():
            self.filename_sqlite.unlink()
        self.db = sqlite3.connect(self.filename_sqlite)
        self.db.execute("pragma journal_mode=OFF")
        self.db.execute(
            """CREATE TABLE tiles (x int, y int, z int, image blob, PRIMARY KEY (x,y,z))"""
        )
        self.db.execute("""CREATE TABLE "android_metadata" (locale TEXT)""")
        self.db.execute("""INSERT INTO "android_metadata" VALUES ("de_CH");""")

    def vacuum(self) -> None:
        before_bytes = self.filename_sqlite.stat().st_size
        self.db.execute("VACUUM")
        after_bytes = self.filename_sqlite.stat().st_size
        print(f"Vaccum by {100.0*(before_bytes-after_bytes)/before_bytes:0.0f}%")

    def commit(self) -> None:
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def insert(
        self, x_tile_offset: int, y_tile_offset: int, orux_layer: int, img
    ) -> None:
        b = sqlite3.Binary(img)
        self.db.execute(
            "insert into tiles values (?,?,?,?)",
            (
                x_tile_offset,  # png.x_tile + x_tile_offset,
                y_tile_offset,  # png.y_tile + y_tile_offset,
                orux_layer,
                b,
            ),
        )

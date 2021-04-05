from dataclasses import dataclass
from typing import List


@dataclass
class Context:
    skip_optimize_png: bool = False
    skip_png_write: bool = False
    skip_tiff_read: bool = False
    only_example_tiles: bool = False
    only_tiffs: List[str] = None
    only_tiles_border: int = None
    only_tiles_modulo: int = None

    def skip_count(self, count) -> int:
        return len(list(self.range(count)))

    def range(self, count):
        if self.only_tiles_border:
            for i in range(count):
                skip = self.only_tiles_border <= i < count - self.only_tiles_border
                if not skip:
                    yield i
            return

        if self.only_tiles_modulo:
            for i in range(0, count, self.only_tiles_modulo):
                yield i
            return

        yield from range(count)

    def append_version(self, basename: str) -> str:
        parts = [
            basename,
        ]
        if self.skip_optimize_png:
            parts.append("skip_optimize")
        if self.only_tiles_border or self.only_tiles_modulo:
            parts.append("subset")
        return "-".join(parts)

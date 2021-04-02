from dataclasses import dataclass
from typing import List


@dataclass
class Context:
    skip_optimize_png: bool = False
    skip_png: bool = False
    only_example_tiles: bool = False
    only_tiffs: List[str] = None
    only_tiles_border: int = None

    def skip_border(self, i, count) -> bool:
        if self.only_tiles_border is None:
            return False
        return self.only_tiles_border <= i < count - self.only_tiles_border

    def skip_count(self, count) -> int:
        if self.only_tiles_border is None:
            return count
        return 2 * self.only_tiles_border

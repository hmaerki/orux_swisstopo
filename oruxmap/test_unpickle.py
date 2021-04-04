import pickle
import pathlib

from oruxmap.oruxmap import DIRECTORY_CACHE_PNG


def main(filename):
    with filename.open("rb") as fin:
        list_png = pickle.load(fin)

    for png in list_png[:2]:
        filename_png = (
            pathlib.Path(__file__).parent
            / f"tmp_{filename.stem}_{png.orux_layer}_{png.x_tile}_{png.y_tile}.png"
        )
        filename_png.write_bytes(png.raw_png)


if __name__ == "__main__":
    for f in (
        "1000_SMR1000_KREL.pickle",
        "1000_SMR1000_KREL-optimize.pickle",
        "0500_SMR500_KREL.pickle",
        "0500_SMR500_KREL-optimize.pickle",
        "0500_SMR500_KREL.pickle",
        "0500_SMR500_KREL-optimize.pickle",
        "0050_swiss-map-raster50_2013_226_komb_2.5_2056-optimize.pickle",
        "0050_swiss-map-raster50_2013_226_komb_2.5_2056.pickle",
    ):
        main(DIRECTORY_CACHE_PNG / f)

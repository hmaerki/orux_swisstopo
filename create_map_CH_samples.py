#!/usr/bin/env python3

# pylint: disable=redefined-outer-name

from oruxmap.utils.context import Context
from oruxmap.utils.constants_switzerland import tiffs_wetzikon
from oruxmap.oruxmap import OruxMap


def get_contextA():
    context = Context()
    # context.skip_optimize_png = True
    context.only_tiffs = tiffs_wetzikon
    # context.only_tiles_border = 5
    # context.only_tiles_modulo = 10
    # context.skip_tiff_read = True
    # context.skip_png_write = True
    return context


def get_contextB():
    context = get_contextA()
    context.skip_optimize_png = True
    # context.multiprocessing = False
    return context


if __name__ == "__main__":
    for context in (
        get_contextA(),
        get_contextB(),
    ):
        with OruxMap("CH_samples_wetzikon_25k_up", context=context) as oruxmap:
            oruxmap.create_layers(iMasstabMin=25, iMasstabMax=1000)

        with OruxMap("CH_samples_wetzikon_10k", context=context) as oruxmap:
            oruxmap.create_layers(iMasstabMin=10, iMasstabMax=10)

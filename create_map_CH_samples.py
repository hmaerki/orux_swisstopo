#!/usr/bin/python
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
    return context


for context in (
    get_contextA(),
    get_contextB(),
):
    with OruxMap("CH_samples", context=context) as oruxmap:
        oruxmap.create_layers(iMasstabMin=10, iMasstabMax=1000)

#!/usr/bin/python

import programm.context
import programm.constants_switzerland
import programm.orux_swisstopo

def get_contextA():
    context = programm.context.Context()
    # context.skip_optimize_png = True
    context.only_tiffs = programm.constants_switzerland.tiffs_wetzikon
    # context.only_tiles_border = 5
    context.only_tiles_modulo = 10
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
    with programm.orux_swisstopo.OruxMap(f"CH_samples{context.parts_png}", context=context) as oruxmap:
        oruxmap.createLayers(iMasstabMin=10, iMasstabMax=200)

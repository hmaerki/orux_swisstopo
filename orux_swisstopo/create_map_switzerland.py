#!/usr/bin/python

import programm.context
import programm.constants_switzerland
import programm.orux_swisstopo

context = programm.context.Context()
# context.skip_optimize_png = True
context.only_tiffs = programm.constants_switzerland.tiffs_wetzikon
# context.only_tiles_border = 5
context.only_tiles_modulo = 10
# context.skip_tiff_read = True
# context.skip_png_write = True
with programm.orux_swisstopo.OruxMap(f"CH_Topo", context=context) as oruxmap:
    oruxmap.createLayers(iMasstabMin=25, iMasstabMax=200)

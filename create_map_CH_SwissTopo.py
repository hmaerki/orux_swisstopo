#!/usr/bin/env python3

from oruxmap.utils.context import Context

# from oruxmap.utils.constants_switzerland import tiffs_wetzikon,
from oruxmap.oruxmap import OruxMap

context = Context()
# context.skip_optimize_png = True
# context.only_tiffs = tiffs_wetzikon
# context.only_tiles_border = 5
# context.only_tiles_modulo = 10
# context.skip_tiff_read = True
# context.skip_png_write = True

with OruxMap(f"CH_SwissTopo25k_up", context=context) as oruxmap:
    oruxmap.create_layers(iMasstabMin=25, iMasstabMax=1000)

with OruxMap(f"CH_SwissTopo10k", context=context) as oruxmap:
    oruxmap.create_layers(iMasstabMin=10, iMasstabMax=10)

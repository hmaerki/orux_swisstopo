#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright (C) 2010 Hans Maerk, Maerki Informatik
# License: LGPL (http://www.gnu.org/licenses/lgpl.html)

import programm

oruxmap = programm.OruxMap("Testmap1", bSqlite=True)
for iLayer in (1000000, 500000, 200000):
    oruxmap.createLayerPlusMinus(iLayer, (701000.0, 235000.0), 10000.0)
for iLayer in (100000, 50000, 25000):
    oruxmap.createLayerPlusMinus(iLayer, (701000.0, 235000.0), 4000.0)
oruxmap.done()

oruxmap = programm.OruxMap("Testmap2", bSqlite=False)
for iLayer in (1000000, 500000, 200000):
    oruxmap.createLayerPlusMinus(iLayer, (701000.0, 235000.0), 10000.0)
for iLayer in (100000, 50000, 25000):
    oruxmap.createLayerPlusMinus(iLayer, (701000.0, 235000.0), 4000.0)
oruxmap.done()

oruxmap = programm.OruxMap("Testmap3", bSqlite=False, bCopyReferenceTiles=True)
for iLayer in (5000000, 2000000, 1000000, 500000, 200000):
    oruxmap.createLayerPlusMinus(iLayer, (701000.0, 235000.0), 10000.0)
for iLayer in (100000, 50000, 25000):
    oruxmap.createLayerPlusMinus(iLayer, (701000.0, 235000.0), 4000.0)
oruxmap.done()

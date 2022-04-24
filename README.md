# orux_swisstopo

2021-04-18, Hans Märki

This scripts creates a offline map of the pixelmap of https://map.geo.admin.ch

You may download the map from https://www.maerki.com/hans/orux/CH_SwissTopo.zip.
To use in Orux Maps, download the zip onto your computer and extract it.
Now copy the two resulting files `CH_SwissTopo.otrk2.xml` and `OruxMapsImages.db` onto your android phone into the folder `oruxmaps/mapfiles/CH_SwissTopo`.

The map may be found now in Orux Maps under `OFFLINE` maps.

# 2022-04-24, Hans Märki

The geographical pixel location of the swiss topo images are sometime not aligned (1:200'000 for example).
It would be easier, if all images could be concatinated into one big image.

Some size calulation:

Layer 1:25'000: height="182400" width="294000"

The PIL limits are:
https://pillow.readthedocs.io/en/stable/reference/limits.html
Maximum pixel dimensions are limited to INT32, or 2^31: 2'147'483'648

```python
memory = 294000 * 182400 *  8
memory requirement for Indexed = 4.290e+11 Bytes, 42.900 GBytes
# print(f"memory requirement = {memory:2.3e} Bytes, {memory/10e9:0.3f} GBytes")

memory *= 3
print(f"memory requirement for RGB = {memory:2.3e} Bytes, {memory/10e9:0.3f} GBytes")
# print(f"memory requirement = {memory:2.3e} Bytes, {memory/10e9:0.3f} GBytes")
```

Conclusion: The map is far too big!

Other approach:

Create tiles of 100x100 px and store them in sqlite.
294000 * 182400 // 100 // 100
= 5_362_560 100x100 tiles for 1:25000

Now concatenate the tiles.

## database

| column | example | unit | comment |
| - | - | - | - |
| filename | layer_12.sqlite |
| east_m | 2_600_000 | m, integer | Bern |
| north_m | 1_200_000 | m, integer | Bern |
| image | | rgb |

100px tiles will always lie on a m boundry. Therefore a integer may be used.

Query to select a 1000x1000 pixel tile:

```sql
select * from WHERE
  [east_m] BETWEEN lower_east_m AND higher_east_m
  and
  [north_m] BETWEEN lower_north_m AND higher_north_m
  order by [lower_east_m], [lower_north_m]
```

## Refactoring rename

lon -> east_m

lat -> north_m



# Oruxmaps Swisstopo

Evaluating the size of the maps

## Size of the different maps

### Size of the original Tiffs from swisstopo

| MBytes | filename
|  --:| --
| 273'168 | target/cache_tif/0010
|   3'902 | target/cache_tif/0025
|   1'578 | target/cache_tif/0050
|     450 | target/cache_tif/0100
|   2'229 | target/cache_tif/0200
|     632 | target/cache_tif/0500
|   1'097 | target/cache_tif/1000


### Size of the lossless optimized pngs

| MBytes | saved | filename
|  --:| --:| --
| 2'211 | 56% | target/cache_png/png/0025
|   888 | 56% | target/cache_png/png/0050
|   120 |     | target/cache_png/png/0100
|   150 |     | target/cache_png/png/0200
|    39 |     | target/cache_png/png/0500
|    30 |     | target/cache_png/png/1000

## Size of scale 10k

swiss-map-raster10_2020_1333-1_krel_0.5_2056.tif

| MBytes | saved | reduced | imagetype | Qualification
|  --:| --:| -- | -- | --
| 436'665 |      | | tif
| 182'322 | 41%  | | png
|  24'208 | 5.5% | | jpg 30% quality |  Good quality, little jpg macciato
|  15'577 | 3.5% | | jpg 15% quality
|  65'927 | 15%  | 2 | png              |  Good quality
|  26'047 | 6.0% | 2 | jpg 90% quality
|  10'177 | 2.3% | 2 | jpg 50% quality  |  Good quality but typical jpg macciato

* It seems difficult to fit the 10k on a android phone
* 273.1 GBytes * 5.5% = 15.0 GBytes
* 273.1 GBytes * 3.5% = 9.5 GBytes

Map size: 17500x12000 --> math.gcd(17500, 12000) --> 500

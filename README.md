# orux_swisstopo

# 2025-07-24, Hans Märki

Retrieved newest links from swisstopo and created CH_SwissTopo.zip 3.2G.

# 2024-04-30, Hans Märki

Build using pyenv

```bash
python -m venv .venv_orux
source .venv_orux/bin/activate
python -m pip install --upgrade -r requirements.txt
python create_map_CH_SwissTopo.py
```

## 2021-06-19, Hans Märki

Rewrite a big part. All tifs will first be devided in subtiles of 100x100px.
Then these subtiles are reassembled to tiles of 1000x1000.

This fixes `oruxmap/doc/bug`,

To build the maps (25'000 and higher), the `target` folder will be about 150 GBytes.
target/maps/CH_SwissTopo.zip 3.2G

To build the maps (10'000 and higher), the `target` folder will be much more than 650 GBytes.

## 2021-04-18, Hans Märki

This scripts creates a offline map of the pixelmap of https://map.geo.admin.ch

You may download the map from https://www.maerki.com/hans/orux/CH_SwissTopo.zip.
To use in Orux Maps, download the zip onto your computer and extract it.
Now copy the two resulting files `CH_SwissTopo.otrk2.xml` and `OruxMapsImages.db` onto your android phone into the folder `oruxmaps/mapfiles/CH_SwissTopo`.

The map may be found now in Orux Maps under `OFFLINE` maps.


## TODO: Refactoring rename

The names `lon`, `lat` are difficil to understand: Rename!

lon -> east_m

lat -> north_m



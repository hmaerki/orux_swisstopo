import io

import PIL.Image


# TODO(hans): merge with method below
def _save_purge_palette(fOut, img, skip_optimize_png)->None:
    if skip_optimize_png:
        # optimize=False, compress_level=0: 8ms 480.6kbytes
        # optimize=False, compress_level=1: 13ms 136.7kbytes
        # optimize=False, compress_level=3: 20ms 124.5kbytes
        # optimize=True,  compress_level=9: 502ms 106.1kbytes
        img.save(fOut, format="PNG", optimize=False, compress_level=1)
        return

    if True:
        img = img.quantize(
            colors=256,
            method=PIL.Image.FASTOCTREE,
            kmeans=0,
            palette=None,
            dither=PIL.Image.NONE,
        )
        # 25k, optimize=True,  compress_level=9: 41ms 9.0kbytes
        # 25k, optimize=False, compress_level=9: 41ms 9.0kbytes
        # 25k, optimize=False, compress_level=8: 20ms 9.1kbytes <<-
        # 25k, optimize=False, compress_level=7: 8ms 9.7kbytes
        # 25k, optimize=True,  compress_level=7: 11ms 9.7kbytes
        # optimize=True,  compress_level=9: 56ms 21.6kbytes
        img.save(fOut, format="PNG", optimize=False, compress_level=8)
        return

    img = img.convert("P", palette=PIL.Image.ADAPTIVE)
    # 25k, optimize=False, compress_level=8: 22ms 9.3kbytes
    img.save(fOut, format="PNG", optimize=False, compress_level=8)

def convert_to_png_raw(img, skip_optimize_png: bool) -> bytes:
    with io.BytesIO() as fOut:
        _save_purge_palette(fOut=fOut, img=img, skip_optimize_png=skip_optimize_png)
        return fOut.getvalue()

# TODO(hans): obsolete
def extract_tile(img, topleft_x:int, topleft_y:int, pixel_per_tile:int, skip_optimize_png:bool)-> bytes:
    assert 0 <= topleft_x < img.width
    assert 0 <= topleft_y < img.height
    bottomright_x = topleft_x + pixel_per_tile
    bottomright_y = topleft_y + pixel_per_tile
    assert pixel_per_tile <= bottomright_x <= img.width
    assert pixel_per_tile <= bottomright_y <= img.height
    im_crop = img.crop((topleft_x, topleft_y, bottomright_x, bottomright_y))
    with io.BytesIO() as fOut :
        _save_purge_palette(fOut=fOut, img=im_crop, skip_optimize_png=skip_optimize_png)
        return fOut.getvalue()

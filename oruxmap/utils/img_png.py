import io

import PIL.Image


def _convert_to_png_raw(fOut, img, skip_optimize_png)->None:
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
        _convert_to_png_raw(fOut=fOut, img=img, skip_optimize_png=skip_optimize_png)
        return fOut.getvalue()



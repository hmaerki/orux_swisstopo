import io


def _save_purge_palette(fOut, img, skip_optimize_png):
    if skip_optimize_png:
        # optimize=False, compress_level=0: 8ms 480.6kbytes
        # optimize=False, compress_level=1: 13ms 136.7kbytes
        # optimize=False, compress_level=3: 20ms 124.5kbytes
        # optimize=True,  compress_level=9: 502ms 106.1kbytes
        img.save(fOut, format="PNG", optimize=False, compress_level=1)
        return

    # img = img.convert("RGB")

    # TODO: Go through the color palette and prune similar colors
    if False:
        threshold = 10
        found = True
        histogram = img.histogram()
        for r, g, b in zip(histogram[0:256], histogram[256:512], histogram[512:768]):
            s = r + g + b
            if 0 < s < threshold:
                found = True
                break
        if found:
            # Without: optimize=True, compress_level=9: f40ms 73.3kbytes
            # With:    optimize=True, compress_level=9: 108ms 73.3kbytes
            data = list(img.getdata())
            for i, v in enumerate(data):
                if sum(v) < threshold:
                    data[i] = (0, 0, 0)
            img.putdata(data)

    img = img.quantize(
        colors=256,
        method=PIL.Image.FASTOCTREE,
        kmeans=0,
        palette=None,
        dither=PIL.Image.NONE,
    )
    # optimize=True,  compress_level=9: 56ms 21.6kbytes
    img.save(fOut, format="PNG", optimize=True, compress_level=9)
    # img.save('/tmp/xy.png', format="PNG", optimize=True, compress_level=9)
    return

    img = img.convert("P", palette=PIL.Image.ADAPTIVE)
    # Now the palette is reordered: At the beginning are used colors
    colors = -1
    for v in img.histogram():
        if v > 0:
            colors += 1
    bits = colors.bit_length()
    # Only store the part of the palette which is used
    ## optimize=True,  compress_level=9: 108ms 73.3kbytes
    ## optimize=False, compress_level=3: 103ms 75.0kbytes
    ## optimize=True , compress_level=3: 113ms 73.3kbytes
    ## ..                              : 107ms 57.8kbytes (full image: img.convert("P", palette=PIL.Image.ADAPTIVE)
    # optimize=True,  compress_level=9: 44ms 73.3kbytes
    img.save(fOut, format="PNG", optimize=True, compress_level=9, bits=bits)


def extract_tile(img, topleft_x, topleft_y, pixel_per_tile, skip_optimize_png):
    assert 0 <= topleft_x < img.width
    assert 0 <= topleft_y < img.height
    bottomright_x = topleft_x + pixel_per_tile
    bottomright_y = topleft_y + pixel_per_tile
    assert pixel_per_tile <= bottomright_x <= img.width
    assert pixel_per_tile <= bottomright_y <= img.height
    im_crop = img.crop((topleft_x, topleft_y, bottomright_x, bottomright_y))
    fOut = io.BytesIO()
    _save_purge_palette(fOut=fOut, img=im_crop, skip_optimize_png=skip_optimize_png)
    return fOut.getvalue()

import io
import math

import rasterio
import PIL.Image


def transformCH1903_to_WGS84(fY, fX):
    """
    E entspricht Lambda (8.x), y (7xx)
    N entspricht Phi (46.x), x (2xx)
    """
    y = (fY - 600000.0) / 1000000.0
    x = (fX - 200000.0) / 1000000.0
    fLambda = 2.6779094 + 4.728982 * y + 0.791484 * y * x + 0.1306 * y * x * x - 0.0436 * y * y * y
    fPhi = 16.9023892 + 3.238272 * x - 0.270978 * y * y - 0.002528 * x * x - 0.0447 * y * y * x - 0.0140 * x * x * x
    return fLambda * 100.0 / 36.0, fPhi * 100.0 / 36.0


def save_purge_palette(fOut, img):
    if False:
        img = img.convert("RGB")

        # TODO: Go through the color palette and prune similar colors
        threshold = 10
        data = list(img.getdata())
        for i, v in enumerate(data):
            if sum(v) < threshold:
                data[i] = (0, 0, 0)
        img.putdata(data)

        img = img.convert("P", palette=PIL.Image.ADAPTIVE)
        # Now the palette is reordered: At the beginning are used colors
        colors = -1
        for v in img.histogram():
            if v > 0:
                colors += 1
        bits = colors.bit_length()
    else:
        bits = 8
    # Only store the part of the palette which is used
    img.save(fOut, format="PNG", optimize=True, compress_level=9, bits=bits)


def doit():
    IMG_SIZE = 400

    filename = "swiss-map-raster25_2013_1112_komb_1.25_2056.tif"
    with rasterio.open(filename, "r") as dataset:
        print(dataset.count, dataset.width, dataset.height)
        print(dataset.bounds)
        print(dataset.shape)
        print(dataset.transform)
        print(dataset.crs)
        print(dataset.crs.wkt)
        print(dataset.meta)

        with PIL.Image.open(filename) as img_sample:
            # img_sample.save('test_shading_no.png')
            width = int(img_sample.width)
            height = int(img_sample.height)
            print(math.gcd(width, height))
            assert width % IMG_SIZE == 0
            assert height % IMG_SIZE == 0

            for y in range(height // IMG_SIZE):
                for x in range(width // IMG_SIZE):
                    im_crop = img_sample.crop((x * IMG_SIZE, y * IMG_SIZE, (x + 1) * IMG_SIZE, (y + 1) * IMG_SIZE))
                    filename = f"tile_{y:03d}_{x:03d}.png"
                    fOut = io.BytesIO()
                    save_purge_palette(fOut, im_crop)
                    rawImagedata = fOut.getvalue()
                    print(filename, len(rawImagedata))

                    if x == 10:
                        return


if __name__ == "__main__":
    doit()

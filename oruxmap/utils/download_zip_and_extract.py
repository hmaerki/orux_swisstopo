import io
import pathlib
from zipfile import ZipFile

import requests

class DownloadZipAndExtractTiff:
    FILENAME_ZIP = 'data.zip'

    def __init__(self, url, tiff_filename):
        assert isinstance(url, str)
        assert isinstance(tiff_filename, pathlib.Path)
        self.url = url
        self.tiff_filename = tiff_filename

    def download(self):
        if self.tiff_filename.exists():
            return
        filename_zip = self.tiff_filename.with_name(DownloadZipAndExtractTiff.FILENAME_ZIP)
        if not filename_zip.exists():
            r = requests.get(self.url)
            filename_zip.write_bytes(r.content)

        with ZipFile(filename_zip, 'r') as zip1:
            for info1 in zip1.infolist():
                if info1.filename.endswith('.zip'):
                    with zip1.open(info1, 'r') as f1:
                        data_zip = f1.read()
                        with io.BytesIO(data_zip) as innerfile:
                            with ZipFile(innerfile, "r") as zip2:
                                def extract(iz, filename):
                                    for info2 in iz.infolist():
                                        if info2.filename.endswith(f'/{filename.name}'):
                                            data_tiff = iz.read(info2)
                                            filename.write_bytes(data_tiff)
                                            return
                                    raise Exception(f'{filename_zip}: Failed to find entry {name}')
                                extract(iz=zip2, filename=self.tiff_filename)
                                extract(iz=zip2, filename=self.tiff_filename.with_suffix('.tfw'))
                                return
        raise Exception(f'{filename_zip}: Failed to find entry {self.tiff_filename.name}')

# url = 'https://data.geo.admin.ch/ch.swisstopo.pixelkarte-farbe-pk500.noscale/data.zip'
# tiff_filename = pathlib.Path('/home/hansm/hans/orux_swisstopo/oruxmap/resources/0500/SMR500_KREL.tif')
# d = DownloadZipAndExtractTiff(url=url, tiff_filename=tiff_filename)
# d.download()

# url = 'https://data.geo.admin.ch/ch.swisstopo.pixelkarte-farbe-pk1000.noscale/data.zip'
# tiff_filename = pathlib.Path('/home/hansm/hans/orux_swisstopo/oruxmap/resources/1000/SMR1000_KREL.tif')
# d = DownloadZipAndExtractTiff(url=url, tiff_filename=tiff_filename)
# d.download()

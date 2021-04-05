from dataclasses import dataclass
from oruxmap.utils.projection import CH1903


@dataclass
class LayerParams:
    scale: int
    orux_layer: int
    m_per_pixel: float
    tiff_filename: str = None
    tiff_url: str = None
    align_CH1903: CH1903 = CH1903(lon=0.0, lat=0.0, valid_data=False)

    @property
    def name(self):
        return f"{self.scale:04d}"

    @property
    def m_per_tile(self) -> float:
        return self.pixel_per_tile * self.m_per_pixel

    @property
    def pixel_per_tile(self) -> float:
        return 400

    def verify_m_per_pixel(self, tiff_images: "TiffImage"):
        assert tiff_images.__class__.__name__ == "TiffImage"
        assert abs((tiff_images.m_per_pixel / self.m_per_pixel) - 1.0) < 0.001


LIST_LAYERS = (
    # LayerParams(
    #     scale=5000,
    #     orux_layer=8,
    # ),
    # LayerParams(
    #     scale=2000,
    #     orux_layer=8,
    #     m_per_pixel=32.0,
    # ),
    LayerParams(
        scale=1000,
        orux_layer=10,
        tiff_url="https://data.geo.admin.ch/ch.swisstopo.pixelkarte-farbe-pk1000.noscale/data.zip",
        tiff_filename="SMR1000_KREL.tif",
        m_per_pixel=50.0,
    ),
    LayerParams(
        scale=500,
        orux_layer=11,
        tiff_url="https://data.geo.admin.ch/ch.swisstopo.pixelkarte-farbe-pk500.noscale/data.zip",
        tiff_filename="SMR500_KREL.tif",
        m_per_pixel=25.0,
    ),
    LayerParams(
        scale=200,
        orux_layer=12,
        m_per_pixel=10.0,
        align_CH1903=CH1903(lon=3000.0, lat=2000.0, valid_data=False),
    ),
    LayerParams(scale=100, orux_layer=13, m_per_pixel=5.0),
    LayerParams(scale=50, orux_layer=14, m_per_pixel=2.5),
    LayerParams(scale=25, orux_layer=15, m_per_pixel=1.25),
    LayerParams(scale=10, orux_layer=16, m_per_pixel=0.5),
)

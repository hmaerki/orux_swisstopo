class CH1903:
    """
    http://www.swisstopo.ch/data/geo/naeherung_d.pdf
    http://www.swisstopo.ch/data/geo/refsysd.pdf

    .               SwissGrid     WGS 84
    .               N    E
    Meilen          691  237      47.26954 8.64375
    Hombrechtikon   700  234      47.25052 8.76696
    """

    LON_OFFSET = 2000000.0
    LAT_OFFSET = 1000000.0
    LAT_BERN = 600000.0
    LON_BERN = 200000.0

    def __init__(self, lon: float, lat: float):
        assert isinstance(lon, float)
        assert isinstance(lat, float)
        self.lon = lon
        self.lat = lat
        self.check()

    def check(self):
        assert self.lon > CH1903.LON_OFFSET
        assert CH1903.LAT_OFFSET < self.lat < CH1903.LON_OFFSET

    def to_WGS84(self) -> "WGS84":
        """
        E entspricht Lambda (8.x), y (7xx)
        N entspricht Phi (46.x), x (2xx)
        """
        lan = self.lat - CH1903.LAT_OFFSET
        lon = self.lon - CH1903.LON_OFFSET

        y = (lon - CH1903.LAT_BERN) / 1000000.0
        x = (lan - CH1903.LON_BERN) / 1000000.0
        fLambda = 2.6779094 + 4.728982 * y + 0.791484 * y * x + 0.1306 * y * x * x - 0.0436 * y * y * y
        fPhi = 16.9023892 + 3.238272 * x - 0.270978 * y * y - 0.002528 * x * x - 0.0447 * y * y * x - 0.0140 * x * x * x
        return WGS84(fLambda * 100.0 / 36.0, fPhi * 100.0 / 36.0)


class BoundsCH1903:
    def __init__(self, a: CH1903, b: CH1903):
        assert isinstance(a, CH1903)
        assert isinstance(b, CH1903)
        self.a = a
        self.b = b
        self.check()

    def check(self):
        assert self.a.lon < self.b.lon  # lon
        assert self.a.lat > self.b.lat  # lat

    def to_WGS84(self) -> "BoundsWGS84":
        northWest = self.a.to_WGS84()
        southEast = self.b.to_WGS84()
        # southWest = projection.CH1903_to_WGS84((self.fASwissgrid[LON], self.fBSwissgrid[LAT]))
        southWest = CH1903(self.a.lon, self.b.lat).to_WGS84()
        # northEast = projection.CH1903_to_WGS84((self.fBSwissgrid[LON], self.fASwissgrid[LAT]))
        northEast = CH1903(self.b.lon, self.a.lat).to_WGS84()
        assertWGS84IsNorthWest(northWest, southEast)
        return BoundsWGS84(northWest=northWest, northEast=northEast, southWest=southWest, southEast=southEast)


class WGS84:
    def __init__(self, lon: float, lat: float):
        assert isinstance(lon, float)
        assert isinstance(lat, float)
        self.lon = lon
        self.lat = lat
        self.check()

    def check(self):
        assert 5.0 < self.lon < 12.0
        assert 45.0 < self.lat < 50.0


class BoundsWGS84:
    def __init__(self, northWest: WGS84, northEast: WGS84, southWest: WGS84, southEast: WGS84):
        assert isinstance(northWest, WGS84)
        assert isinstance(northEast, WGS84)
        assert isinstance(southWest, WGS84)
        assert isinstance(southEast, WGS84)
        self.northWest = northWest
        self.northEast = northEast
        self.southWest = southWest
        self.southEast = southEast
        self.check()

    def check(self):
        assert self.northWest.lon < self.northEast.lon  # lon
        assert self.southWest.lon < self.southEast.lon  # lon
        assert self.southWest.lat < self.northWest.lat  # lat
        assert self.southEast.lat < self.northEast.lat  # lat

        assertWGS84IsNorthWest(self.northWest, self.southEast)


# a is north west of b
def assertSwissgridIsNorthWest(bounds: BoundsCH1903):
    assert bounds.a.lon < bounds.b.lon
    assert bounds.a.lat > bounds.b.lat


# a is north west of b
def assertTilesIsNorthWest(a, b):
    assert a[0] < b[0]
    assert a[1] < b[1]


# a is north west of b
def assertPixelsIsNorthWest(a, b):
    assert a[0] < b[0]
    assert a[1] < b[1]


def assertWGS84IsNorthWest(a, b):
    assert a.lon < b.lon
    assert a.lat > b.lat


# def add(a, b):
#     if not isinstance(a, collections.Iterable):
#         a = (a, a)
#     if not isinstance(b, collections.Iterable):
#         b = (b, b)
#     return a[0] + b[0], a[1] + b[1]


# def diff(a, b):
#     if not isinstance(a, collections.Iterable):
#         a = (a, a)
#     if not isinstance(b, collections.Iterable):
#         b = (b, b)
#     return a[0] - b[0], a[1] - b[1]


# def mult(a, b):
#     if not isinstance(a, collections.Iterable):
#         a = (a, a)
#     if not isinstance(b, collections.Iterable):
#         b = (b, b)
#     return (a[0] * b[0], a[1] * b[1])


# def div(a, b):
#     if not isinstance(a, collections.Iterable):
#         a = a, a
#     if not isinstance(b, collections.Iterable):
#         b = b, b
#     return float(a[0]) / b[0], float(a[1]) / b[1]


# def floor(a):
#     return int(math.floor(a[0])), int(math.floor(a[1]))


# def ceil(a):
#     return -int(math.floor(-a[0])), -int(math.floor(-a[1]))


# def min_(a, b):
#     if not isinstance(a, collections.Iterable):
#         a = a, a
#     if not isinstance(b, collections.Iterable):
#         b = b, b
#     return min(a[0], b[0]), min(a[1], b[1])


# def max_(a, b):
#     if not isinstance(a, collections.Iterable):
#         a = a, a
#     if not isinstance(b, collections.Iterable):
#         b = b, b
#     return max(a[0], b[0]), max(a[1], b[1])

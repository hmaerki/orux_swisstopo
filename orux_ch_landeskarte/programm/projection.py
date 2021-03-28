
LON = 0
LAT = 1
LON_OFFSET = 2000000.0
LAT_OFFSET = 1000000.0
LAT_BERN = 600000.0
LON_BERN = 200000.0

class CH1903:
    def __init__(self, lon: float, lat: float):
        assert isinstance(lon, float)
        assert isinstance(lat, float)
        self.lon = lon
        self.lat = lat
        self.check()

    def check(self):
        assert self.lon > LON_OFFSET
        assert LAT_OFFSET < self.lat < LON_OFFSET

    """
    http://www.swisstopo.ch/data/geo/naeherung_d.pdf
    http://www.swisstopo.ch/data/geo/refsysd.pdf

                    SwissGrid ???	 WGS 84
                    N    E
    Meilen          691  237       47.26954 8.64375
    Hombrechtikon   700  234       47.25052 8.76696
    """
    def to_WGS84(self) -> 'WGS84':
        """
        E entspricht Lambda (8.x), y (7xx)
        N entspricht Phi (46.x), x (2xx)
        """
        lan = self.lat - LAT_OFFSET
        lon = self.lon - LON_OFFSET

        y = (lon - LAT_BERN) / 1000000.0
        x = (lan - LON_BERN) / 1000000.0
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
        assert self.a.lon < self.b.lon # lon
        assert self.a.lat > self.b.lat # lat

    def to_WGS84(self) -> 'BoundsWGS84':
        topLeft = self.a.to_WGS84()
        bottomRight = self.b.to_WGS84()
        # bottomLeft = projection.CH1903_to_WGS84((self.fASwissgrid[LON], self.fBSwissgrid[LAT]))
        bottomLeft = CH1903(self.a.lon, self.b.lat).to_WGS84()
        # topRight = projection.CH1903_to_WGS84((self.fBSwissgrid[LON], self.fASwissgrid[LAT]))
        topRight = CH1903(self.b.lon, self.a.lat).to_WGS84()
        assertWGS84IsNorthWest(topLeft, bottomRight)
        return BoundsWGS84(topLeft=topLeft, topRight=topRight, bottomLeft=bottomLeft, bottomRight=bottomRight)

class WGS84:
    def __init__(self, lon: float, lat: float):
        assert isinstance(lon, float)
        assert isinstance(lat, float)
        self.lon = lon
        self.lat = lat
        self.check()

    def check(self):
        assert 5.0 < self.lon < 12.0
        assert 45.0 < self.lat < 48.0

class BoundsWGS84:
    def __init__(self, topLeft:WGS84, topRight:WGS84, bottomLeft:WGS84, bottomRight:WGS84):
        assert isinstance(topLeft, WGS84)
        assert isinstance(topRight, WGS84)
        assert isinstance(bottomLeft, WGS84)
        assert isinstance(bottomRight, WGS84)
        self.topLeft = topLeft
        self.topRight = topRight
        self.bottomLeft = bottomLeft
        self.bottomRight = bottomRight
        self.check()

    def check(self):
        assert self.topLeft.lon < self.topRight.lon # lon
        assert self.bottomLeft.lon < self.bottomRight.lon # lon
        assert self.bottomLeft.lat < self.topLeft.lat # lat
        assert self.bottomRight.lat < self.topRight.lat # lat

        assertWGS84IsNorthWest(self.topLeft, self.bottomRight)



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


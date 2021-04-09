class CH1903:
    """
    http://www.swisstopo.ch/data/geo/naeherung_d.pdf
    http://www.swisstopo.ch/data/geo/refsysd.pdf

    .               SwissGrid     WGS 84
    .               N    E
    Meilen          691  237      47.26954 8.64375
    Hombrechtikon   700  234      47.25052 8.76696
    """

    LON_OFFSET_M = 2000000.0
    LAT_OFFSET_M = 1000000.0
    LAT_OFFSET_OUTSIDE_M = 90000.0  # The 1Mio swiss map is outside the 'allowed' range
    LAT_BERN_M = 600000.0
    LON_BERN_M = 200000.0

    def __init__(self, lon_m: float, lat_m: float, valid_data=True):
        assert isinstance(lon_m, float)
        assert isinstance(lat_m, float)
        self.lon_m = lon_m
        self.lat_m = lat_m
        if valid_data:
            self.check()

    def __repr__(self):
        return f"CH1903({self.lon_m:0.1f}, {self.lat_m:0.1f})"

    def check(self):
        assert self.lon_m > CH1903.LON_OFFSET_M
        assert CH1903.LAT_OFFSET_OUTSIDE_M < self.lat_m < CH1903.LON_OFFSET_M

    @property
    def _iter_value(self):
        yield self.lon_m
        yield self.lat_m

    def minus(self, point: "CH1903") -> "CH1903":
        assert isinstance(point, CH1903)
        return CH1903(lon_m=self.lon_m - point.lon_m, lat_m=self.lat_m - point.lat_m)

    def plus(self, point: "CH1903") -> "CH1903":
        assert isinstance(point, CH1903)
        return CH1903(lon_m=self.lon_m + point.lon_m, lat_m=self.lat_m + point.lat_m)

    def floor(
        self,
        floor_lon_m: float,
        floor_lat_m: float,
    ):
        """
        if floor_lon_x > 0: result will be smaller, else bigger
          val   floor   result
           22     10      10
           22    -10      30
        """
        return CH1903(
            lon_m=self.lon_m - ((self.lon_m) % floor_lon_m),
            lat_m=self.lat_m - ((self.lat_m) % floor_lat_m),
        )

    def to_WGS84(self) -> "WGS84":
        """
        E entspricht Lambda (8.x), y (7xx)
        N entspricht Phi (46.x), x (2xx)
        """
        lan = self.lat_m - CH1903.LAT_OFFSET_M
        lon_m = self.lon_m - CH1903.LON_OFFSET_M

        y = (lon_m - CH1903.LAT_BERN_M) / 1000000.0
        x = (lan - CH1903.LON_BERN_M) / 1000000.0
        fLambda = (
            2.6779094
            + 4.728982 * y
            + 0.791484 * y * x
            + 0.1306 * y * x * x
            - 0.0436 * y * y * y
        )
        fPhi = (
            16.9023892
            + 3.238272 * x
            - 0.270978 * y * y
            - 0.002528 * x * x
            - 0.0447 * y * y * x
            - 0.0140 * x * x * x
        )
        return WGS84(fLambda * 100.0 / 36.0, fPhi * 100.0 / 36.0)


class BoundsCH1903:
    def __init__(self, nw: CH1903, se: CH1903, valid_data=True):
        assert isinstance(nw, CH1903)
        assert isinstance(se, CH1903)
        self.nw = nw
        self.se = se
        if valid_data:
            self.check()

    def __repr__(self):
        return f"BoundsCH1903(({self.nw.lon_m:0.1f},{self.nw.lat_m:0.1f}),({self.se.lon_m:0.1f},{self.se.lat_m:0.1f}))"

    def check(self):
        assert self.nw.lon_m < self.se.lon_m
        assert self.nw.lat_m > self.se.lat_m

    def extend(self, bounds):
        assert isinstance(bounds, BoundsCH1903)
        for x in (bounds.nw, bounds.se):
            self.nw.lon_m = min(self.nw.lon_m, x.lon_m)
            self.se.lon_m = max(self.se.lon_m, x.lon_m)
            self.nw.lat_m = max(self.nw.lat_m, x.lat_m)
            self.se.lat_m = min(self.se.lat_m, x.lat_m)
        self.check()

    @property
    def lon_m(self) -> float:
        v = self.se.lon_m - self.nw.lon_m
        assert v > 0.0
        return v

    @property
    def lat_m(self) -> float:
        v = self.nw.lat_m - self.se.lat_m
        assert v > 0.0
        return v

    @property
    def _iter_value(self):
        yield from self.nw._iter_value
        yield from self.se._iter_value

    def equals(self, bounds: "BoundsCH1903", tolerance_m=0.05) -> bool:
        assert isinstance(bounds, BoundsCH1903)
        for a, b in zip(self._iter_value, bounds._iter_value):
            if abs(a - b) > tolerance_m:
                return False
        return True

    def minus(self, point: CH1903) -> "BoundsCH1903":
        assert isinstance(point, CH1903)
        return BoundsCH1903(nw=self.nw.minus(point), se=self.se.minus(point))

    def plus(self, point: CH1903) -> "BoundsCH1903":
        assert isinstance(point, CH1903)
        return BoundsCH1903(nw=self.nw.plus(point), se=self.se.plus(point))

    @property
    def csv(self) -> str:
        return f"{self.nw.lon_m:0.1f},{self.nw.lat_m:0.1f},{self.se.lon_m:0.1f},{self.se.lat_m:0.1f}"

    @staticmethod
    def csv_header(name: str) -> str:
        return f"{name}.nw.lon_m,{name}.nw.lat_m,{name}.se.lon_m,{name}.se.lat_m"

    def floor(self, floor_m: float):
        """Cut incomplete tiles from top, left, bottom and right"""
        return BoundsCH1903(
            nw=self.nw.floor(
                floor_lon_m=-floor_m,
                floor_lat_m=floor_m,
            ),
            se=self.se.floor(
                floor_lon_m=floor_m,
                floor_lat_m=-floor_m,
            ),
        )

    def to_WGS84(self) -> "BoundsWGS84":
        northWest = self.nw.to_WGS84()
        southEast = self.se.to_WGS84()
        # southWest = projection.CH1903_to_WGS84((self.fASwissgrid[LON], self.fBSwissgrid[LAT]))
        southWest = CH1903(self.nw.lon_m, self.se.lat_m).to_WGS84()
        # northEast = projection.CH1903_to_WGS84((self.fBSwissgrid[LON], self.fASwissgrid[LAT]))
        northEast = CH1903(self.se.lon_m, self.nw.lat_m).to_WGS84()
        assertWGS84IsNorthWest(northWest, southEast)
        return BoundsWGS84(
            northWest=northWest,
            northEast=northEast,
            southWest=southWest,
            southEast=southEast,
        )


def create_boundsCH1903_extrema():
    extrema_NW = CH1903(
        lon_m=CH1903.LON_OFFSET_M + 1.0, lat_m=CH1903.LON_OFFSET_M - 1.0
    )
    extrema_SE = CH1903(
        lon_m=CH1903.LON_OFFSET_M * 2.0, lat_m=CH1903.LAT_OFFSET_M + 1.0
    )
    return BoundsCH1903(nw=extrema_SE, se=extrema_NW, valid_data=False)


class WGS84:
    def __init__(self, lon_m: float, lat_m: float):
        assert isinstance(lon_m, float)
        assert isinstance(lat_m, float)
        self.lon_m = lon_m
        self.lat_m = lat_m
        self.check()

    def check(self):
        assert 3.5 < self.lon_m < 14.0
        assert 44.0 < self.lat_m < 50.0


class BoundsWGS84:
    def __init__(
        self, northWest: WGS84, northEast: WGS84, southWest: WGS84, southEast: WGS84
    ):
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
        assert self.northWest.lon_m < self.northEast.lon_m  # lon_m
        assert self.southWest.lon_m < self.southEast.lon_m  # lon_m
        assert self.southWest.lat_m < self.northWest.lat_m  # lat_m
        assert self.southEast.lat_m < self.northEast.lat_m  # lat_m

        assertWGS84IsNorthWest(self.northWest, self.southEast)


# a is north west of b
def assertSwissgridIsNorthWest(bounds: BoundsCH1903):
    assert bounds.nw.lon_m < bounds.se.lon_m
    assert bounds.nw.lat_m > bounds.se.lat_m


# a is north west of b
def assertTilesIsNorthWest(a, b):
    assert a[0] < b[0]
    assert a[1] < b[1]


# a is north west of b
def assertPixelsIsNorthWest(a, b):
    assert a[0] < b[0]
    assert a[1] < b[1]


def assertWGS84IsNorthWest(a, b):
    assert a.lon_m < b.lon_m
    assert a.lat_m > b.lat_m


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

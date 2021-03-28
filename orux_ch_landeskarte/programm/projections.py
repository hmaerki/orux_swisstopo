LON = 0
LAT = 1
LON_OFFSET = 2000000.0
LAT_OFFSET = 1000000.0
LAT_BERN = 600000.0
LON_BERN = 200000.0

"""
  http://www.swisstopo.ch/data/geo/naeherung_d.pdf
  http://www.swisstopo.ch/data/geo/refsysd.pdf

                  SwissGrid ???	 WGS 84
                  N    E
  Meilen          691  237       47.26954 8.64375
  Hombrechtikon   700  234       47.25052 8.76696
"""
def transformCH1903_to_WGS84(fLon, fLat):
    """
    E entspricht Lambda (8.x), y (7xx)
    N entspricht Phi (46.x), x (2xx)
    """
    assert isinstance(fLat, float)
    assert isinstance(fLon, float)
    assert fLon > LON_OFFSET
    assert LAT_OFFSET < fLat < LON_OFFSET
    fLat -= LAT_OFFSET
    fLon -= LON_OFFSET

    y = (fLon - LAT_BERN) / 1000000.0
    x = (fLat - LON_BERN) / 1000000.0
    fLambda = 2.6779094 + 4.728982 * y + 0.791484 * y * x + 0.1306 * y * x * x - 0.0436 * y * y * y
    fPhi = 16.9023892 + 3.238272 * x - 0.270978 * y * y - 0.002528 * x * x - 0.0447 * y * y * x - 0.0140 * x * x * x
    return fLambda * 100.0 / 36.0, fPhi * 100.0 / 36.0

def assertOrientation(fSwissgrid):
    fA, fB = fSwissgrid
    assert fA[0] > 2000000
    assert fB[0] > 2000000
    assert 1000000 < fA[1] < 2000000
    assert 1000000 < fB[1] < 2000000
    assert fA[0] < fB[0] # lon
    assert fA[1] > fB[1] # lat


def CH1903_to_WGS84(a):
    return transformCH1903_to_WGS84(a[LON], a[LAT])


# a is north west of b
def assertSwissgridIsNorthWest(a, b):
    assert a[0] < b[0]
    assert a[1] > b[1]


# a is north west of b
def assertTilesIsNorthWest(a, b):
    assert a[0] < b[0]
    assert a[1] < b[1]


# a is north west of b
def assertPixelsIsNorthWest(a, b):
    assert a[0] < b[0]
    assert a[1] < b[1]


def assertWGS84IsNorthWest(a, b):
    assert a[LON] < b[LON]
    assert a[LAT] > b[LON]


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


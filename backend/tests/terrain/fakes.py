"""Test doubles for the terrain service: synthetic elevation, source tiles and an SFTP server."""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import rasterio
from rasterio.transform import from_origin

from fieldclub.terrain.catalogue import Catalogue, SourceTile, tile_origin
from fieldclub.terrain.grid import window_for

MIB = 1024 * 1024
NODATA = -3.4028234663852886e38


def ground(shape: tuple[int, int], res: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """Eastings and northings in metres of pixel centres, north up, origin at the top left."""
    rows, cols = np.mgrid[0 : shape[0], 0 : shape[1]].astype(np.float64)
    return (cols + 0.5) * res, -(rows + 0.5) * res


def earthworks(east: np.ndarray, north: np.ndarray, *, slope: float = 0.0) -> np.ndarray:
    """A landscape with a known mound, ditch and bank on a regional slope rising to the east.

    Mound: a 1.5 m Gaussian of 8 m radius at (60, -60). Ditch: 1 m deep and 6
    m wide, running north to south at east = 140. Bank: 0.8 m high and 6 m
    wide at east = 180.
    """
    z = 100.0 + slope * east
    z = z + 1.5 * np.exp(-((east - 60) ** 2 + (north + 60) ** 2) / (2 * 8.0**2))
    z = z - 1.0 * np.exp(-((east - 140) ** 2) / (2 * 3.0**2))
    z = z + 0.8 * np.exp(-((east - 180) ** 2) / (2 * 3.0**2))
    return z.astype(np.float32)


class FunctionSource:
    """Elevation from a formula of Web Mercator position, exact at every pixel of any window."""

    def __init__(
        self, formula: Callable[[np.ndarray, np.ndarray], np.ndarray], *, edition: str = "synthetic"
    ):
        self.formula = formula
        self.edition = edition
        self.cacheable = True
        self.reads: list[tuple[float, float, float, float]] = []
        self.lock = threading.Lock()

    def read(self, bounds: tuple[float, float, float, float], width: int, height: int) -> np.ndarray:
        with self.lock:
            self.reads.append(bounds)
        window = window_for(bounds, width, height)
        xs, ys = np.meshgrid(window.x_centres(), window.y_centres())
        return self.formula(xs, ys).astype(np.float32)


def rolling_hills(xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    """Hills, a ditch and a mound pattern, in metres, varying on scales from 10 m to 2 km."""
    return (
        120
        + 15 * np.sin(xs / 700.0) * np.cos(ys / 900.0)
        + 1.2 * np.sin(xs / 37.0 + ys / 53.0)
        + 0.4 * np.cos(xs / 11.0) * np.sin(ys / 13.0)
    )


def write_source_tile(
    folder: Path,
    name: str,
    *,
    res: float = 4.0,
    formula: Callable[[np.ndarray, np.ndarray], np.ndarray] | None = None,
    width_m: float = 5000,
) -> Path:
    """A 5 km source tile in Defra's layout (float32, LZW, its nodata value), at a coarse resolution."""
    west, south = tile_origin(name)
    size = round(5000 / res)
    # Coastal tiles are cropped: only `width_m` from the west edge, as Defra supplies them.
    width = round(width_m / res)
    cols, rows = np.meshgrid(np.arange(width), np.arange(size))
    east = west + (cols + 0.5) * res
    north = south + 5000 - (rows + 0.5) * res
    formula = formula or (lambda e, n: 100 + 0.01 * e - 0.005 * n + np.sin(e / 50.0) * 2)
    data = formula(east, north).astype(np.float32)
    path = folder / f"{name}_DTM_1m.tif"
    folder.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=width,
        height=size,
        count=1,
        dtype="float32",
        crs="EPSG:27700",
        transform=from_origin(west, south + 5000, res, res),
        nodata=NODATA,
        compress="lzw",
        tiled=True,
        blockxsize=128,
        blockysize=128,
    ) as ds:
        ds.write(data, 1)
    return path


def catalogue_of(paths: Iterable[Path], *, extra: Iterable[str] = ()) -> Catalogue:
    """A catalogue of these source files at their real sizes, plus tiles that exist only in it."""
    tiles = {
        path.name.split("_")[0]: SourceTile(path.name.split("_")[0], path.stat().st_size) for path in paths
    }
    tiles.update({name: SourceTile(name, 1_000) for name in extra})
    return Catalogue("test-edition", tiles)


# --------------------------------------------------------------------------
# SFTP
# --------------------------------------------------------------------------


@dataclass
class FakeServer:
    """A server holding files, which can misbehave the way Defra's does."""

    files: dict[str, bytes]
    # A handle that has sent this many bytes drops the connection, as Defra's does at about 52 MiB.
    drop_after: int = 54_493_184
    # Absolute file offsets at which a read fails once, mid-window.
    fail_at: set[int] = field(default_factory=set)
    # An absolute offset at which every read fails, for a server that never recovers.
    stuck_at: int | None = None
    connections: int = 0
    opens: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def connect(self) -> FakeSession:
        with self.lock:
            self.connections += 1
        return FakeSession(self)


class FakeSession:
    def __init__(self, server: FakeServer) -> None:
        self.server = server
        self.alive = True

    def stat(self, path: str) -> SimpleNamespace:
        self._check()
        if path not in self.server.files:
            raise FileNotFoundError(path)
        return SimpleNamespace(st_size=len(self.server.files[path]))

    def open(self, path: str, mode: str = "r") -> FakeHandle:
        self._check()
        assert "r" in mode, "the downloader only reads"
        if path not in self.server.files:
            raise FileNotFoundError(path)
        self.server.opens += 1
        return FakeHandle(self, self.server.files[path])

    def close(self) -> None:
        self.alive = False

    def _check(self) -> None:
        if not self.alive:
            raise EOFError("the connection is closed")


class FakeHandle:
    def __init__(self, session: FakeSession, data: bytes) -> None:
        self.session = session
        self.data = data
        self.sent = 0

    def readv(self, chunks: list[tuple[int, int]]) -> Iterable[bytes]:
        server = self.session.server
        for offset, length in chunks:
            self.session._check()
            if server.stuck_at is not None and offset <= server.stuck_at < offset + length:
                self.session.alive = False
                raise OSError("Socket exception: connection reset by peer")
            for failure in sorted(server.fail_at):
                if offset <= failure < offset + length:
                    server.fail_at.discard(failure)
                    self.session.alive = False
                    raise OSError("Socket exception: connection reset by peer")
            if self.sent + length > server.drop_after:
                self.session.alive = False
                raise EOFError("Server connection dropped")
            self.sent += length
            yield self.data[offset : offset + length]

    def close(self) -> None:
        pass

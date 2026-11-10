"""Just enough of a Mapbox vector tile decoder to check what the record tiles hold.

Reads the protobuf wire format of the vector tile 2.1 spec by hand: layers,
features with their ids, properties and type, and the first point of each
geometry in tile units. Anything malformed raises, which is the point: a
tile this can't read is not a valid tile.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Any

GEOMETRY_TYPES = {0: "Unknown", 1: "Point", 2: "LineString", 3: "Polygon"}


@dataclass
class Feature:
    id: int | None
    type: str
    properties: dict[str, Any]
    # The first point, in tile units from the top-left corner.
    first: tuple[int, int] | None


@dataclass
class Layer:
    name: str
    extent: int
    features: list[Feature] = field(default_factory=list)


def _varint(data: bytes, at: int) -> tuple[int, int]:
    value = shift = 0
    while True:
        if at >= len(data):
            raise ValueError("varint runs past the end")
        byte = data[at]
        at += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, at
        shift += 7
        if shift > 63:
            raise ValueError("varint too long")


def _fields(data: bytes) -> list[tuple[int, int, Any]]:
    """`(field number, wire type, value)` for each field of a message."""
    out: list[tuple[int, int, Any]] = []
    at = 0
    while at < len(data):
        key, at = _varint(data, at)
        number, wire = key >> 3, key & 7
        if wire == 0:
            value, at = _varint(data, at)
        elif wire == 1:
            value, at = data[at : at + 8], at + 8
        elif wire == 2:
            length, at = _varint(data, at)
            value, at = data[at : at + length], at + length
            if at > len(data):
                raise ValueError("field runs past the end")
        elif wire == 5:
            value, at = data[at : at + 4], at + 4
        else:
            raise ValueError(f"unsupported wire type {wire}")
        out.append((number, wire, value))
    return out


def _packed(data: bytes) -> list[int]:
    values, at = [], 0
    while at < len(data):
        value, at = _varint(data, at)
        values.append(value)
    return values


def _zigzag(value: int) -> int:
    return (value >> 1) ^ -(value & 1)


def _value(data: bytes) -> Any:
    for number, _, raw in _fields(data):
        if number == 1:
            return raw.decode("utf-8")
        if number == 2:
            return struct.unpack("<f", raw)[0]
        if number == 3:
            return struct.unpack("<d", raw)[0]
        if number in (4, 5):
            return raw
        if number == 6:
            return _zigzag(raw)
        if number == 7:
            return bool(raw)
    raise ValueError("empty value")


def _layer(data: bytes) -> Layer:
    name, extent, keys, values, raw_features = "", 4096, [], [], []
    for number, _, raw in _fields(data):
        if number == 1:
            name = raw.decode("utf-8")
        elif number == 2:
            raw_features.append(raw)
        elif number == 3:
            keys.append(raw.decode("utf-8"))
        elif number == 4:
            values.append(_value(raw))
        elif number == 5:
            extent = raw
    layer = Layer(name, extent)
    for raw in raw_features:
        feature_id, tags, kind, geometry = None, [], 0, []
        for number, _, value in _fields(raw):
            if number == 1:
                feature_id = value
            elif number == 2:
                tags = _packed(value)
            elif number == 3:
                kind = value
            elif number == 4:
                geometry = _packed(value)
        assert len(tags) % 2 == 0, "tags come in key, value pairs"
        properties = {keys[tags[i]]: values[tags[i + 1]] for i in range(0, len(tags), 2)}
        first = None
        if len(geometry) >= 3 and geometry[0] & 7 == 1:
            first = (_zigzag(geometry[1]), _zigzag(geometry[2]))
        layer.features.append(Feature(feature_id, GEOMETRY_TYPES[kind], properties, first))
    return layer


def decode(tile: bytes) -> dict[str, Layer]:
    """Every layer of a tile by name. An empty tile has none."""
    layers = {}
    for number, wire, raw in _fields(tile):
        assert number == 3, f"a tile holds only layers, not field {number}"
        assert wire == 2, "a layer is length-delimited"
        layer = _layer(raw)
        layers[layer.name] = layer
    return layers

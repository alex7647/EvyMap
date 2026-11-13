"""Геометрия объектов. Координаты нормализованы (0..1) относительно подложки этажа,
поэтому замена фото на более качественное не ломает разметку."""
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, TypeAdapter

Coord = Annotated[float, Field(ge=0.0, le=1.0)]
XY = tuple[Coord, Coord]
GeometryKind = Literal["point", "polygon", "line"]


class Point(BaseModel):
    type: Literal["point"] = "point"
    x: Coord
    y: Coord

    def centroid(self) -> tuple[float, float]:
        return (self.x, self.y)


class _Path(BaseModel):
    points: list[XY]

    def centroid(self) -> tuple[float, float]:
        n = len(self.points)
        return (sum(p[0] for p in self.points) / n, sum(p[1] for p in self.points) / n)


class Polygon(_Path):
    type: Literal["polygon"] = "polygon"
    points: Annotated[list[XY], Field(min_length=3, max_length=500)]


class Line(_Path):
    type: Literal["line"] = "line"
    points: Annotated[list[XY], Field(min_length=2, max_length=500)]


Geometry = Annotated[Union[Point, Polygon, Line], Field(discriminator="type")]
geometry_adapter = TypeAdapter(Geometry)

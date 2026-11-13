"""Обработка фото плана: нормализация (EXIF-поворот, удаление метаданных), перспективное
выравнивание по 4 углам, сжатие в WebP. ImageStore — абстракция хранилища (локально / S3)."""
import io
import math
from abc import ABC, abstractmethod
from pathlib import Path

from PIL import Image, ImageOps

Image.MAX_IMAGE_PIXELS = 100_000_000  # защита от «бомб» распаковки


class ImageError(ValueError):
    pass


class ImageStore(ABC):
    @abstractmethod
    def save(self, rel: str, data: bytes) -> None: ...

    @abstractmethod
    def read(self, rel: str) -> bytes | None: ...

    @abstractmethod
    def delete(self, rel: str) -> None: ...


class LocalImageStore(ImageStore):
    """Файлы под root/public (раздаются как /media) и root/private (оригиналы, наружу не отдаются)."""

    def __init__(self, root: Path):
        self.root = Path(root)
        (self.root / "public").mkdir(parents=True, exist_ok=True)
        (self.root / "private").mkdir(parents=True, exist_ok=True)

    def _path(self, rel: str) -> Path:
        p = (self.root / rel).resolve()
        if self.root.resolve() not in p.parents:
            raise ValueError("path outside media root")
        return p

    def save(self, rel, data):
        p = self._path(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def read(self, rel):
        p = self._path(rel)
        return p.read_bytes() if p.exists() else None

    def delete(self, rel):
        self._path(rel).unlink(missing_ok=True)


def normalize(raw: bytes) -> Image.Image:
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
        img = ImageOps.exif_transpose(img).convert("RGB")  # конвертация в RGB отбрасывает EXIF/GPS
    except Exception as e:
        raise ImageError("не удалось прочитать изображение (JPEG, PNG, WebP)") from e
    img.thumbnail((8000, 8000))
    return img


def to_jpeg(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def from_jpeg(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data)).convert("RGB")


def _solve(a: list[list[float]], b: list[float]) -> list[float]:
    n = len(b)
    m = [row[:] + [v] for row, v in zip(a, b)]
    for i in range(n):
        p = max(range(i, n), key=lambda r: abs(m[r][i]))
        if abs(m[p][i]) < 1e-12:
            raise ImageError("углы заданы некорректно")
        m[i], m[p] = m[p], m[i]
        for r in range(n):
            if r != i:
                f = m[r][i] / m[i][i]
                for c in range(i, n + 1):
                    m[r][c] -= f * m[i][c]
    return [m[i][n] / m[i][i] for i in range(n)]


def _perspective_coeffs(out_pts, in_pts) -> list[float]:
    """Коэффициенты Image.PERSPECTIVE: точка результата (x, y) -> точка исходника (X, Y)."""
    a, b = [], []
    for (x, y), (X, Y) in zip(out_pts, in_pts):
        a.append([x, y, 1, 0, 0, 0, -x * X, -y * X]); b.append(X)
        a.append([0, 0, 0, x, y, 1, -x * Y, -y * Y]); b.append(Y)
    return _solve(a, b)


def render_base(img: Image.Image, corners=None, max_px: int = 4096) -> tuple[bytes, tuple[int, int]]:
    """Возвращает (WebP-байты, (ширина, высота)). corners — 4 угла (tl, tr, br, bl), доли 0..1."""
    if corners:
        w0, h0 = img.size
        tl, tr, br, bl = [(x * w0, y * h0) for x, y in corners]
        w = int(max(math.dist(tl, tr), math.dist(bl, br)))
        h = int(max(math.dist(tl, bl), math.dist(tr, br)))
        if w < 50 or h < 50:
            raise ImageError("выбранная область слишком мала")
        coeffs = _perspective_coeffs([(0, 0), (w, 0), (w, h), (0, h)], [tl, tr, br, bl])
        img = img.transform((w, h), Image.PERSPECTIVE, coeffs, Image.BICUBIC)
    else:
        img = img.copy()
    img.thumbnail((max_px, max_px))
    buf = io.BytesIO()
    img.save(buf, "WEBP", quality=82)
    return buf.getvalue(), img.size

"""Detecção de formato e normalização local de uploads de mídia."""

from __future__ import annotations

import io
import struct

MARCAS_HEIF = frozenset({b"heic", b"heix", b"heim", b"mif1", b"msf1"})


def _marcas_ftyp(conteudo: bytes) -> tuple[bytes, ...]:
    """Lê marcas alinhadas da primeira caixa ``ftyp`` ISO-BMFF."""
    if len(conteudo) < 16 or conteudo[4:8] != b"ftyp":
        return ()
    tamanho = struct.unpack(">I", conteudo[:4])[0]
    if tamanho < 16 or tamanho > len(conteudo):
        return ()
    # Marca principal em 8; os quatro bytes seguintes são a minor_version.
    marcas = [conteudo[8:12]]
    marcas.extend(
        conteudo[posicao : posicao + 4]
        for posicao in range(16, tamanho - 3, 4)
    )
    return tuple(marcas)


def eh_heif(conteudo: bytes, mime_declarado: str = "") -> bool:
    """Decide se o conteúdo é HEIF sem confundir o mesmo container com MP4."""
    mime = (mime_declarado or "").split(";", 1)[0].strip().lower()
    if mime in {"image/heic", "image/heif"}:
        return True
    return any(marca in MARCAS_HEIF for marca in _marcas_ftyp(conteudo))


def detectar_mime(conteudo: bytes) -> str | None:
    """Detecta os formatos aceitos pelos bytes, sem confiar no nome ou mime."""
    if eh_heif(conteudo):
        return "image/heic"
    if conteudo.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if conteudo.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if conteudo.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if (
        len(conteudo) >= 16
        and conteudo.startswith(b"RIFF")
        and conteudo[8:12] == b"WEBP"
        and conteudo[12:16] in {b"VP8 ", b"VP8L", b"VP8X"}
    ):
        return "image/webp"
    if conteudo.startswith(b"\x1a\x45\xdf\xa3"):
        return "video/webm"

    marcas = _marcas_ftyp(conteudo)
    if marcas:
        if b"qt  " in marcas:
            return "video/quicktime"
        return "video/mp4"
    return None


def normalizar(
    conteudo: bytes,
    mime_declarado: str = "",
    nome_arquivo: str = "",
) -> tuple[bytes, str, bool]:
    """Converte HEIF para JPEG; os demais formatos permanecem byte a byte."""
    if not eh_heif(conteudo, mime_declarado):
        return conteudo, detectar_mime(conteudo) or mime_declarado, False

    try:
        import pillow_heif
        from PIL import Image, ImageOps

        pillow_heif.register_heif_opener()
        with Image.open(io.BytesIO(conteudo)) as imagem:
            orientada = ImageOps.exif_transpose(imagem)
            if orientada.mode != "RGB":
                orientada = orientada.convert("RGB")
            saida = io.BytesIO()
            orientada.save(saida, format="JPEG", quality=92, optimize=True)
    except Exception as exc:
        nome = f" {nome_arquivo!r}" if nome_arquivo else ""
        raise ValueError(f"não foi possível converter o arquivo HEIF{nome}: {exc}") from exc
    return saida.getvalue(), "image/jpeg", True



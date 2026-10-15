"""Turn PDFs, images, and text files into page images."""

from __future__ import annotations

import os
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont, ImageOps

from spoolmate.papers import paper_inches as catalog_inches
from spoolmate.papers import paper_name

Image.MAX_IMAGE_PIXELS = 40_000_000

MAX_RENDER_SIDE = 6000
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp"}
TEXT_EXTS = {".txt", ".log", ".csv"}
TYPE_LABELS = {
    ".pdf": "PDF",
    ".png": "PNG",
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".bmp": "BMP",
    ".gif": "GIF",
    ".tif": "TIFF",
    ".tiff": "TIFF",
    ".webp": "WEBP",
    ".txt": "TXT",
    ".log": "LOG",
    ".csv": "CSV",
}
TEXT_PAGE_LIMIT = 400
TEXT_BYTE_LIMIT = 5_000_000


class RenderError(Exception):
    """The file could not be turned into pages."""


def extension_of(path: str) -> str:
    return os.path.splitext(path)[1].lower()


def classify(path: str) -> tuple[str, str]:
    ext = extension_of(path)
    if ext == ".pdf":
        return "pdf", "PDF"
    if ext in IMAGE_EXTS:
        return "image", TYPE_LABELS[ext]
    if ext in TEXT_EXTS:
        return "text", TYPE_LABELS[ext]
    return "other", TYPE_LABELS.get(ext, ext.replace(".", "").upper() or "FILE")


def allowed_extensions(settings: dict) -> set[str]:
    enabled = settings.get("types") or {}
    exts: set[str] = set()
    if enabled.get("pdf", True):
        exts.add(".pdf")
    if enabled.get("images", True):
        exts.update(IMAGE_EXTS)
    if enabled.get("text", True):
        exts.update(TEXT_EXTS)
    return exts


def is_allowed(path: str, settings: dict) -> bool:
    return extension_of(path) in allowed_extensions(settings)


def inspect_pages(path: str, settings: dict) -> int:
    source = open_source(path, settings)
    try:
        return source.page_count
    finally:
        source.close()


def open_source(path: str, settings: dict) -> "PageSource":
    kind, _label = classify(path)
    if kind == "other":
        raise RenderError("This file type is not supported")
    if not os.path.isfile(path):
        raise RenderError("The file is no longer there")
    return PageSource(path, kind, settings)


def prepare(image: Image.Image, settings: dict) -> Image.Image:
    image = flatten(image)
    rotate = int(settings.get("rotate") or 0) % 360
    if rotate:
        image = image.rotate(-rotate, expand=True, fillcolor="white")
    if settings.get("color") == "grayscale":
        image = image.convert("L").convert("RGB")
    cap_w, cap_h, _dpi = _paper_pixels(settings)
    if image.width > cap_w or image.height > cap_h:
        image = image.copy()
        image.thumbnail((cap_w, cap_h), Image.Resampling.LANCZOS)
    return image


def is_blank_page(image: Image.Image, threshold: int = 250) -> bool:
    """True when nearly all pixels are near-white."""
    rgb = flatten(image).convert("RGB")
    sample = rgb.resize((64, 64), Image.Resampling.BILINEAR)
    pixels = list(sample.getdata())
    if not pixels:
        return True
    dark = sum(1 for px in pixels if min(px) < threshold)
    return dark < max(3, len(pixels) // 200)


def decorate_page(image: Image.Image, settings: dict, *, page: int = 1, page_count: int = 1, name: str = "") -> Image.Image:
    """Apply watermark and header/footer stamps."""
    image = flatten(image).convert("RGB")
    wm = settings.get("watermark") or {}
    if wm.get("behind"):
        image = apply_watermark(image, settings, page=page)
    image = apply_stamps(image, settings, page=page, page_count=page_count, name=name)
    if not wm.get("behind"):
        image = apply_watermark(image, settings, page=page)
    return image


def apply_stamps(image: Image.Image, settings: dict, *, page: int, page_count: int, name: str = "") -> Image.Image:
    stamps = settings.get("stamps") or {}
    fields = [
        stamps.get("header_left") or "",
        stamps.get("header_center") or "",
        stamps.get("header_right") or "",
        stamps.get("footer_left") or "",
        stamps.get("footer_center") or "",
        stamps.get("footer_right") or "",
    ]
    if not any(fields):
        return image
    out = image.copy()
    draw = ImageDraw.Draw(out)
    size = max(8, int(stamps.get("font_size") or 8))
    font = _font(size)
    margin = max(8, size)
    width, height = out.size
    values = [_expand_stamp(text, page=page, page_count=page_count, name=name) for text in fields]

    def place(text: str, x_mode: str, y: int) -> None:
        if not text:
            return
        box = draw.textbbox((0, 0), text, font=font)
        tw = box[2] - box[0]
        if x_mode == "left":
            x = margin
        elif x_mode == "right":
            x = width - margin - tw
        else:
            x = (width - tw) // 2
        draw.text((x, y), text, font=font, fill=(60, 60, 60))

    place(values[0], "left", margin)
    place(values[1], "center", margin)
    place(values[2], "right", margin)
    footer_y = height - margin - size - 2
    place(values[3], "left", footer_y)
    place(values[4], "center", footer_y)
    place(values[5], "right", footer_y)
    return out


def apply_watermark(image: Image.Image, settings: dict, *, page: int) -> Image.Image:
    wm = settings.get("watermark") or {}
    text = str(wm.get("text") or "").strip()
    image_path = str(wm.get("image") or "").strip()
    if not text and not image_path:
        return image
    page_range = str(wm.get("page_range") or "").strip()
    if page_range:
        try:
            from spoolmate.pages import parse_range

            allowed = parse_range(page_range, max(page, 1))
            if page not in allowed:
                return image
        except ValueError:
            pass
    out = image.copy().convert("RGBA")
    overlay = Image.new("RGBA", out.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    intensity = max(1, min(100, int(wm.get("intensity") or 15)))
    alpha = max(20, min(200, int(255 * intensity / 100)))
    angle = int(wm.get("angle") or 45)
    if text:
        size = int(wm.get("font_size") or 0) or max(24, out.width // 12)
        font = _font(size)
        fill = (120, 120, 120, alpha)
        box = draw.textbbox((0, 0), text, font=font)
        tw, th = box[2] - box[0], box[3] - box[1]
        layer = Image.new("RGBA", (tw + 40, th + 40), (0, 0, 0, 0))
        ImageDraw.Draw(layer).text((20, 20), text, font=font, fill=fill)
        if wm.get("outline"):
            ImageDraw.Draw(layer).text((20, 20), text, font=font, fill=(255, 255, 255, alpha // 2))
        layer = layer.rotate(angle, expand=True, fillcolor=(0, 0, 0, 0))
        x, y = _watermark_xy(out.size, layer.size, wm)
        overlay.alpha_composite(layer, (x, y))
    if image_path and os.path.isfile(image_path):
        try:
            mark = Image.open(image_path).convert("RGBA")
            pct = max(1, min(100, int(wm.get("image_size") or 40))) / 100.0
            target = max(16, int(min(out.size) * pct))
            mark.thumbnail((target, target), Image.Resampling.LANCZOS)
            if alpha < 255:
                r, g, b, a = mark.split()
                a = a.point(lambda v: int(v * alpha / 255))
                mark = Image.merge("RGBA", (r, g, b, a))
            if angle:
                mark = mark.rotate(angle, expand=True, fillcolor=(0, 0, 0, 0))
            x, y = _watermark_xy(out.size, mark.size, wm)
            overlay.alpha_composite(mark, (x, y))
        except OSError:
            pass
    return Image.alpha_composite(out, overlay).convert("RGB")


def _watermark_xy(page_size, mark_size, wm: dict) -> tuple[int, int]:
    pw, ph = page_size
    mw, mh = mark_size
    hx = str(wm.get("position_h") or "center").lower()
    vy = str(wm.get("position_v") or "middle").lower()
    ox = int(wm.get("offset_x") or 0)
    oy = int(wm.get("offset_y") or 0)
    if hx == "left":
        x = 20
    elif hx == "right":
        x = pw - mw - 20
    else:
        x = (pw - mw) // 2
    if vy == "top":
        y = 20
    elif vy == "bottom":
        y = ph - mh - 20
    else:
        y = (ph - mh) // 2
    return x + ox, y + oy


def _expand_stamp(text: str, *, page: int, page_count: int, name: str) -> str:
    return (
        str(text or "")
        .replace("{page}", str(page))
        .replace("{pages}", str(page_count))
        .replace("{name}", name or "")
        .replace("{date}", datetime.now().strftime("%Y-%m-%d"))
    )


def compose_nup(images: list[Image.Image | None], settings: dict) -> Image.Image:
    """Compose page images onto one sheet (n-up / booklet face)."""
    from spoolmate.pages import nup_grid

    n_up = 2 if settings.get("booklet") else int(settings.get("n_up") or 1)
    cols, rows = nup_grid(n_up)
    sheet_w, sheet_h, _dpi = _paper_pixels(settings)
    if settings.get("booklet") or (settings.get("orientation") == "landscape" and n_up == 2):
        # Booklet faces are typically landscape relative to the final fold.
        pass
    sheet = Image.new("RGB", (sheet_w, sheet_h), "white")
    cell_w = sheet_w // cols
    cell_h = sheet_h // rows
    order = str(settings.get("n_up_order") or "rowsright").lower()
    slots = cols * rows
    while len(images) < slots:
        images.append(None)
    positions = list(range(slots))
    for index, image in enumerate(images[:slots]):
        if image is None:
            continue
        slot = positions[index]
        if order == "rowsleft":
            row, col = divmod(slot, cols)
            col = cols - 1 - col
        elif order == "colsdown":
            col, row = divmod(slot, rows)
        elif order == "colsup":
            col, row = divmod(slot, rows)
            row = rows - 1 - row
        else:
            row, col = divmod(slot, cols)
        cell = Image.new("RGB", (cell_w, cell_h), "white")
        fitted = flatten(image).convert("RGB")
        fitted.thumbnail((max(1, cell_w - 8), max(1, cell_h - 8)), Image.Resampling.LANCZOS)
        ox = (cell_w - fitted.width) // 2
        oy = (cell_h - fitted.height) // 2
        cell.paste(fitted, (ox, oy))
        if settings.get("n_up_border") or settings.get("crop_marks"):
            draw = ImageDraw.Draw(cell)
            draw.rectangle((1, 1, cell_w - 2, cell_h - 2), outline=(180, 180, 180))
        sheet.paste(cell, (col * cell_w, row * cell_h))
    if settings.get("crop_marks"):
        sheet = _draw_crop_marks(sheet)
    return sheet


def _draw_crop_marks(image: Image.Image) -> Image.Image:
    out = image.copy()
    draw = ImageDraw.Draw(out)
    w, h = out.size
    mark = max(8, min(w, h) // 40)
    for x, y, dx, dy in (
        (0, 0, 1, 0),
        (0, 0, 0, 1),
        (w - 1, 0, -1, 0),
        (w - 1, 0, 0, 1),
        (0, h - 1, 1, 0),
        (0, h - 1, 0, -1),
        (w - 1, h - 1, -1, 0),
        (w - 1, h - 1, 0, -1),
    ):
        draw.line((x, y, x + dx * mark, y + dy * mark), fill=(0, 0, 0), width=1)
    return out


def labeled_separator(settings: dict, title: str) -> Image.Image:
    width, height, dpi = _paper_pixels(settings)
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    font = _font(max(18, int(dpi * 0.28)))
    small = _font(max(12, int(dpi * 0.14)))
    draw.text((int(dpi * 0.6), int(height * 0.4)), title or "Separator", font=font, fill=(40, 40, 40))
    draw.text((int(dpi * 0.6), int(height * 0.4) + int(dpi * 0.4)), datetime.now().strftime("%Y-%m-%d %H:%M"), font=small, fill=(120, 120, 120))
    return image


def orientation_for(image: Image.Image, setting: str) -> str:
    if setting == "portrait":
        return "portrait"
    if setting == "landscape":
        return "landscape"
    return "landscape" if image.width > image.height else "portrait"


def render_test_page(settings: dict) -> Image.Image:
    width, height, dpi = _paper_pixels(settings)
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    header = int(dpi * 0.95)
    draw.rectangle((0, 0, width, header), fill=(47, 111, 237))
    title_font = _font(int(dpi * 0.34))
    body_font = _font(int(dpi * 0.16))
    small_font = _font(int(dpi * 0.12))
    draw.text((int(dpi * 0.45), int(dpi * 0.24)), "SpoolMate", font=title_font, fill="white")

    lines = [
        "Test page",
        settings.get("printer") or "No printer selected",
        datetime.now().strftime("%B %d, %Y  %H:%M"),
        f"Paper: {paper_name(str(settings.get('paper') or 'letter'))}",
        f"Orientation: {settings.get('orientation', 'auto')}",
        f"Color: {settings.get('color', 'color')}",
        f"Sides: {_duplex_label(settings.get('duplex', 'simplex'))}",
    ]
    y = header + int(dpi * 0.35)
    for index, line in enumerate(lines):
        font = body_font if index == 0 else small_font
        draw.text((int(dpi * 0.5), y), line, font=font, fill=(31, 41, 51))
        y += int(dpi * (0.34 if index == 0 else 0.26))

    colors = [
        (214, 48, 48),
        (31, 157, 87),
        (47, 111, 237),
        (0, 174, 199),
        (214, 64, 176),
        (240, 196, 40),
        (32, 32, 32),
        (190, 190, 190),
    ]
    bar_top = y + int(dpi * 0.25)
    bar_h = int(dpi * 0.55)
    gap = int(dpi * 0.12)
    left = int(dpi * 0.5)
    bar_w = max(8, int((width - left * 2 - gap * (len(colors) - 1)) / len(colors)))
    for index, color in enumerate(colors):
        x = left + index * (bar_w + gap)
        draw.rectangle((x, bar_top, x + bar_w, bar_top + bar_h), fill=color)

    note = "If this page is sharp and the colors are distinct, the printer is ready."
    draw.text((int(dpi * 0.5), bar_top + bar_h + int(dpi * 0.35)), note, font=small_font, fill=(82, 96, 109))
    _draw_marks(draw, width, height, int(dpi * 0.38))
    return image


class PageSource:
    def __init__(self, path: str, kind: str, settings: dict):
        self.path = path
        self.kind = kind
        self.settings = settings
        self._pdf = None
        self._image = None
        self._text_pages: list[list[str]] | None = None
        if kind == "pdf":
            self._pdf = _open_pdf(path)
            self.page_count = len(self._pdf)
        elif kind == "image":
            try:
                self._image = Image.open(path)
                self._image.load()
            except Exception as exc:
                raise RenderError(f"Could not open this image ({exc})") from exc
            self.page_count = _frame_count(self._image)
        else:
            self._text_pages = _layout_text(path, settings)
            self.page_count = len(self._text_pages)
        if self.page_count <= 0:
            raise RenderError("This file has no pages")

    def close(self) -> None:
        if self._pdf is not None:
            self._pdf.close()
            self._pdf = None
        if self._image is not None:
            self._image.close()
            self._image = None

    def render(self, index: int, target: str) -> Image.Image:
        if index < 0 or index >= self.page_count:
            raise RenderError(f"Page {index + 1} is not in this file")
        if self.kind == "pdf":
            return _render_pdf_page(self._pdf, index, target, self.settings)
        if self.kind == "image":
            return _render_image_frame(self._image, index)
        assert self._text_pages is not None
        dpi = 140 if target == "preview" else output_dpi(self.settings)
        return _draw_text_page(
            self._text_pages[index],
            os.path.basename(self.path),
            index,
            self.page_count,
            self.settings,
            dpi=dpi,
        )


def flatten(image: Image.Image) -> Image.Image:
    image = ImageOps.exif_transpose(image) or image
    if image.mode == "RGB":
        return image
    has_alpha = image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info)
    if has_alpha:
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, "white")
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    return image.convert("RGB")


def _open_pdf(path: str):
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise RenderError("PDF support is not installed.") from exc
    try:
        return pdfium.PdfDocument(path)
    except Exception as exc:
        message = str(exc)
        lowered = message.lower()
        if "password" in lowered or "encrypt" in lowered:
            raise RenderError("This PDF is password protected") from exc
        raise RenderError(f"Could not open this PDF ({message})") from exc


def _render_pdf_page(pdf, index: int, target: str, settings: dict | None = None) -> Image.Image:
    page = pdf[index]
    try:
        width, height = page.get_size()
        width = float(width) or 1
        height = float(height) or 1
        if target == "preview":
            scale = min(1000 / width, 1000 / height)
        else:
            scale = output_dpi(settings or {}) / 72
            long_side = max(width, height) * scale
            if long_side > MAX_RENDER_SIDE:
                scale *= MAX_RENDER_SIDE / long_side
        bitmap = page.render(scale=scale)
        return flatten(bitmap.to_pil())
    finally:
        page.close()


def _frame_count(image: Image.Image) -> int:
    if image.format == "TIFF":
        return int(getattr(image, "n_frames", 1) or 1)
    return 1


def _render_image_frame(image: Image.Image, index: int) -> Image.Image:
    if image.format == "TIFF" and _frame_count(image) > 1:
        image.seek(index)
    frame = image.copy()
    frame.load()
    return flatten(frame)


def paper_inches(settings: dict) -> tuple[float, float]:
    """Physical page size in inches for preview/text layout."""
    custom_w = float(settings.get("custom_paper_width") or 0)
    custom_h = float(settings.get("custom_paper_height") or 0)
    if custom_w >= 20 and custom_h >= 20:
        return custom_w / 25.4, custom_h / 25.4
    paper = str(settings.get("paper") or "letter").lower()
    if paper == "default":
        paper = "letter"
    return catalog_inches(paper)


def output_dpi(settings: dict) -> int:
    """Dots per inch used when a page is drawn for the printer."""
    try:
        dpi = int((settings or {}).get("image_dpi") or 300)
    except (TypeError, ValueError):
        dpi = 300
    return min(1200, max(72, dpi))


def blank_page(settings: dict, dpi: int | None = None):
    """Solid white page used to pad duplex jobs onto a front side."""
    width, height, _dpi = _paper_pixels(settings, dpi=dpi)
    return Image.new("RGB", (width, height), "white")


def _paper_pixels(settings: dict, dpi: int | None = None) -> tuple[int, int, int]:
    dpi = output_dpi(settings) if dpi is None else int(dpi)
    width_in, height_in = paper_inches(settings)
    if settings.get("orientation") == "landscape":
        width_in, height_in = height_in, width_in
    width = max(1, int(width_in * dpi))
    height = max(1, int(height_in * dpi))
    long_side = max(width, height)
    if long_side > MAX_RENDER_SIDE:
        scale = MAX_RENDER_SIDE / long_side
        width = max(1, int(width * scale))
        height = max(1, int(height * scale))
        dpi = max(72, int(dpi * scale))
    return width, height, dpi


def _layout_text(path: str, settings: dict) -> list[list[str]]:
    size = os.path.getsize(path)
    if size > TEXT_BYTE_LIMIT:
        raise RenderError("This text file is too large to print")
    try:
        text = open(path, "r", encoding="utf-8", errors="replace").read()
    except OSError as exc:
        raise RenderError(f"Could not read this file ({exc})") from exc
    text = text.replace("\t", "    ").replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip():
        text = "(This file is empty.)"

    width, height, dpi = _paper_pixels(settings, dpi=140)
    text_settings = settings.get("text") or {}
    pt = max(4, int(text_settings.get("size") or 9))
    spacing = max(50, int(text_settings.get("line_spacing") or 100)) / 100.0
    margin = int(dpi * 0.7)
    footer = int(dpi * 0.4)
    font = _font(max(12, int(dpi * pt / 72)))
    line_height = int(_font_size(font) * 1.4 * spacing)
    max_width = max(40, width - margin * 2)
    usable = max(line_height, height - margin - footer - margin)
    per_page = max(1, usable // line_height)

    probe = Image.new("RGB", (10, 10))
    draw = ImageDraw.Draw(probe)
    lines = _wrap(draw, text, font, max_width)
    pages = [lines[start : start + per_page] for start in range(0, len(lines), per_page)] or [[]]
    if len(pages) > TEXT_PAGE_LIMIT:
        raise RenderError(f"This text file is longer than {TEXT_PAGE_LIMIT} pages. Split it and try again.")
    return pages


def _draw_text_page(lines: list[str], name: str, index: int, total: int, settings: dict, dpi: int | None = None) -> Image.Image:
    width, height, dpi = _paper_pixels(settings, dpi=140 if dpi is None else dpi)
    margin = int(dpi * 0.7)
    font = _font(max(12, int(dpi * 11 / 72)))
    small = _font(max(10, int(dpi * 9 / 72)))
    line_height = int(_font_size(font) * 1.4)
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    y = margin
    for line in lines:
        draw.text((margin, y), line, font=font, fill=(31, 41, 51))
        y += line_height
    footer = f"{name}   ·   {index + 1} of {total}"
    draw.text((margin, height - int(dpi * 0.45)), footer, font=small, fill=(120, 130, 140))
    return image


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        if paragraph == "":
            lines.append("")
            continue
        current = ""
        for word in paragraph.split(" "):
            trial = word if not current else f"{current} {word}"
            if draw.textlength(trial, font=font) <= max_width:
                current = trial
                continue
            if current:
                lines.append(current)
            if draw.textlength(word, font=font) <= max_width:
                current = word
                continue
            chunk = ""
            for char in word:
                if draw.textlength(chunk + char, font=font) <= max_width:
                    chunk += char
                else:
                    if chunk:
                        lines.append(chunk)
                    chunk = char
            current = chunk
        if current:
            lines.append(current)
    return lines or [""]


def _font_size(font: ImageFont.ImageFont) -> int:
    return int(getattr(font, "size", 12) or 12)


def _font(size: int) -> ImageFont.ImageFont:
    for path in (r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf"):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _draw_marks(draw: ImageDraw.ImageDraw, width: int, height: int, inset: int) -> None:
    tick = max(8, inset // 2)
    for x, y in ((inset, inset), (width - inset, inset), (inset, height - inset), (width - inset, height - inset)):
        draw.line((x - tick, y, x + tick, y), fill=(31, 41, 51), width=2)
        draw.line((x, y - tick, x, y + tick), fill=(31, 41, 51), width=2)


def _duplex_label(value: str) -> str:
    return {
        "simplex": "one side",
        "long": "both sides, long edge",
        "short": "both sides, short edge",
    }.get(value, value)

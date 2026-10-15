"""Nested print settings defaults and validation."""

from __future__ import annotations

import copy

SCALES = {"fit", "fill", "actual", "percent"}
PARITIES = {"all", "odd", "even"}
ALIGNS_H = {"left", "center", "right"}
ALIGNS_V = {"top", "middle", "bottom"}
NUP_VALUES = {1, 2, 4, 6, 9, 16}
NUP_ORDERS = {"rowsright", "rowsleft", "colsdown", "colsup"}
ROTATES = {0, 90, 180, 270}
REPORT_FORMATS = {"text", "html"}
BOOKLET_BINDINGS = {"left", "right"}

DEFAULT_WATERMARK = {
    "text": "",
    "font_size": 0,
    "angle": 45,
    "intensity": 15,
    "outline": False,
    "behind": False,
    "position_h": "center",
    "position_v": "middle",
    "offset_x": 0,
    "offset_y": 0,
    "page_range": "",
    "image": "",
    "image_size": 40,
}

DEFAULT_STAMPS = {
    "header_left": "",
    "header_center": "",
    "header_right": "",
    "footer_left": "",
    "footer_center": "",
    "footer_right": "",
    "font_size": 8,
}

DEFAULT_TEXT = {
    "font": "",
    "size": 9,
    "line_spacing": 100,
    "code_page": 0,
}

PAGE_OPTION_DEFAULTS = {
    "scale": "fit",
    "scale_percent": 100,
    "margin_left": 0,
    "margin_top": 0,
    "margin_right": 0,
    "margin_bottom": 0,
    "horizontal_align": "center",
    "vertical_align": "middle",
    "offset_x": 0,
    "offset_y": 0,
    "parity": "all",
    "reverse_order": False,
    "skip_blank": False,
    "print_as_image": False,
    "image_dpi": 300,
    "rotate": 0,
    "n_up": 1,
    "n_up_border": False,
    "n_up_order": "rowsright",
    "booklet": False,
    "booklet_binding": "left",
    "crop_marks": False,
    "cover_page": False,
    "separator_pages": False,
    "placeholder": False,
    "folder_cover_page": False,
    "end_cover_page": False,
    "cover_template": "",
    "folder_cover_template": "",
    "end_cover_template": "",
    "print_report": False,
    "report_file": False,
    "report_format": "text",
    "watermark": copy.deepcopy(DEFAULT_WATERMARK),
    "stamps": copy.deepcopy(DEFAULT_STAMPS),
    "text": copy.deepcopy(DEFAULT_TEXT),
}

# camelCase aliases used by saved settings and the UI
OPTION_ALIASES = {
    "scalePercent": "scale_percent",
    "marginLeft": "margin_left",
    "marginTop": "margin_top",
    "marginRight": "margin_right",
    "marginBottom": "margin_bottom",
    "horizontalAlign": "horizontal_align",
    "verticalAlign": "vertical_align",
    "offsetX": "offset_x",
    "offsetY": "offset_y",
    "reverseOrder": "reverse_order",
    "skipBlank": "skip_blank",
    "printAsImage": "print_as_image",
    "imageDpi": "image_dpi",
    "nUp": "n_up",
    "nUpBorder": "n_up_border",
    "nUpOrder": "n_up_order",
    "bookletBinding": "booklet_binding",
    "cropMarks": "crop_marks",
    "coverPage": "cover_page",
    "separatorPages": "separator_pages",
    "folderCoverPage": "folder_cover_page",
    "endCoverPage": "end_cover_page",
    "coverTemplate": "cover_template",
    "folderCoverTemplate": "folder_cover_template",
    "endCoverTemplate": "end_cover_template",
    "printReport": "print_report",
    "reportFile": "report_file",
    "reportFormat": "report_format",
}


def merge_option_defaults(settings: dict) -> dict:
    """Ensure nested option keys exist on a settings dict."""
    out = settings
    for key, value in PAGE_OPTION_DEFAULTS.items():
        if key not in out:
            out[key] = copy.deepcopy(value)
        elif key in {"watermark", "stamps", "text"} and isinstance(out[key], dict):
            base = copy.deepcopy(value)
            base.update(out[key])
            out[key] = base
    return out


def apply_option_setting(updated: dict, key: str, value) -> bool:
    """Apply one nested option. Returns True if handled."""
    if key in OPTION_ALIASES:
        key = OPTION_ALIASES[key]
    if key == "scale":
        scale = str(value or "fit").strip().lower()
        if scale not in SCALES:
            raise ValueError("Choose Fit, Fill, Actual, or Percent")
        updated["scale"] = scale
        return True
    if key == "scale_percent":
        pct = int(value)
        if not 1 <= pct <= 400:
            raise ValueError("Scale percent must be from 1 to 400")
        updated["scale_percent"] = pct
        return True
    if key in {"margin_left", "margin_top", "margin_right", "margin_bottom", "offset_x", "offset_y"}:
        size = float(value)
        if not -500 <= size <= 500:
            raise ValueError("Margin/offset is out of range")
        updated[key] = int(size) if size == int(size) else round(size, 1)
        return True
    if key == "horizontal_align":
        align = str(value or "center").strip().lower()
        if align not in ALIGNS_H:
            raise ValueError("Choose left, center, or right")
        updated["horizontal_align"] = align
        return True
    if key == "vertical_align":
        align = str(value or "middle").strip().lower()
        if align not in ALIGNS_V:
            raise ValueError("Choose top, middle, or bottom")
        updated["vertical_align"] = align
        return True
    if key == "parity":
        parity = str(value or "all").strip().lower()
        if parity not in PARITIES:
            raise ValueError("Choose All, Odd, or Even pages")
        updated["parity"] = parity
        return True
    if key in {
        "reverse_order",
        "skip_blank",
        "print_as_image",
        "n_up_border",
        "booklet",
        "crop_marks",
        "cover_page",
        "separator_pages",
        "placeholder",
        "folder_cover_page",
        "end_cover_page",
        "print_report",
        "report_file",
    }:
        updated[key] = bool(value)
        return True
    if key == "image_dpi":
        dpi = int(value)
        if not 72 <= dpi <= 1200:
            raise ValueError("Image DPI must be from 72 to 1200")
        updated["image_dpi"] = dpi
        return True
    if key == "rotate":
        rotate = int(value)
        if rotate not in ROTATES:
            raise ValueError("Rotate must be 0, 90, 180, or 270")
        updated["rotate"] = rotate
        return True
    if key == "n_up":
        n_up = int(value)
        if n_up not in NUP_VALUES:
            raise ValueError("N-up must be 1, 2, 4, 6, 9, or 16")
        updated["n_up"] = n_up
        return True
    if key == "n_up_order":
        order = str(value or "rowsright").strip().lower().replace("_", "")
        order = {"rowsright": "rowsright", "rowsleft": "rowsleft", "colsdown": "colsdown", "colsup": "colsup"}.get(
            order, order
        )
        if order not in NUP_ORDERS:
            raise ValueError("Choose an n-up order")
        updated["n_up_order"] = order
        return True
    if key == "booklet_binding":
        binding = str(value or "left").strip().lower()
        if binding not in BOOKLET_BINDINGS:
            raise ValueError("Choose left or right booklet binding")
        updated["booklet_binding"] = binding
        return True
    if key in {"cover_template", "folder_cover_template", "end_cover_template"}:
        path = str(value or "").strip()
        if len(path) > 400:
            raise ValueError("That template path is too long")
        updated[key] = path
        return True
    if key == "report_format":
        fmt = str(value or "text").strip().lower()
        if fmt not in REPORT_FORMATS:
            raise ValueError("Choose Text or Html for the report")
        updated["report_format"] = fmt
        return True
    if key == "watermark":
        updated["watermark"] = _merge_watermark(updated.get("watermark") or DEFAULT_WATERMARK, value)
        return True
    if key == "stamps":
        updated["stamps"] = _merge_stamps(updated.get("stamps") or DEFAULT_STAMPS, value)
        return True
    if key == "text":
        updated["text"] = _merge_text(updated.get("text") or DEFAULT_TEXT, value)
        return True
    return False


def _merge_watermark(current: dict, incoming) -> dict:
    if not isinstance(incoming, dict):
        raise ValueError("Watermark settings were not understood")
    out = copy.deepcopy(current)
    aliases = {
        "fontSize": "font_size",
        "positionH": "position_h",
        "positionV": "position_v",
        "offsetX": "offset_x",
        "offsetY": "offset_y",
        "pageRange": "page_range",
        "imageSize": "image_size",
    }
    for raw, value in incoming.items():
        key = aliases.get(raw, raw)
        if key == "text":
            out["text"] = str(value or "")[:200]
        elif key == "font_size":
            out["font_size"] = max(0, min(200, int(value or 0)))
        elif key == "angle":
            out["angle"] = int(value) % 360
        elif key == "intensity":
            out["intensity"] = max(1, min(100, int(value or 15)))
        elif key in {"outline", "behind"}:
            out[key] = bool(value)
        elif key == "position_h":
            pos = str(value or "center").strip().lower()
            if pos not in ALIGNS_H:
                raise ValueError("Watermark horizontal position is invalid")
            out["position_h"] = pos
        elif key == "position_v":
            pos = str(value or "middle").strip().lower()
            if pos not in ALIGNS_V:
                raise ValueError("Watermark vertical position is invalid")
            out["position_v"] = pos
        elif key in {"offset_x", "offset_y"}:
            out[key] = float(value or 0)
        elif key == "page_range":
            out["page_range"] = str(value or "")[:80]
        elif key == "image":
            out["image"] = str(value or "")[:400]
        elif key == "image_size":
            out["image_size"] = max(1, min(100, int(value or 40)))
    return out


def _merge_stamps(current: dict, incoming) -> dict:
    if not isinstance(incoming, dict):
        raise ValueError("Stamp settings were not understood")
    out = copy.deepcopy(current)
    aliases = {
        "headerLeft": "header_left",
        "headerCenter": "header_center",
        "headerRight": "header_right",
        "footerLeft": "footer_left",
        "footerCenter": "footer_center",
        "footerRight": "footer_right",
        "fontSize": "font_size",
    }
    for raw, value in incoming.items():
        key = aliases.get(raw, raw)
        if key in {
            "header_left",
            "header_center",
            "header_right",
            "footer_left",
            "footer_center",
            "footer_right",
        }:
            out[key] = str(value or "")[:120]
        elif key == "font_size":
            out["font_size"] = max(4, min(72, int(value or 8)))
    return out


def _merge_text(current: dict, incoming) -> dict:
    if not isinstance(incoming, dict):
        raise ValueError("Text settings were not understood")
    out = copy.deepcopy(current)
    aliases = {"lineSpacing": "line_spacing", "codePage": "code_page"}
    for raw, value in incoming.items():
        key = aliases.get(raw, raw)
        if key == "font":
            out["font"] = str(value or "")[:80]
        elif key == "size":
            out["size"] = max(4, min(72, int(value or 9)))
        elif key == "line_spacing":
            out["line_spacing"] = max(50, min(300, int(value or 100)))
        elif key == "code_page":
            out["code_page"] = max(0, int(value or 0))
    return out


def public_option_settings(settings: dict) -> dict:
    wm = settings.get("watermark") or DEFAULT_WATERMARK
    stamps = settings.get("stamps") or DEFAULT_STAMPS
    text = settings.get("text") or DEFAULT_TEXT
    return {
        "scale": settings.get("scale", "fit"),
        "scalePercent": settings.get("scale_percent", 100),
        "marginLeft": settings.get("margin_left", 0),
        "marginTop": settings.get("margin_top", 0),
        "marginRight": settings.get("margin_right", 0),
        "marginBottom": settings.get("margin_bottom", 0),
        "horizontalAlign": settings.get("horizontal_align", "center"),
        "verticalAlign": settings.get("vertical_align", "middle"),
        "offsetX": settings.get("offset_x", 0),
        "offsetY": settings.get("offset_y", 0),
        "parity": settings.get("parity", "all"),
        "reverseOrder": settings.get("reverse_order", False),
        "skipBlank": settings.get("skip_blank", False),
        "printAsImage": settings.get("print_as_image", False),
        "imageDpi": settings.get("image_dpi", 300),
        "rotate": settings.get("rotate", 0),
        "nUp": settings.get("n_up", 1),
        "nUpBorder": settings.get("n_up_border", False),
        "nUpOrder": settings.get("n_up_order", "rowsright"),
        "booklet": settings.get("booklet", False),
        "bookletBinding": settings.get("booklet_binding", "left"),
        "cropMarks": settings.get("crop_marks", False),
        "coverPage": settings.get("cover_page", False),
        "separatorPages": settings.get("separator_pages", False),
        "placeholder": settings.get("placeholder", False),
        "folderCoverPage": settings.get("folder_cover_page", False),
        "endCoverPage": settings.get("end_cover_page", False),
        "coverTemplate": settings.get("cover_template", ""),
        "folderCoverTemplate": settings.get("folder_cover_template", ""),
        "endCoverTemplate": settings.get("end_cover_template", ""),
        "printReport": settings.get("print_report", False),
        "reportFile": settings.get("report_file", False),
        "reportFormat": settings.get("report_format", "text"),
        "watermark": {
            "text": wm.get("text", ""),
            "fontSize": wm.get("font_size", 0),
            "angle": wm.get("angle", 45),
            "intensity": wm.get("intensity", 15),
            "outline": wm.get("outline", False),
            "behind": wm.get("behind", False),
            "positionH": wm.get("position_h", "center"),
            "positionV": wm.get("position_v", "middle"),
            "offsetX": wm.get("offset_x", 0),
            "offsetY": wm.get("offset_y", 0),
            "pageRange": wm.get("page_range", ""),
            "image": wm.get("image", ""),
            "imageSize": wm.get("image_size", 40),
        },
        "stamps": {
            "headerLeft": stamps.get("header_left", ""),
            "headerCenter": stamps.get("header_center", ""),
            "headerRight": stamps.get("header_right", ""),
            "footerLeft": stamps.get("footer_left", ""),
            "footerCenter": stamps.get("footer_center", ""),
            "footerRight": stamps.get("footer_right", ""),
            "fontSize": stamps.get("font_size", 8),
        },
        "text": {
            "font": text.get("font", ""),
            "size": text.get("size", 9),
            "lineSpacing": text.get("line_spacing", 100),
            "codePage": text.get("code_page", 0),
        },
    }


def preset_option_block(settings: dict) -> dict:
    """Flat preset keys for a settings export."""
    pub = public_option_settings(settings)
    return {
        "nUp": pub["nUp"],
        "nUpBorder": pub["nUpBorder"],
        "nUpOrder": {"rowsright": "RowsRight", "rowsleft": "RowsLeft", "colsdown": "ColsDown", "colsup": "ColsUp"}.get(
            pub["nUpOrder"], "RowsRight"
        ),
        "customPaperWidth": settings.get("custom_paper_width", 0),
        "customPaperHeight": settings.get("custom_paper_height", 0),
        "documentOnFrontSide": settings.get("document_on_front", True),
        "scale": {"fit": "Fit", "fill": "Fill", "actual": "Actual", "percent": "Percent"}.get(pub["scale"], "Fit"),
        "scalePercent": pub["scalePercent"],
        "marginLeft": pub["marginLeft"],
        "marginTop": pub["marginTop"],
        "marginRight": pub["marginRight"],
        "marginBottom": pub["marginBottom"],
        "horizontalAlign": pub["horizontalAlign"].title(),
        "verticalAlign": pub["verticalAlign"].title(),
        "offsetX": pub["offsetX"],
        "offsetY": pub["offsetY"],
        "parity": pub["parity"].title(),
        "reverseOrder": pub["reverseOrder"],
        "skipBlank": pub["skipBlank"],
        "printAsImage": pub["printAsImage"],
        "imageDpi": pub["imageDpi"],
        "rotate": pub["rotate"],
        "booklet": pub["booklet"],
        "bookletBinding": pub["bookletBinding"].title(),
        "cropMarks": pub["cropMarks"],
        "coverPage": pub["coverPage"],
        "separatorPages": pub["separatorPages"],
        "placeholder": pub["placeholder"],
        "folderCoverPage": pub["folderCoverPage"],
        "endCoverPage": pub["endCoverPage"],
        "coverTemplate": pub["coverTemplate"],
        "folderCoverTemplate": pub["folderCoverTemplate"],
        "endCoverTemplate": pub["endCoverTemplate"],
        "watermark": pub["watermark"],
        "stamps": pub["stamps"],
        "text": pub["text"],
        "printReport": pub["printReport"],
        "reportFile": pub["reportFile"],
        "reportFormat": pub["reportFormat"].title(),
    }

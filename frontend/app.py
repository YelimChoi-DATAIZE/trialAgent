"""Trial AX - Clinical Agent (PyQt6 UI).

Two screens:
  1) Launcher  - describe a task, pick agent tools.
  2) Workspace - results / activity / audit + agent chat (shown after run).

Run inside the project venv:
    ./venv/bin/python run.py          # starts the backend + this UI together

Or start the two processes manually (two terminals):
    ./venv/bin/python backend/agent_server.py
    ./venv/bin/python frontend/app.py
"""

from __future__ import annotations

import json
import logging
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime

from PyQt6.QtCore import QPoint, QRect, QRectF, QSize, Qt, QThread, QTimer, pyqtSignal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("trial_agent.ui")
from PyQt6.QtGui import QColor, QCursor, QFont, QLinearGradient, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------
BG_TOP = "#0a0e15"
BG_BOTTOM = "#0c111a"
PANEL = "#10151e"
CARD = "#121823"
CARD_HOVER = "#161d2a"
BUBBLE = "#141b26"
BORDER = "#1f2733"
BORDER_SOFT = "#1a212c"
TEAL = "#2dd4bf"
TEAL_DIM = "#14b8a6"
AMBER = "#fbbf24"
RED = "#f87171"
TEXT = "#e6edf3"
TEXT_MUTED = "#8a94a6"
TEXT_FAINT = "#5b6577"

EXAMPLE_PROMPT = "\ube44\uc18c\uc138\ud3ec\ud3d0\uc554 \ud658\uc790\uc5d0\uac8c \ub9de\ub294 \ud6c4\ubcf4 \uc784\uc0c1\uc2dc\ud5d8\uc744 \uac80\uc0c9\ud558\uace0 \uc801\uaca9\uc131\uc744 \ub9e4\uce6d\ud574\uc918"

GREETING = (
    "\uc548\ub155\ud558\uc138\uc694. \uc784\uc0c1 \uc6b4\uc601 \ubc18\ubcf5 \uc5c5\ubb34\ub97c \ub3c4\uc640\ub4dc\ub9bd\ub2c8\ub2e4. "
    "\ucc98\ub9ac\ud560 \ub0b4\uc6a9\uc744 \uc801\uace0 \uc544\ub798\uc5d0\uc11c \ud544\uc694\ud55c \uc791\uc5c5\uc744 \uc120\ud0dd\ud574 \uc8fc\uc138\uc694. "
    "\uaddc\uc81c \uc601\ud5a5\uc774 \uc788\ub294 \uacb0\uacfc\ub294 \ud56d\uc0c1 \uc0ac\ub78c \uac80\ud1a0 \ud6c4 \ubc18\uc601\ub429\ub2c8\ub2e4."
)


# ---------------------------------------------------------------------------
# Flow layout (wraps tool chips)
# ---------------------------------------------------------------------------
class FlowLayout(QLayout):
    def __init__(self, parent=None, spacing=8):
        super().__init__(parent)
        self._items: list = []
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(spacing)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        return size

    def _do_layout(self, rect, test):
        x, y, line_h = rect.x(), rect.y(), 0
        spacing = self.spacing()
        for item in self._items:
            w = item.sizeHint().width()
            h = item.sizeHint().height()
            if x + w > rect.right() and line_h > 0:
                x = rect.x()
                y += line_h + spacing
                line_h = 0
            if not test:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
            x += w + spacing
            line_h = max(line_h, h)
        return y + line_h - rect.y()


# ---------------------------------------------------------------------------
# Small reusable widgets
# ---------------------------------------------------------------------------
class IconBadge(QFrame):
    def __init__(self, glyph: str, size: int = 30, radius: int = 9, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setStyleSheet(
            f"QFrame {{ background: transparent; border: none; border-radius: {radius}px; }}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(glyph)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(
            f"color: {TEAL}; font-size: {int(size * 0.45)}px; background: transparent; border: none;"
        )
        lay.addWidget(lbl)


# ---------------------------------------------------------------------------
# Title bar (shared)
# ---------------------------------------------------------------------------
_FRONTEND_DIR = os.path.dirname(os.path.abspath(__file__))
LOGO_PATH = os.path.join(_FRONTEND_DIR, "logo-filled.svg")


def make_logo(size: int = 26) -> QLabel:
    """Render the company SVG logo into a crisp QLabel."""
    lbl = QLabel()
    lbl.setFixedSize(size, size)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    renderer = QSvgRenderer(LOGO_PATH)
    if renderer.isValid():
        hi = size * 4  # render large, then scale down for crisp edges
        pm = QPixmap(hi, hi)
        pm.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pm)
        renderer.render(painter, QRectF(0, 0, hi, hi))
        painter.end()
        lbl.setPixmap(pm.scaled(
            size, size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ))
    return lbl


class TitleBar(QFrame):
    def __init__(self, window: "MainWindow", show_home: bool = False):
        super().__init__()
        self._win = window
        self._drag_pos: QPoint | None = None
        self.setFixedHeight(48)
        self.setStyleSheet(
            "QFrame { background: transparent; border-bottom: 1px solid rgba(255,255,255,0.20); }"
        )

        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(10)

        logo = make_logo(20)
        logo.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        lay.addWidget(logo)
        brand = QLabel("DATAIZEAI - Trial Agent")
        brand.setStyleSheet(f"color: {TEXT}; font-size: 14px; font-weight: 800; background: transparent;")
        lay.addWidget(brand)

        lay.addStretch(1)

        if show_home:
            home_btn = QPushButton("\u2302")
            home_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            home_btn.clicked.connect(window.go_home)
            home_btn.setFixedSize(30, 26)
            home_btn.setStyleSheet(
                f"QPushButton {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 8px;"
                f" color: {TEXT_MUTED}; font-size: 13px; }}"
                f"QPushButton:hover {{ color: {TEXT}; border: 1px solid {TEAL_DIM}; }}"
            )
            lay.addWidget(home_btn)
            lay.addSpacing(8)

        for glyph, slot in (("\u2013", window.showMinimized), ("\u25a1", self._toggle_max), ("\u2715", window.close)):
            btn = QPushButton(glyph)
            btn.setFixedSize(28, 24)
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn.clicked.connect(slot)
            btn.setStyleSheet(
                f"QPushButton {{ background: transparent; border: none; color: {TEXT_FAINT}; font-size: 13px; }}"
                f"QPushButton:hover {{ color: {TEXT}; }}"
            )
            lay.addWidget(btn)

    def _toggle_max(self):
        self._win.showNormal() if self._win.isMaximized() else self._win.showMaximized()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self._win.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._win.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None


# ===========================================================================
# LAUNCHER SCREEN
# ===========================================================================
PROTOCOL_LOGO = os.path.join(_FRONTEND_DIR, "clinicalprotocol.png")
TRIALGPT_LOGO = os.path.join(_FRONTEND_DIR, "trial_gpt_logo.png")
CTG_LOGO = os.path.join(_FRONTEND_DIR, "ctg_logo.png")

# light card palette
CARD_L = "#eef1f5"
CARD_L_HOVER = "#e4e9f0"
CARD_L_BORDER = "#d3dae3"
CARD_TITLE = "#1e293b"
CARD_SUB = "#64748b"
CARD_STATUS = "#94a3b8"


def make_image_logo(path: str, height: int = 28) -> QLabel:
    """Load a raster (PNG) logo into a crisp, transparent QLabel."""
    lbl = QLabel()
    lbl.setFixedHeight(height)
    lbl.setStyleSheet("background: transparent;")
    pm = QPixmap(path)
    if not pm.isNull():
        dpr = 2
        scaled = pm.scaledToHeight(height * dpr, Qt.TransformationMode.SmoothTransformation)
        scaled.setDevicePixelRatio(dpr)
        lbl.setPixmap(scaled)
    return lbl


class ToolCard(QFrame):
    def __init__(self, logo_path: str, title: str, subtitle: str, key: str, on_toggle, parent=None):
        super().__init__(parent)
        self.key = key
        self._on_toggle = on_toggle
        self.selected = False
        self.setObjectName("toolCard")
        self.setMinimumHeight(104)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._apply()

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(0)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.addWidget(make_image_logo(logo_path, 20), alignment=Qt.AlignmentFlag.AlignTop)
        top.addStretch(1)
        self.radio = QLabel()
        self.radio.setFixedSize(15, 15)
        self._set_radio(False)
        top.addWidget(self.radio, alignment=Qt.AlignmentFlag.AlignTop)
        root.addLayout(top)

        root.addSpacing(9)
        t = QLabel(title)
        t.setWordWrap(True)
        t.setStyleSheet(f"color: {CARD_TITLE}; font-size: 13px; font-weight: 800; background: transparent;")
        root.addWidget(t)
        root.addSpacing(3)
        s = QLabel(subtitle)
        s.setWordWrap(True)
        s.setStyleSheet(f"color: {CARD_SUB}; font-size: 10px; background: transparent;")
        root.addWidget(s)
        root.addStretch(1)

    def _set_radio(self, on: bool):
        color = TEAL_DIM if on else "#c2ccd8"
        fill = "rgba(45,212,191,0.25)" if on else "transparent"
        self.radio.setStyleSheet(f"background: {fill}; border: 1.5px solid {color}; border-radius: 8px;")

    def _apply(self):
        border = TEAL_DIM if self.selected else CARD_L_BORDER
        bg = "#e7ecf2" if self.selected else CARD_L
        self.setStyleSheet(
            f"QFrame#toolCard {{ background: {bg}; border: 1px solid {border}; border-radius: 0px; }}"
            f"QFrame#toolCard:hover {{ background: {CARD_L_HOVER};"
            f" border: 1px solid {TEAL_DIM if self.selected else '#b9c3d0'}; }}"
        )

    def mousePressEvent(self, event):
        self.selected = not self.selected
        self._apply()
        self._set_radio(self.selected)
        if self._on_toggle:
            self._on_toggle()
        super().mousePressEvent(event)


class Chip(QPushButton):
    def __init__(self, text: str, parent=None):
        super().__init__("\u2727  " + text.replace("&", "&&"), parent)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setStyleSheet(
            f"QPushButton {{ background: rgba(255,255,255,0.02); border: 1px solid {BORDER};"
            f" border-radius: 16px; color: {TEXT_MUTED}; padding: 7px 16px; font-size: 12px; }}"
            f"QPushButton:hover {{ background: rgba(45,212,191,0.06); border: 1px solid {TEAL_DIM}; color: {TEXT}; }}"
        )


LAUNCHER_TOOLS = [
    # Clinical Protocol Review
    (PROTOCOL_LOGO, "Protocol Drafting", "\uc801\uc751\uc99d\u00b7\ubaa9\uc801 \uae30\ubc18 \uc784\uc0c1 \ud504\ub85c\ud1a0\ucf5c \ucd08\uc548 \uc0dd\uc131", "Protocol Generator"),
    (PROTOCOL_LOGO, "Scientific & PI Review", "\uc5f0\uad6c \uc124\uacc4\u00b7endpoint\u00b7\uc548\uc804\uc131\u00b7\uc724\ub9ac\uc131 \uac80\ud1a0", "PI"),
    (PROTOCOL_LOGO, "Site Feasibility Review", "\uc2e4\uc81c \ubcd1\uc6d0\uc5d0\uc11c \uc218\ud589 \uac00\ub2a5\ud55c\uc9c0 \uc6b4\uc601 \uad00\uc810 \uac80\ud1a0", "Site Physician"),
    (PROTOCOL_LOGO, "Regulatory Review", "\uaddc\uc81c\uae30\uad00 \uc81c\ucd9c \uad00\uc810\uc758 \ucd5c\uc885 \ub9ac\uc2a4\ud06c \uac80\ud1a0", "Health Authority"),
    # TrialGPT
    (TRIALGPT_LOGO, "TrialGPT Retrieval", "\ud0a4\uc6cc\ub4dc \uc0dd\uc131\u00b7\ud558\uc774\ube0c\ub9ac\ub4dc \uac80\uc0c9\uc73c\ub85c \ud6c4\ubcf4 \uc2dc\ud5d8 \uc120\ubcc4", "TrialGPT Retrieval"),
    (TRIALGPT_LOGO, "TrialGPT Matching", "\uae30\uc900\ubcc4 \ud658\uc790 \uc801\uaca9\uc131 \ud310\uc815 \ubc0f \uadfc\uac70 \uc124\uba85 \uc0dd\uc131", "TrialGPT Matching"),
    (TRIALGPT_LOGO, "TrialGPT Ranking", "\uae30\uc900 \uc810\uc218\ub97c \uc885\ud569\ud574 \uc2dc\ud5d8 \ub2e8\uc704 \uc21c\uc704 \uc0b0\uc815", "TrialGPT Ranking"),
    # ClinicalTrials.gov
    (CTG_LOGO, "CTG Retrieval", "\uacf5\uac1c \uc784\uc0c1\uc2dc\ud5d8(ClinicalTrials.gov) \ub4f1\ub85d \uc815\ubcf4 \uc870\ud68c\u00b7\uc218\uc9d1", "CTG Retrieval"),
]


SAMPLE_PROMPT_PATH = os.path.join(_FRONTEND_DIR, "sample_prompt.json")


def load_sample_prompts() -> list[dict]:
    """Load example prompts grouped by topic from sample_prompt.json.

    Returns a list of ``{"topic": str, "items": list[str]}`` entries. On any
    error (missing/invalid file) returns an empty list so the launcher falls
    back to its built-in example chips.
    """
    try:
        with open(SAMPLE_PROMPT_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:  # noqa: BLE001
        log.warning("sample_prompt.json load failed: %s", exc)
        return []
    out = []
    for entry in data.get("prompts", []):
        topic = (entry.get("topic") or "").strip()
        items = [str(i).strip() for i in entry.get("items", []) if str(i).strip()]
        if topic and items:
            out.append({"topic": topic, "items": items})
    return out


PAGE_BG = (
    f"qlineargradient(x1:0,y1:0,x2:0.3,y2:1, stop:0 {BG_TOP}, stop:1 {BG_BOTTOM})"
)

BACKGROUND_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "background.png")


class LauncherPage(QWidget):
    def __init__(self, window: "MainWindow"):
        super().__init__()
        self._win = window
        self.cards: list[ToolCard] = []
        self.setObjectName("launcherPage")
        self._bg = QPixmap(BACKGROUND_PATH)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(TitleBar(window))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            f"QScrollArea {{ background: transparent; border: none; }}"
            f"QScrollBar:vertical {{ background: transparent; width: 9px; margin: 4px; }}"
            f"QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 4px; min-height: 40px; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}"
        )
        outer.addWidget(scroll, 1)

        footer = QWidget()
        footer.setStyleSheet("background: transparent;")
        fcol = QVBoxLayout(footer)
        fcol.setContentsMargins(0, 8, 0, 14)
        fcol.setSpacing(8)

        # OPENAI_API_KEY input — applied to each run via MainWindow.api_key.
        key_row = QHBoxLayout()
        key_row.setContentsMargins(0, 0, 0, 0)
        key_row.setSpacing(0)
        key_row.addStretch(1)
        self.key_input = QLineEdit()
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.setPlaceholderText("OPENAI_API_KEY (sk-...)")
        self.key_input.setText(self._win.api_key)
        self.key_input.setFixedWidth(420)
        self.key_input.setStyleSheet(
            "QLineEdit { background: rgba(255,255,255,0.06);"
            f" color: {TEXT}; border: 1px solid {BORDER}; border-radius: 9px;"
            " padding: 8px 12px; font-size: 12px; }"
            f"QLineEdit:focus {{ border: 1px solid {TEAL_DIM}; }}"
        )
        self.key_input.textChanged.connect(self._on_api_key_changed)
        key_row.addWidget(self.key_input)
        key_row.addStretch(1)
        fcol.addLayout(key_row)

        fl = QHBoxLayout()
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(7)
        fl.addStretch(1)
        fl.addWidget(make_logo(16))
        contact = QLabel(
            '<a href="https://dataize.io/contact-us"'
            ' style="color:#cdd9e6; text-decoration:underline;">Contact us</a>'
        )
        contact.setTextFormat(Qt.TextFormat.RichText)
        contact.setOpenExternalLinks(True)
        contact.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        contact.setStyleSheet(
            "color:#cdd9e6; font-size:13px; font-weight:700; background: transparent;"
        )
        fl.addWidget(contact)

        sep = QLabel("\u00b7")
        sep.setStyleSheet("color:#6b7685; font-size:13px; background: transparent;")
        fl.addWidget(sep)

        api_key_link = QLabel(
            '<a href="https://dataize.io/konect-api-key"'
            ' style="color:#cdd9e6; text-decoration:underline;">Get API key</a>'
        )
        api_key_link.setTextFormat(Qt.TextFormat.RichText)
        api_key_link.setOpenExternalLinks(True)
        api_key_link.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        api_key_link.setStyleSheet(
            "color:#cdd9e6; font-size:13px; font-weight:700; background: transparent;"
        )
        fl.addWidget(api_key_link)
        fl.addStretch(1)
        fcol.addLayout(fl)
        outer.addWidget(footer)

        body = QWidget()
        body.setStyleSheet("background: transparent;")
        scroll.setWidget(body)

        # center a fixed max-width column both horizontally and vertically
        outer_body = QVBoxLayout(body)
        outer_body.setContentsMargins(40, 28, 40, 28)
        outer_body.setSpacing(0)
        outer_body.addStretch(1)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addStretch(1)
        col_widget = QWidget()
        col_widget.setMaximumWidth(1040)
        col_widget.setStyleSheet("background: transparent;")
        content = QVBoxLayout(col_widget)
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)
        row.addWidget(col_widget, 1)
        row.addStretch(1)
        outer_body.addLayout(row)
        outer_body.addStretch(1)

        self._build_hero(content)
        self._build_prompt(content)
        self._build_chips(content)
        self._build_tools(content)

    def paintEvent(self, event):
        painter = QPainter(self)
        rect = self.rect()
        if not self._bg.isNull():
            # scale the photo to cover the whole page (keep aspect ratio)
            scaled = self._bg.scaled(
                rect.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (scaled.width() - rect.width()) // 2
            y = (scaled.height() - rect.height()) // 2
            painter.drawPixmap(rect, scaled, QRect(x, y, rect.width(), rect.height()))
        else:
            painter.fillRect(rect, QColor(BG_BOTTOM))

        # dark overlay so the UI stays readable on top of the photo
        overlay = QLinearGradient(0, 0, rect.width() * 0.4, rect.height())
        overlay.setColorAt(0.0, QColor(8, 12, 19, 120))
        overlay.setColorAt(1.0, QColor(10, 14, 21, 165))
        painter.fillRect(rect, overlay)
        super().paintEvent(event)

    def _build_hero(self, layout):
        eyebrow = QLabel("\u25cf  AGENT WORKSPACE")
        eyebrow.setStyleSheet(
            f"color: {TEAL}; font-size: 11px; font-weight: 800; letter-spacing: 1.5px; background: transparent;"
        )
        layout.addWidget(eyebrow)
        layout.addSpacing(14)
        title = QLabel("\ubb34\uc5c7\uc744 \ucc98\ub9ac\ud574 \ub4dc\ub9b4\uae4c\uc694?")
        title.setStyleSheet(f"color: {TEXT}; font-size: 32px; font-weight: 800; background: transparent;")
        layout.addWidget(title)
        layout.addSpacing(22)

    def _build_prompt(self, layout):
        card = QFrame()
        card.setObjectName("promptCard")
        card.setStyleSheet(
            "QFrame#promptCard { background: #dde3ea;"
            " border: 1px solid #c2ccd8; border-radius: 16px; }"
        )
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(40)
        shadow.setColor(QColor(0, 0, 0, 120))
        shadow.setOffset(0, 12)
        card.setGraphicsEffect(shadow)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(22, 20, 22, 18)
        cl.setSpacing(0)

        self.prompt = QPlainTextEdit()
        self.prompt.setPlaceholderText(
            "\uc608: \ube44\uc18c\uc138\ud3ec\ud3d0\uc554 2\ucc28 \uce58\ub8cc \uc784\uc0c1\uc2dc\ud5d8 \ud504\ub85c\ud1a0\ucf5c \ucd08\uc548\uc744 \uc0dd\uc131\ud558\uace0, "
            "ICH-GCP\u00b7FDA \uaddc\uc81c \uc900\uc218\uc640 PI \uad00\uc810\uc758 \uacfc\ud559\uc801 \ud0c0\ub2f9\uc131\uc744 \ud568\uaed8 \uac80\ud1a0\ud574\uc918"
        )
        self.prompt.setFixedHeight(72)
        self.prompt.setFrameShape(QFrame.Shape.NoFrame)
        self.prompt.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.prompt.setStyleSheet(
            "QPlainTextEdit { background: transparent; border: none; color: #0f172a; font-size: 14px; }"
        )
        cl.addWidget(self.prompt)
        cl.addSpacing(10)

        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.setSpacing(10)
        self.sel_label = QLabel()
        self.sel_label.setStyleSheet("color: #64748b; font-size: 11px; background: transparent;")
        bottom.addWidget(self.sel_label)
        bottom.addStretch(1)

        run = QPushButton("\u25b6")
        run.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        run.setFixedSize(34, 34)
        run.clicked.connect(self._run)
        run.setStyleSheet(
            f"QPushButton {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {TEAL}, stop:1 #16b8a6);"
            f" color: #06251f; border: none; border-radius: 9px; font-size: 13px; font-weight: 800; padding-left: 2px; }}"
            f"QPushButton:hover {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #3ce0cc, stop:1 #1cc6b3); }}"
        )
        bottom.addWidget(run)
        cl.addLayout(bottom)
        layout.addWidget(card)
        layout.addSpacing(18)

    def _build_chips(self, layout):
        # Example prompts come from sample_prompt.json: each topic is a chip,
        # and clicking it opens a picker to choose one of the topic's examples.
        self._sample_prompts = load_sample_prompts()
        self._topic_items = {e["topic"]: e["items"] for e in self._sample_prompts}
        self._example_popup: QFrame | None = None

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        if self._sample_prompts:
            for entry in self._sample_prompts:
                topic = entry["topic"]
                chip = Chip(topic)
                chip.clicked.connect(
                    lambda _=False, t=topic, c=chip: self._open_examples(t, c))
                row.addWidget(chip)
        else:
            # Fallback to the built-in chips if the JSON is missing/invalid.
            for text in self.CHIP_PROMPTS:
                chip = Chip(text)
                chip.clicked.connect(lambda _=False, t=text: self._use_chip(t))
                row.addWidget(chip)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addSpacing(30)

    def _on_api_key_changed(self, text: str):
        self._win.api_key = text.strip()

    def _build_tools(self, layout):
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        title = QLabel("AI \uc791\uc5c5")
        title.setStyleSheet(f"color: {TEXT}; font-size: 14px; font-weight: 700; background: transparent;")
        hint = QLabel("\uc2e4\ud589\ud560 \uc791\uc5c5\uc744 \uc120\ud0dd\ud574 \uc8fc\uc138\uc694")
        hint.setStyleSheet(f"color: {TEXT_FAINT}; font-size: 12px; background: transparent;")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(hint)
        layout.addLayout(header)
        layout.addSpacing(16)

        grid = QGridLayout()
        grid.setSpacing(12)
        grid.setContentsMargins(0, 0, 0, 0)
        for i, (logo_path, t, s, key) in enumerate(LAUNCHER_TOOLS):
            card = ToolCard(logo_path, t, s, key, self._update_sel)
            self.cards.append(card)
            grid.addWidget(card, i // 4, i % 4)
        for c in range(4):
            grid.setColumnStretch(c, 1)
        layout.addLayout(grid)
        self._update_sel()

    # behaviour ------------------------------------------------------------
    def _selected_keys(self) -> list[str]:
        return [c.key for c in self.cards if c.selected]

    def _update_sel(self):
        n = len(self._selected_keys())
        self.sel_label.setText(f"selected {n}")

    CHIP_PROMPTS = {
        "\uc784\uc0c1 \ud504\ub85c\ud1a0\ucf5c \ucd08\uc548 \uc0dd\uc131":
            "\ube44\uc18c\uc138\ud3ec\ud3d0\uc554 2\ucc28 \uce58\ub8cc \uc784\uc0c1\uc2dc\ud5d8 \ud504\ub85c\ud1a0\ucf5c \ucd08\uc548\uc744 \uc801\uc751\uc99d\u00b7\ubaa9\uc801 \uae30\ubc18\uc73c\ub85c \uc0dd\uc131\ud574\uc918",
        "ICH-GCP\u00b7FDA \uaddc\uc81c \uc900\uc218 \uac80\ud1a0":
            "\uc791\uc131\ub41c \ud504\ub85c\ud1a0\ucf5c\uc744 ICH-GCP\u00b7FDA\u00b7EMA \uaddc\uc81c \uc900\uc218\uc640 \ub370\uc774\ud130 \ubb34\uacb0\uc131 \uad00\uc810\uc5d0\uc11c \uac80\ud1a0\ud574\uc918",
        "\ud658\uc790 \uc2dc\ud5d8 \uc801\uaca9\uc131 \ub9e4\uce6d & \uadfc\uac70":
            "\ud658\uc790 \uc694\uc57d\uc744 \uae30\uc900\ubcc4\ub85c \ud3c9\uac00\ud574 \uc784\uc0c1\uc2dc\ud5d8 \uc801\uaca9\uc131\uc744 \ud310\uc815\ud558\uace0 \uadfc\uac70\ub97c \uc124\uba85\ud574\uc918",
        "\ud6c4\ubcf4 \uc784\uc0c1\uc2dc\ud5d8 \uac80\uc0c9\u00b7\uc21c\uc704\ud654":
            "\ud658\uc790 \uc870\uac74\uc5d0 \ub9de\ub294 \ud6c4\ubcf4 \uc784\uc0c1\uc2dc\ud5d8\uc744 \uac80\uc0c9\ud558\uace0 \uae30\uc900 \uc810\uc218\ub97c \uc885\ud569\ud574 \uc21c\uc704\ub97c \uc0b0\uc815\ud574\uc918",
    }

    def _open_examples(self, topic: str, anchor: QWidget):
        """Open a picker popup listing the topic's example prompts."""
        items = self._topic_items.get(topic, [])
        if not items:
            return
        if self._example_popup is not None:
            self._example_popup.close()
            self._example_popup.deleteLater()
            self._example_popup = None

        popup = QFrame(self, Qt.WindowType.Popup)
        popup.setStyleSheet(
            f"QFrame {{ background: {CARD_L}; border: 1px solid {CARD_L_BORDER}; border-radius: 12px; }}"
        )
        pv = QVBoxLayout(popup)
        pv.setContentsMargins(14, 12, 14, 14)
        pv.setSpacing(8)
        head = QLabel("\u2727  " + topic)
        head.setStyleSheet(
            f"color: {CARD_TITLE}; font-size: 12px; font-weight: 800;"
            " background: transparent; border: none;"
        )
        pv.addWidget(head)
        sub = QLabel("\uc608\uc2dc\ub97c \uc120\ud0dd\ud558\uba74 \uc785\ub825\ucc3d\uc5d0 \ucc44\uc6cc\uc9d1\ub2c8\ub2e4")
        sub.setStyleSheet(f"color: {CARD_SUB}; font-size: 10px; background: transparent; border: none;")
        pv.addWidget(sub)
        pv.addSpacing(2)

        for i, text in enumerate(items, 1):
            item = _ClickableFrame()
            item.setObjectName("exItem")
            item.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            item.setStyleSheet(
                f"QFrame#exItem {{ background: #ffffff; border: 1px solid {CARD_L_BORDER};"
                " border-radius: 8px; }"
                f"QFrame#exItem:hover {{ border: 1px solid {TEAL_DIM}; background: #eefbf8; }}"
            )
            il = QVBoxLayout(item)
            il.setContentsMargins(12, 10, 12, 10)
            il.setSpacing(0)
            lbl = QLabel(f"{i}. {text}")
            lbl.setWordWrap(True)
            lbl.setStyleSheet(
                f"color: {CARD_TITLE}; font-size: 11px; background: transparent; border: none;"
            )
            il.addWidget(lbl)
            item.clicked.connect(lambda t=text: self._select_example(t))
            pv.addWidget(item)

        popup.setFixedWidth(560)
        popup.adjustSize()
        self._example_popup = popup
        below = anchor.mapToGlobal(QPoint(0, anchor.height() + 8))
        popup.move(below)
        popup.show()

    def _select_example(self, text: str):
        self.prompt.setPlainText(text)
        if self._example_popup is not None:
            self._example_popup.close()
        self.prompt.setFocus()

    def _use_chip(self, text: str):
        self.prompt.setPlainText(self.CHIP_PROMPTS.get(text, text))
        self.prompt.setFocus()

    def _run(self):
        text = self.prompt.toPlainText().strip()
        keys = self._selected_keys()
        self._win.launch(text, keys)


# ===========================================================================
# WORKSPACE SCREEN
# ===========================================================================
class ToolChip(QFrame):
    def __init__(self, glyph: str, name: str, status: str = TEAL, light: bool = False, parent=None, key: str | None = None):
        super().__init__(parent)
        self.glyph = glyph
        self.name = name
        self.key = key if key is not None else name
        self.status = status
        self.light = light
        self.selected = False
        self._on_click = None
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        lay = QHBoxLayout(self)
        lay.setContentsMargins(11, 6, 12, 6)
        lay.setSpacing(7)
        self._dot = QLabel("\u25cf")
        self._dot.setStyleSheet(f"color: {status}; font-size: 9px; background: transparent; border: none;")
        self._text = QLabel(f"{glyph} {name}".strip())
        lay.addWidget(self._dot)
        lay.addWidget(self._text)
        self._apply()

    def clicked_connect(self, fn):
        self._on_click = fn

    def _apply(self):
        if self.light:
            border = TEAL_DIM if self.selected else CARD_L_BORDER
            bg = "rgba(45,212,191,0.18)" if self.selected else "#ffffff"
            txt = "#0f766e" if self.selected else "#475569"
        else:
            border = TEAL_DIM if self.selected else BORDER
            bg = "rgba(45,212,191,0.10)" if self.selected else "rgba(255,255,255,0.02)"
            txt = TEXT if self.selected else TEXT_MUTED
        self.setStyleSheet(
            f"QFrame {{ background: {bg}; border: 1px solid {border}; border-radius: 14px; }}"
            f"QFrame:hover {{ border: 1px solid {TEAL_DIM}; }}"
        )
        self._text.setStyleSheet(f"color: {txt}; font-size: 12px; background: transparent; border: none;")
        self._dot.setStyleSheet(f"color: {self.status}; font-size: 9px; background: transparent; border: none;")

    def set_selected(self, value: bool):
        self.selected = value
        self._apply()

    def toggle(self):
        self.set_selected(not self.selected)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._on_click:
            self._on_click()
        super().mousePressEvent(event)


class ChatBubble(QFrame):
    def __init__(self, text: str, author: str = "agent", parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        is_agent = author == "agent"
        bubble = QLabel(text)
        bubble.setWordWrap(True)
        bubble.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        if is_agent:
            bubble.setTextFormat(Qt.TextFormat.MarkdownText)
            bubble.setOpenExternalLinks(True)
            bubble.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
                | Qt.TextInteractionFlag.LinksAccessibleByMouse
            )
        wrap = QHBoxLayout()
        if is_agent:
            bubble.setStyleSheet(
                f"QLabel {{ background: transparent; border: none;"
                f" color: {TEXT}; font-size: 12px; padding: 2px 0px; }}"
            )
            wrap.setContentsMargins(0, 0, 26, 0)
            wrap.addWidget(bubble)
        else:
            bubble.setStyleSheet(
                f"QLabel {{ background: rgba(45,212,191,0.13); border: 1px solid {TEAL_DIM};"
                f" border-radius: 12px; color: {TEXT}; font-size: 12px; padding: 12px 14px; }}"
            )
            wrap.setContentsMargins(40, 0, 0, 0)
            wrap.addStretch(1)
            wrap.addWidget(bubble)
        outer.addLayout(wrap)


class TabButton(QPushButton):
    def __init__(self, glyph: str, text: str, parent=None):
        super().__init__(f"{glyph}  {text}", parent)
        self.setCheckable(True)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._apply()
        self.toggled.connect(lambda _: self._apply())

    def _apply(self):
        if self.isChecked():
            self.setStyleSheet(
                f"QPushButton {{ background: rgba(45,212,191,0.10); border: 1px solid {BORDER};"
                f" border-radius: 8px; color: {TEXT}; font-size: 12px; font-weight: 700; padding: 6px 12px; }}"
            )
        else:
            self.setStyleSheet(
                f"QPushButton {{ background: transparent; border: 1px solid transparent;"
                f" border-radius: 8px; color: {TEXT_MUTED}; font-size: 12px; padding: 6px 12px; }}"
                f"QPushButton:hover {{ color: {TEXT}; }}"
            )


class _ClickableFrame(QFrame):
    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class CollapsibleResult(QFrame):
    """A collapsible (accordion) section for a single tool's result."""

    def __init__(self, label, status_text, status_color, output, parent=None):
        super().__init__(parent)
        self.setStyleSheet("QFrame { background: transparent; border: none; }")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Prominent, clickable header bar so each agent line stands out.
        self.header = _ClickableFrame()
        self.header.setObjectName("accHeader")
        self.header.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.header.setStyleSheet(
            "QFrame#accHeader { background: rgba(45,212,191,0.12);"
            f" border: none; border-left: 3px solid {TEAL}; }}"
            "QFrame#accHeader:hover { background: rgba(45,212,191,0.18); }"
        )
        hl = QHBoxLayout(self.header)
        hl.setContentsMargins(10, 8, 10, 8)
        hl.setSpacing(8)
        self._chevron = QLabel("\u25be")
        self._chevron.setStyleSheet(f"color: {TEAL}; font-size: 10px; background: transparent; border: none;")
        name = QLabel(label)
        name.setStyleSheet(
            f"color: {TEXT}; font-size: 13px; font-weight: 800; background: transparent; border: none;"
        )
        badge = QLabel(status_text)
        badge.setStyleSheet(
            f"color: {status_color}; font-size: 11px; font-weight: 700;"
            " background: transparent; border: none;"
        )
        hl.addWidget(self._chevron)
        hl.addWidget(name)
        hl.addStretch(1)
        hl.addWidget(badge)
        outer.addWidget(self.header)

        # Body holds the markdown-rendered output and can be collapsed.
        self.body = QFrame()
        self.body.setStyleSheet("QFrame { background: transparent; border: none; }")
        bl = QVBoxLayout(self.body)
        bl.setContentsMargins(13, 10, 6, 12)
        bl.setSpacing(0)
        md = QLabel(output)
        md.setTextFormat(Qt.TextFormat.MarkdownText)
        md.setWordWrap(True)
        md.setOpenExternalLinks(True)
        md.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        md.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; background: transparent; border: none;")
        bl.addWidget(md)
        outer.addWidget(self.body)

        self._expanded = False
        self.body.setVisible(False)
        self._chevron.setText("\u25b8")
        self.header.clicked.connect(self._toggle)

    def _toggle(self):
        self._expanded = not self._expanded
        self.body.setVisible(self._expanded)
        self._chevron.setText("\u25be" if self._expanded else "\u25b8")


class ResultsPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_items_layout = None
        self.setStyleSheet("QFrame { background: transparent; }")
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 16)
        root.setSpacing(14)

        root.addWidget(self._make_results_page(), 1)

    def _make_results_page(self):
        self.results_stack = QStackedWidget()
        self.results_stack.addWidget(self._make_empty_state())
        holder = QScrollArea()
        holder.setWidgetResizable(True)
        holder.setFrameShape(QFrame.Shape.NoFrame)
        holder.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        self.results_list = QVBoxLayout(inner)
        self.results_list.setContentsMargins(0, 4, 0, 4)
        self.results_list.setSpacing(12)
        self.results_list.addStretch(1)
        holder.setWidget(inner)
        self.results_stack.addWidget(holder)
        return self.results_stack

    def _make_empty_state(self):
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addStretch(1)
        icon = QLabel("\u2727")
        icon.setFixedSize(60, 60)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(
            f"background: rgba(255,255,255,0.03); border: 1px solid {BORDER_SOFT};"
            f" border-radius: 16px; color: {TEXT_MUTED}; font-size: 22px;"
        )
        lay.addWidget(icon, alignment=Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(18)
        title = QLabel("\uc544\uc9c1 \uc2e4\ud589\ub41c \uc791\uc5c5\uc774 \uc5c6\uc2b5\ub2c8\ub2e4")
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        title.setStyleSheet(f"color: {TEXT}; font-size: 16px; font-weight: 700; background: transparent;")
        lay.addWidget(title)
        lay.addSpacing(8)
        desc = QLabel(
            "\uc6b0\uce21\uc5d0\uc11c \ub0b4\uc6a9\uc744 \uc124\uba85\ud558\uace0 \ud544\uc694\ud55c \uc791\uc5c5\uc744 \uc120\ud0dd\ud574 \uc5d0\uc774\uc804\ud2b8\ub97c \uc2e4\ud589\ud558\uba74,\n"
            "\uacb0\uacfc\u00b7\uadfc\uac70\u00b7\uac10\uc0ac\ucd94\uc801\uc774 \uc774\uacf3\uc5d0 \ud45c\uc2dc\ub429\ub2c8\ub2e4."
        )
        desc.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        desc.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; background: transparent;")
        lay.addWidget(desc)
        lay.addSpacing(20)
        self.example_btn = QPushButton(f"\u21b3  \uc608: \"{EXAMPLE_PROMPT}\"")
        self.example_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.example_btn.setStyleSheet(
            f"QPushButton {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 9px;"
            f" color: {TEXT_MUTED}; font-size: 12px; padding: 9px 16px; }}"
            f"QPushButton:hover {{ color: {TEXT}; border: 1px solid {TEAL_DIM}; }}"
        )
        lay.addWidget(self.example_btn, alignment=Qt.AlignmentFlag.AlignHCenter)
        lay.addStretch(1)
        return w

    def _make_note(self, title, desc):
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(w)
        lay.addStretch(1)
        t = QLabel(title)
        t.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        t.setStyleSheet(f"color: {TEXT}; font-size: 15px; font-weight: 700; background: transparent;")
        d = QLabel(desc)
        d.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        d.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; background: transparent;")
        lay.addWidget(t)
        lay.addSpacing(6)
        lay.addWidget(d)
        lay.addStretch(1)
        return w

    def add_result(self, prompt, tools):
        """Start a new result group for one question (prompt)."""
        self.results_stack.setCurrentIndex(1)
        group = QFrame()
        group.setObjectName("resultGroup")
        group.setStyleSheet(
            "QFrame#resultGroup { background: transparent; border: none; border-radius: 0px; }"
        )
        gl = QVBoxLayout(group)
        gl.setContentsMargins(2, 8, 2, 8)
        gl.setSpacing(6)

        ts = QLabel(datetime.now().strftime("%H:%M:%S"))
        ts.setStyleSheet(f"color: {TEXT_FAINT}; font-size: 10px; background: transparent;")
        gl.addWidget(ts)

        body = QLabel(prompt)
        body.setWordWrap(True)
        body.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; font-weight: 600; background: transparent;")
        gl.addWidget(body)
        if tools:
            tags = QLabel("\uc791\uc5c5 \u00b7 " + " \u00b7 ".join(tools))
            tags.setStyleSheet(f"color: {TEAL}; font-size: 11px; background: transparent;")
            gl.addWidget(tags)

        # Connected container that holds all tool results for this question.
        # The continuous left line visually ties the results to the prompt above.
        items = QFrame()
        items.setObjectName("resultItems")
        items.setStyleSheet(
            "QFrame#resultItems { background: transparent; border: none;"
            f" border-left: 2px solid {TEAL_DIM}; border-radius: 0px; }}"
        )
        il = QVBoxLayout(items)
        il.setContentsMargins(14, 2, 0, 0)
        il.setSpacing(8)
        gl.addWidget(items)
        self._current_items_layout = il

        self.results_list.insertWidget(self.results_list.count() - 1, group)

    def add_tool_result(self, label: str, status: str, output: str):
        """Append a per-tool result into the current question's group."""
        self.results_stack.setCurrentIndex(1)
        if self._current_items_layout is None:
            self.add_result("\uacb0\uacfc", [])
        il = self._current_items_layout

        status_color = {"ok": TEAL, "error": RED, "skipped": TEXT_FAINT}.get(status, TEXT_MUTED)
        status_text = {"ok": "\uc644\ub8cc", "error": "\uc624\ub958", "skipped": "\uac74\ub108\ub6c0"}.get(status, status)
        section = CollapsibleResult(label, status_text, status_color, output)
        il.addWidget(section)

    def reset(self):
        while self.results_list.count() > 1:
            item = self.results_list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._current_items_layout = None
        self.results_stack.setCurrentIndex(0)


WORKSPACE_TOOLS = [
    ("", "Protocol Drafting", "Protocol Generator", TEAL),
    ("", "Scientific & PI Review", "PI", TEAL),
    ("", "Site Feasibility Review", "Site Physician", TEAL),
    ("", "Regulatory Review", "Health Authority", TEAL),
    ("", "TrialGPT Retrieval", "TrialGPT Retrieval", TEAL),
    ("", "TrialGPT Matching", "TrialGPT Matching", TEAL),
    ("", "TrialGPT Ranking", "TrialGPT Ranking", TEAL),
    ("", "CTG Retrieval", "CTG Retrieval", TEAL),
]

# Backend tool key -> workspace display label
TOOL_DISPLAY = {key: label for _, label, key, _ in WORKSPACE_TOOLS}


# ---------------------------------------------------------------------------
# Backend connection
# ---------------------------------------------------------------------------
AGENT_SERVER_URL = os.getenv("AGENT_SERVER_URL", "http://127.0.0.1:8000")


class RunWorker(QThread):
    """Streams the agent server's /agent/run/stream endpoint off the UI thread.

    Emits one signal per NDJSON event so the UI can render progressively:
    `routed` (tool selection), `step` (a finished tool result), `completed`
    (final summary), and `failed` (any error).
    """

    routed = pyqtSignal(dict)
    step = pyqtSignal(dict)
    completed = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, prompt: str, tools: list[str], api_key: str = "", parent=None):
        super().__init__(parent)
        self._prompt = prompt
        self._tools = tools
        self._api_key = api_key

    def run(self):
        body: dict = {"prompt": self._prompt, "tools": self._tools}
        if self._api_key:
            body["openai_api_key"] = self._api_key
        payload = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            f"{AGENT_SERVER_URL}/agent/run/stream",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                for raw in resp:  # NDJSON: one event per line, as it arrives
                    line = raw.decode("utf-8").strip()
                    if not line:
                        continue
                    ev = json.loads(line)
                    kind = ev.get("type")
                    if kind == "routed":
                        self.routed.emit(ev)
                    elif kind == "result":
                        self.step.emit(ev)
                    elif kind == "done":
                        self.completed.emit(ev)
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            self.failed.emit(str(reason))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class TypingIndicator(QFrame):
    """A Claude-style blinking 'thinking' bubble shown while the agent runs."""

    def __init__(self, label: str = "처리 중", parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        wrap = QHBoxLayout()
        wrap.setContentsMargins(0, 0, 26, 0)
        bubble = QFrame()
        bubble.setStyleSheet("QFrame { background: transparent; border: none; }")
        bl = QHBoxLayout(bubble)
        bl.setContentsMargins(2, 2, 2, 2)
        bl.setSpacing(6)
        self._caption = QLabel(label)
        self._caption.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; background: transparent; border: none;")
        bl.addWidget(self._caption)
        self._dots: list[QLabel] = []
        for _ in range(3):
            dot = QLabel("\u25cf")
            bl.addWidget(dot)
            self._dots.append(dot)
        wrap.addWidget(bubble)
        wrap.addStretch(1)
        outer.addLayout(wrap)

        self._phase = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(300)
        self._tick()

    def _tick(self):
        for i, dot in enumerate(self._dots):
            on = (i == self._phase % len(self._dots))
            color = TEAL if on else "rgba(148,163,184,0.45)"
            dot.setStyleSheet(f"color: {color}; font-size: 8px; background: transparent; border: none;")
        self._phase += 1

    def stop(self):
        self._timer.stop()


class AgentPanel(QFrame):
    def __init__(self, results: ResultsPanel, window: "MainWindow", parent=None):
        super().__init__(parent)
        self._results = results
        self._win = window
        self.setObjectName("agentPanel")
        self.setStyleSheet("QFrame#agentPanel { background: transparent; border-left: 1px solid rgba(255,255,255,0.20); }")
        self.chips: list[ToolChip] = []
        self._tool_popup: QFrame | None = None
        self._worker: RunWorker | None = None
        self._pending_bubble: TypingIndicator | None = None
        self._pending_prompt: str = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 16)
        root.setSpacing(0)

        head = QHBoxLayout()
        head.setSpacing(10)
        head.addWidget(IconBadge("\u25c8", 22, 8))
        t = QLabel("Trial Agent")
        t.setStyleSheet(f"color: {TEXT}; font-size: 14px; font-weight: 800; background: transparent;")
        head.addWidget(t)
        head.addStretch(1)
        root.addLayout(head)
        root.addSpacing(14)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet(
            f"QScrollArea {{ background: transparent; border: none; }}"
            f"QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}"
            f"QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 4px; min-height: 30px; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}"
        )
        chat_holder = QWidget()
        chat_holder.setStyleSheet("background: transparent;")
        self.chat_layout = QVBoxLayout(chat_holder)
        self.chat_layout.setContentsMargins(0, 0, 4, 0)
        self.chat_layout.setSpacing(14)
        self.chat_layout.addStretch(1)
        self.scroll.setWidget(chat_holder)
        root.addWidget(self.scroll, 1)
        root.addSpacing(12)

        # tool chips live inside a pop-up menu opened from the "대상 도구" button
        for glyph, name, key, status in WORKSPACE_TOOLS:
            chip = ToolChip(glyph, name, status, light=True, key=key)
            chip.clicked_connect(lambda c=chip: self._toggle_chip(c))
            self.chips.append(chip)

        box = QFrame()
        box.setStyleSheet("QFrame { background: #c7cfda; border: 1px solid #a7b2c1; border-radius: 14px; }")
        bl = QVBoxLayout(box)
        bl.setContentsMargins(14, 12, 12, 10)
        bl.setSpacing(8)
        self.input = QPlainTextEdit()
        self.input.setPlaceholderText(
            "\uc791\uc5c5\uc744 \uc124\uba85\ud558\uc138\uc694...  (\uc608: \ud6c4\ubcf4 \uc784\uc0c1\uc2dc\ud5d8\uc744 \uac80\uc0c9\ud574 \uae30\uc900 \uc810\uc218\ub85c \uc21c\uc704\ud654)"
        )
        self.input.setFixedHeight(54)
        self.input.setFrameShape(QFrame.Shape.NoFrame)
        self.input.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.input.setStyleSheet(
            "QPlainTextEdit { background: transparent; border: none; color: #0f172a; font-size: 13px; }"
        )
        bl.addWidget(self.input)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.sel_btn = QPushButton("@ \ub300\uc0c1 \uc791\uc5c5 0")
        self.sel_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.sel_btn.clicked.connect(self._open_tool_menu)
        self._update_sel()
        row.addWidget(self.sel_btn)
        row.addStretch(1)
        run = QPushButton("\u25b6")
        run.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        run.setFixedSize(28, 28)
        run.clicked.connect(self._run)
        run.setStyleSheet(
            f"QPushButton {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {TEAL}, stop:1 #16b8a6);"
            f" color: #06251f; border: none; border-radius: 8px; font-size: 12px; font-weight: 800; padding-left: 2px; }}"
            f"QPushButton:hover {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #3ce0cc, stop:1 #1cc6b3); }}"
        )
        row.addWidget(run)
        bl.addLayout(row)
        root.addWidget(box)

        results.example_btn.clicked.connect(self._use_example)

    # behaviour ------------------------------------------------------------
    def _add_bubble(self, text, author):
        bubble = ChatBubble(text, author)
        # Keep the typing indicator pinned to the bottom while it's active.
        if self._pending_bubble is not None:
            idx = self.chat_layout.indexOf(self._pending_bubble)
            self.chat_layout.insertWidget(idx, bubble)
        else:
            self.chat_layout.insertWidget(self.chat_layout.count() - 1, bubble)
        self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum())
        return bubble

    def _toggle_chip(self, chip):
        chip.toggle()
        self._update_sel()

    def _selected_tools(self):
        return [c.key for c in self.chips if c.selected]

    def _update_sel(self):
        n = len(self._selected_tools())
        self.sel_btn.setText(f"@ \ub300\uc0c1 \uc791\uc5c5 {n}")
        if n:
            self.sel_btn.setStyleSheet(
                f"QPushButton {{ background: rgba(45,212,191,0.18); border: 1px solid {TEAL_DIM};"
                f" border-radius: 9px; color: #0f766e; font-size: 12px; font-weight: 700; padding: 6px 11px; }}"
            )
        else:
            self.sel_btn.setStyleSheet(
                "QPushButton { background: #ffffff; border: 1px solid #c2ccd8;"
                " border-radius: 9px; color: #64748b; font-size: 12px; padding: 6px 11px; }"
                "QPushButton:hover { color: #1e293b; border: 1px solid #94a3b8; }"
            )

    def _open_tool_menu(self):
        if self._tool_popup is None:
            popup = QFrame(self, Qt.WindowType.Popup)
            popup.setStyleSheet(
                f"QFrame {{ background: {CARD_L}; border: 1px solid {CARD_L_BORDER}; border-radius: 12px; }}"
            )
            pv = QVBoxLayout(popup)
            pv.setContentsMargins(14, 12, 14, 14)
            pv.setSpacing(10)
            head = QLabel("\u2727  \uc791\uc5c5 \uc120\ud0dd")
            head.setStyleSheet(f"color: {CARD_SUB}; font-size: 12px; font-weight: 700; background: transparent; border: none;")
            pv.addWidget(head)
            chip_wrap = QWidget()
            chip_wrap.setStyleSheet("background: transparent;")
            flow = FlowLayout(chip_wrap, spacing=8)
            for chip in self.chips:
                flow.addWidget(chip)
            pv.addWidget(chip_wrap)
            popup.setFixedWidth(320)
            self._tool_popup = popup

        popup = self._tool_popup
        popup.adjustSize()
        top_left = self.sel_btn.mapToGlobal(QPoint(0, 0))
        popup.move(top_left.x(), top_left.y() - popup.height() - 8)
        popup.show()

    def select_tools(self, keys):
        for c in self.chips:
            c.set_selected(c.key in keys)
        self._update_sel()

    def _use_example(self):
        self.input.setPlainText(EXAMPLE_PROMPT)
        self.input.setFocus()

    def _run(self):
        if self._worker is not None and self._worker.isRunning():
            return
        text = self.input.toPlainText().strip()
        if not text:
            return
        tools = self._selected_tools()
        self._add_bubble(text, "user")
        self.input.clear()
        self._pending_prompt = text

        log.info("run requested | tools=%s | prompt=%.40s", tools or "auto", text)
        self._pending_bubble = TypingIndicator("Agent working")
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, self._pending_bubble)
        self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum())
        self._worker = RunWorker(text, tools, getattr(self._win, "api_key", ""), self)
        self._worker.routed.connect(self._on_routed)
        self._worker.step.connect(self._on_step)
        self._worker.completed.connect(self._on_completed)
        self._worker.failed.connect(self._on_run_failed)
        self._worker.start()

    def _clear_pending(self):
        if self._pending_bubble is not None:
            self._pending_bubble.stop()
            self._pending_bubble.setParent(None)
            self._pending_bubble.deleteLater()
            self._pending_bubble = None

    def _on_routed(self, ev: dict):
        tools = ev.get("tools", [])
        log.info("routed | auto=%s | tools=%s", ev.get("auto_routed"), tools)
        names = [TOOL_DISPLAY.get(t, t) for t in tools]
        # Start a fresh result group on the left for this question.
        self._results.add_result(self._pending_prompt, names)
        if not tools:
            self._add_bubble("No tools were selected for this request.", "agent")
            return
        verb = "tool" if len(tools) == 1 else "tools"
        joined = ", ".join(names)
        if ev.get("auto_routed"):
            # Tools came from the LLM planner — present them as a plan.
            self._add_bubble(
                f"**Planning result** — selected {len(tools)} {verb} for this request:\n{joined}",
                "agent",
            )
        else:
            self._add_bubble(f"Selected {verb}: {joined}", "agent")

    def _on_step(self, ev: dict):
        # Render each tool result on the left as soon as it arrives.
        log.info("step | %s | %s", ev.get("label"), ev.get("status"))
        self._results.add_tool_result(
            ev.get("label", ev.get("tool", "")),
            ev.get("status", ""),
            ev.get("output", ""),
        )

    def _on_completed(self, ev: dict):
        self._clear_pending()
        log.info("run done | %d ok / %d total | mock=%s",
                 ev.get("ok"), ev.get("total"), ev.get("mock"))
        if ev.get("mock"):
            self._add_bubble("(mock response · OPENAI_API_KEY not set)", "agent")
        self._worker = None

    def _on_run_failed(self, message: str):
        self._clear_pending()
        log.error("run failed: %s", message)
        self._add_bubble(
            "\uc11c\ubc84 \uc5f0\uacb0\uc5d0 \uc2e4\ud328\ud588\uc2b5\ub2c8\ub2e4: " + message + "\n"
            "\uc5d0\uc774\uc804\ud2b8 \uc11c\ubc84\uac00 \uc2e4\ud589 \uc911\uc778\uc9c0 \ud655\uc778\ud574 \uc8fc\uc138\uc694 "
            "(./venv/bin/python backend/agent_server.py).",
            "agent",
        )

    def start_task(self, prompt: str, keys: list[str]):
        """Called from the launcher: prefill, select tools, and run."""
        self.select_tools(keys)
        if prompt:
            self.input.setPlainText(prompt)
            self._run()

    def reset(self):
        while self.chat_layout.count() > 1:
            item = self.chat_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for c in self.chips:
            c.set_selected(False)
        self._update_sel()
        self.input.clear()
        self._results.reset()


class WorkspacePage(QWidget):
    def __init__(self, window: "MainWindow"):
        super().__init__()
        self.setObjectName("workspacePage")
        self._bg = QPixmap(BACKGROUND_PATH)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(TitleBar(window, show_home=True))

        split = QHBoxLayout()
        split.setContentsMargins(0, 0, 0, 0)
        split.setSpacing(0)
        self.results = ResultsPanel()
        self.agent = AgentPanel(self.results, window)
        self.agent.setFixedWidth(360)
        split.addWidget(self.results, 1)
        split.addWidget(self.agent)
        outer.addLayout(split, 1)

    def paintEvent(self, event):
        painter = QPainter(self)
        rect = self.rect()
        if not self._bg.isNull():
            scaled = self._bg.scaled(
                rect.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (scaled.width() - rect.width()) // 2
            y = (scaled.height() - rect.height()) // 2
            painter.drawPixmap(rect, scaled, QRect(x, y, rect.width(), rect.height()))
        else:
            painter.fillRect(rect, QColor(BG_BOTTOM))
        overlay = QLinearGradient(0, 0, rect.width() * 0.4, rect.height())
        overlay.setColorAt(0.0, QColor(8, 12, 19, 200))
        overlay.setColorAt(1.0, QColor(10, 14, 21, 224))
        painter.fillRect(rect, overlay)
        super().paintEvent(event)


# ===========================================================================
# MAIN WINDOW
# ===========================================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DATAIZEAI - Trial Agent")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)

        # OPENAI_API_KEY entered on the launcher; sent with each run so the
        # backend can switch out of mock mode and call the real models.
        self.api_key = os.environ.get("OPENAI_API_KEY", "")

        # square window based on width, clamped to the available screen
        side = 1240
        screen = QApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            side = min(side, avail.width() - 24, avail.height() - 24)
        self.resize(side, side)
        self.setMinimumSize(760, 760)

        self.stack = QStackedWidget()
        self.stack.setObjectName("central")
        self.stack.setStyleSheet(f"QStackedWidget#central {{ background: {BG_BOTTOM}; }}")
        self.launcher = LauncherPage(self)
        self.workspace = WorkspacePage(self)
        self.stack.addWidget(self.launcher)
        self.stack.addWidget(self.workspace)
        self.setCentralWidget(self.stack)

    def launch(self, prompt: str, keys: list[str]):
        self.stack.setCurrentWidget(self.workspace)
        self.workspace.agent.start_task(prompt, keys)

    def go_home(self):
        self.workspace.agent.reset()
        self.stack.setCurrentWidget(self.launcher)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    font = QFont("Apple SD Gothic Neo")
    font.setPixelSize(13)
    app.setFont(font)
    win = MainWindow()
    screen = app.primaryScreen()
    if screen is not None:
        geo = win.frameGeometry()
        geo.moveCenter(screen.availableGeometry().center())
        win.move(geo.topLeft())
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

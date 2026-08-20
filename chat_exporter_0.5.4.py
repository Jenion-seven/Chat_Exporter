#!/usr/bin/env python3
"""
Chat Exporter 0.5
Desktop PySide6 edition.

A native GUI wrapper around the proven ChatGPT shared-conversation parser
from ChatExporter 0.3, with the output modes and clean HTML workflow
developed in the browser prototype.

Requires:
    pip install PySide6 requests markdown

Run:
    python chat_exporter_0.5.py
"""

import sys
import re
import json
from pathlib import Path
from urllib.parse import urlparse

import requests
import markdown as md_lib

from PySide6.QtCore import (
    Qt,
    QObject,
    QThread,
    Signal,
    QSize,
    QMimeData,
)
from PySide6.QtGui import (
    QFont,
    QCursor,
)
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QFrame,
    QRadioButton,
    QButtonGroup,
    QTextBrowser,
    QSizePolicy,
    QScrollArea,
)


APP_NAME = "Chat Exporter"
APP_VERSION = "0.5.4"

REF_TOKEN_RE = re.compile(
    r"([a-zA-Z0-9_-]+)(?:([^]*))?"
)


# ==================================================
# Core parser
# ==================================================

def download_page(url):
    response = requests.get(
        url,
        timeout=30,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )
    response.raise_for_status()
    return response.text


def extract_router_data(html):
    pattern = (
        r'window\.__reactRouterContext\.streamController'
        r'\.enqueue\("(.+?)"\);'
    )

    matches = re.findall(
        pattern,
        html,
        flags=re.DOTALL
    )

    if not matches:
        raise RuntimeError(
            "Could not find ChatGPT conversation data "
            "in the shared page."
        )

    candidates = []

    for block in matches:
        try:
            decoded = json.loads(f'"{block}"')
        except json.JSONDecodeError:
            continue

        try:
            parsed = json.loads(decoded)
        except (json.JSONDecodeError, TypeError):
            continue

        if isinstance(parsed, list):
            candidates.append(parsed)

    if not candidates:
        raise RuntimeError(
            "Found ChatGPT page data, but could not "
            "identify a conversation payload."
        )

    return max(candidates, key=len)


def make_helpers(data):

    def decode_key(key):
        if isinstance(key, str) and key.startswith("_"):
            number = key[1:]
            if number.isdigit():
                index = int(number)
                if 0 <= index < len(data):
                    return data[index]
        return key

    def deref(value):
        if (
            isinstance(value, int)
            and not isinstance(value, bool)
            and 0 <= value < len(data)
        ):
            return data[value]
        return value

    def decode_dict(obj):
        if not isinstance(obj, dict):
            return {}

        result = {}

        for raw_key, value in obj.items():
            real_key = decode_key(raw_key)
            if isinstance(real_key, str):
                result[real_key] = value

        return result

    def get_field(obj, field_name):
        if not isinstance(obj, dict):
            return None

        for raw_key, value in obj.items():
            if decode_key(raw_key) == field_name:
                return deref(value)

        return None

    return decode_key, deref, decode_dict, get_field



def build_citation_lookup(data, decode_dict, deref):
    """
    Build a lookup from ChatGPT citation tokens to their
    human-readable Markdown alternatives.

    Shared pages store web citations separately from the
    message text. The message contains a token such as:

        citeturn0search2turn0search4

    Elsewhere in the router data, a citation record contains
    the same token as ``matched_text`` plus an ``alt`` field
    containing a ready-to-render Markdown link.
    """
    lookup = {}

    for item in data:
        if not isinstance(item, dict):
            continue

        decoded = decode_dict(item)

        if not {"matched_text", "alt"}.issubset(decoded.keys()):
            continue

        matched_text = deref(decoded["matched_text"])
        alt = deref(decoded["alt"])
        citation_type = deref(decoded.get("type"))

        if (
            isinstance(matched_text, str)
            and isinstance(alt, str)
            and matched_text.startswith("cite")
            and alt.strip()
            and citation_type in ("grouped_webpages", "webpage_extended", "webpage")
        ):
            lookup[matched_text] = alt.strip()

    return lookup

def build_nodes(data, decode_dict, deref):
    nodes = {}

    for index, item in enumerate(data):

        if not isinstance(item, dict):
            continue

        decoded = decode_dict(item)

        required = {
            "id",
            "message",
            "parent",
            "children",
        }

        if not required.issubset(decoded.keys()):
            continue

        node_id = deref(decoded["id"])

        if not isinstance(node_id, str):
            continue

        nodes[node_id] = {
            "table_index": index,
            "message_ref": decoded["message"],
            "parent": deref(decoded["parent"]),
            "children": deref(decoded["children"]),
        }

    return nodes


def find_conversation_info(data, nodes, decode_dict, deref):
    for item in data:

        if not isinstance(item, dict):
            continue

        decoded = decode_dict(item)

        if "current_node" not in decoded:
            continue

        current_node = deref(decoded["current_node"])

        if current_node not in nodes:
            continue

        title = None

        if "title" in decoded:
            candidate = deref(decoded["title"])

            if isinstance(candidate, str):
                title = candidate.strip()

        return current_node, title

    return None, None


def build_active_path(nodes, current_node):
    ordered = []
    visited = set()
    node_id = current_node

    while node_id in nodes:

        if node_id in visited:
            raise RuntimeError(
                "A loop was detected in the conversation graph."
            )

        visited.add(node_id)

        node = nodes[node_id]
        ordered.append(node)

        parent = node["parent"]

        if not parent or parent not in nodes:
            break

        node_id = parent

    ordered.reverse()
    return ordered


def fallback_linear_path(nodes):
    roots = [
        node_id
        for node_id, node in nodes.items()
        if (
            node["parent"] is None
            or node["parent"] not in nodes
        )
    ]

    if len(roots) != 1:
        raise RuntimeError(
            "Could not determine a unique conversation path."
        )

    ordered = []
    visited = set()
    current_id = roots[0]

    while current_id in nodes:

        if current_id in visited:
            raise RuntimeError(
                "A loop was detected in the conversation graph."
            )

        visited.add(current_id)

        node = nodes[current_id]
        ordered.append(node)

        children = node["children"]

        if not children:
            break

        next_child = children[0]

        if isinstance(next_child, int):
            break

        current_id = next_child

    return ordered


def get_role(message, get_field):
    author = get_field(message, "author")

    if not isinstance(author, dict):
        return None

    return get_field(author, "role")


def get_text(message, get_field, deref):
    content = get_field(message, "content")

    if not isinstance(content, dict):
        return None

    content_type = get_field(content, "content_type")

    if content_type not in (
        "text",
        "multimodal_text",
    ):
        return None

    texts = []

    parts = get_field(content, "parts")

    if isinstance(parts, list):
        for part_ref in parts:
            part = deref(part_ref)

            if isinstance(part, str):
                texts.append(part)
                continue

            if isinstance(part, dict):
                part_text = get_field(part, "text")

                if isinstance(part_text, str):
                    texts.append(part_text)

    direct_text = get_field(content, "text")

    if isinstance(direct_text, str):
        if direct_text not in texts:
            texts.append(direct_text)

    texts = [
        text
        for text in texts
        if isinstance(text, str) and text.strip()
    ]

    if not texts:
        return None

    return "\n".join(texts)


def clean_known_artifacts(text):
    text = text.strip()

    if text == (
        "Original custom instructions "
        "no longer available"
    ):
        return ""

    return text


def extract_messages(ordered_nodes, deref, get_field):
    messages = []

    for node in ordered_nodes:
        message = deref(node["message_ref"])

        if not isinstance(message, dict):
            continue

        role = get_role(message, get_field)

        if role not in (
            "user",
            "assistant",
        ):
            continue

        text = get_text(
            message,
            get_field,
            deref
        )

        if not text:
            continue

        text = clean_known_artifacts(text)

        if not text:
            continue

        messages.append({
            "role": role,
            "text": text,
        })

    return messages


def parse_conversation(html):
    data = extract_router_data(html)

    (
        decode_key,
        deref,
        decode_dict,
        get_field,
    ) = make_helpers(data)

    nodes = build_nodes(
        data,
        decode_dict,
        deref
    )

    if not nodes:
        raise RuntimeError(
            "No conversation nodes were found."
        )

    current_node, title = find_conversation_info(
        data,
        nodes,
        decode_dict,
        deref
    )

    if current_node:
        ordered_nodes = build_active_path(
            nodes,
            current_node
        )
    else:
        ordered_nodes = fallback_linear_path(
            nodes
        )

    messages = extract_messages(
        ordered_nodes,
        deref,
        get_field
    )

    citation_lookup = build_citation_lookup(
        data,
        decode_dict,
        deref
    )

    if not messages:
        raise RuntimeError(
            "No user or assistant messages were found."
        )

    return {
        "title": title or "ChatGPT Conversation",
        "messages": messages,
        "citation_lookup": citation_lookup,
    }


# ==================================================
# References + renderers
# ==================================================

def parse_ref_token(match):
    family = match.group(1)
    payload = match.group(2) or ""

    parts = [
        item
        for item in payload.split("")
        if item
    ]

    return {
        "raw": match.group(0),
        "family": family,
        "parts": parts,
    }


def transform_references(text, mode, refs, citation_lookup=None):
    if mode == "raw":
        return text

    citation_lookup = citation_lookup or {}

    def replace(match):
        if mode == "clean":
            raw = match.group(0)
            family = match.group(1)

            if family == "cite":
                resolved = citation_lookup.get(raw)
                if resolved:
                    return resolved

            return ""

        ref = parse_ref_token(match)
        refs.append(ref)

        return f"[[CHATREF:{len(refs)}]]"

    transformed = REF_TOKEN_RE.sub(
        replace,
        text
    )

    if mode == "clean":
        transformed = re.sub(
            r"[ \t]+\n",
            "\n",
            transformed
        )
        transformed = re.sub(
            r" {2,}",
            " ",
            transformed
        )

    return transformed.strip()


def make_markdown(messages, mode, citation_lookup=None):
    output = []
    refs = []

    for message in messages:

        if message["role"] == "user":
            speaker = "User name"
        else:
            speaker = "ChatGPT"

        output.append(
            f"## {speaker}"
        )

        output.append("")

        transformed = transform_references(
            message["text"],
            mode,
            refs,
            citation_lookup
        )

        output.append(transformed)
        output.append("")

    markdown_text = (
        "\n".join(output).rstrip()
        + "\n"
    )

    return markdown_text, refs


def reference_description(ref):
    names = {
        "cite": "Web citation",
        "filecite": "File citation",
        "memcite": "Memory citation",
    }

    label = names.get(
        ref["family"],
        ref["family"]
    )

    if ref["parts"]:
        details = " · ".join(
            ref["parts"]
        )
    else:
        details = "no embedded target data"

    return f"{label}: {details}"


def markdown_body_to_html(markdown_text):
    html = md_lib.markdown(
        markdown_text,
        extensions=[
            "fenced_code",
            "tables",
        ]
    )

    html = re.sub(
        r"\[\[CHATREF:(\d+)\]\]",
        r'<sup class="chat-ref"><a href="#ref-\1">\1</a></sup>',
        html
    )

    return html


def make_html_document(
    title,
    markdown_text,
    refs,
    mode
):
    body = markdown_body_to_html(
        markdown_text
    )

    if mode == "refs" and refs:
        items = []

        for index, ref in enumerate(
            refs,
            start=1
        ):
            description = (
                reference_description(ref)
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )

            items.append(
                f'<li id="ref-{index}">'
                f'<code>{description}</code>'
                f'</li>'
            )

        body += (
            '\n<section class="references">'
            '<h2>References</h2>'
            '<ol>'
            + "\n".join(items)
            + '</ol></section>'
        )

    safe_title = (
        title
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{safe_title}</title>
</head>
<body>
{body}
</body>
</html>
"""


def safe_filename(title, extension):
    filename = (
        title
        if title
        else "ChatGPT Conversation"
    )

    filename = re.sub(
        r'[\\/:*?"<>|]',
        '',
        filename
    )

    filename = re.sub(
        r'\s+',
        ' ',
        filename
    ).strip()

    if not filename:
        filename = "ChatGPT Conversation"

    return f"{filename}{extension}"


# ==================================================
# Background fetch worker
# ==================================================

class FetchWorker(QObject):
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            html = download_page(
                self.url
            )
            self.finished.emit(
                html
            )

        except requests.RequestException as error:
            self.failed.emit(
                "Could not download the shared conversation.\n"
                + str(error)
            )

        except Exception as error:
            self.failed.emit(
                str(error)
            )


# ==================================================
# Clickable mode card
# ==================================================

class ModeCard(QFrame):
    clicked = Signal()

    def __init__(
        self,
        title,
        description,
        radio,
        parent=None
    ):
        super().__init__(parent)

        self.radio = radio
        self.setObjectName(
            "modeCard"
        )
        self.setCursor(
            QCursor(Qt.PointingHandCursor)
        )
        self.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Fixed
        )
        self.setMinimumHeight(132)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            22, 18, 22, 18
        )
        layout.setSpacing(4)

        title_row = QHBoxLayout()
        title_row.setSpacing(10)

        self.radio.setCursor(
            QCursor(Qt.PointingHandCursor)
        )

        title_label = QLabel(
            title
        )
        title_label.setObjectName(
            "modeTitle"
        )

        title_row.addWidget(
            self.radio,
            0,
            Qt.AlignTop
        )
        title_row.addWidget(
            title_label,
            1
        )

        description_label = QLabel(
            description
        )
        description_label.setObjectName(
            "modeDescription"
        )
        description_label.setWordWrap(
            True
        )

        layout.addLayout(
            title_row
        )
        layout.addWidget(
            description_label
        )
        layout.addStretch()

        self.radio.toggled.connect(
            self.refresh_style
        )

        self.refresh_style()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.radio.setChecked(True)
            self.clicked.emit()

        super().mousePressEvent(event)

    def refresh_style(self):
        if self.radio.isChecked():
            self.setProperty(
                "selected",
                True
            )
        else:
            self.setProperty(
                "selected",
                False
            )

        self.style().unpolish(self)
        self.style().polish(self)


# ==================================================
# Smart preview scroll hand-off
# ==================================================

class SmartPreview(QTextBrowser):
    """
    Make nested scrolling feel like one continuous page.

    Scrolling down:
      - outer page scrolls until the preview reaches the top
      - then the preview itself scrolls

    Scrolling up:
      - preview scrolls back to its beginning first
      - then the outer page scrolls upward
    """

    def __init__(self, outer_scroll=None, parent=None):
        super().__init__(parent)
        self.outer_scroll = outer_scroll

    def set_outer_scroll(self, outer_scroll):
        self.outer_scroll = outer_scroll

    def preview_top_in_viewport(self):
        if self.outer_scroll is None:
            return 0

        viewport = self.outer_scroll.viewport()

        point = self.mapTo(
            viewport,
            self.rect().topLeft()
        )

        return point.y()

    def scroll_outer(self, event):
        if self.outer_scroll is None:
            return False

        scrollbar = (
            self.outer_scroll
            .verticalScrollBar()
        )

        # Pixel delta gives smooth trackpad scrolling when available.
        pixel_delta = event.pixelDelta().y()

        if pixel_delta:
            scrollbar.setValue(
                scrollbar.value()
                - pixel_delta
            )
            event.accept()
            return True

        angle_delta = event.angleDelta().y()

        if angle_delta:
            steps = angle_delta / 120.0
            amount = int(
                steps
                * scrollbar.singleStep()
                * 3
            )

            scrollbar.setValue(
                scrollbar.value()
                - amount
            )

            event.accept()
            return True

        return False

    def wheelEvent(self, event):
        if self.outer_scroll is None:
            super().wheelEvent(event)
            return

        preview_bar = self.verticalScrollBar()
        outer_bar = self.outer_scroll.verticalScrollBar()

        delta = (
            event.pixelDelta().y()
            or event.angleDelta().y()
        )

        # Scrolling downward:
        # let the whole page move until it can move no farther.
        # Then hand the same gesture to the conversation preview.
        if delta < 0:
            if outer_bar.value() < outer_bar.maximum():
                if self.scroll_outer(event):
                    return

            super().wheelEvent(event)
            return

        # Scrolling upward:
        # rewind the conversation first; when it reaches its top,
        # hand control back to the outer page.
        if delta > 0:
            if preview_bar.value() > preview_bar.minimum():
                super().wheelEvent(event)
                return

            if outer_bar.value() > outer_bar.minimum():
                if self.scroll_outer(event):
                    return

        super().wheelEvent(event)


# ==================================================
# Main window
# ==================================================

class ChatExporterWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.page_html = None
        self.conversation = None
        self.export_html = ""
        self.export_markdown = ""
        self.fetch_thread = None
        self.fetch_worker = None

        self.setWindowTitle(
            f"{APP_NAME} {APP_VERSION}"
        )

        self.resize(
            1120,
            820
        )

        self.build_ui()
        self.apply_styles()

    # ----------------------------------------------

    def build_ui(self):
        self.page_scroll = QScrollArea()
        self.page_scroll.setWidgetResizable(True)
        self.page_scroll.setFrameShape(QFrame.NoFrame)
        self.page_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff
        )

        root = QWidget()
        root.setObjectName(
            "pageRoot"
        )

        self.page_scroll.setWidget(
            root
        )

        self.setCentralWidget(
            self.page_scroll
        )

        page = QVBoxLayout(root)
        page.setContentsMargins(
            28, 28, 28, 28
        )
        page.setSpacing(18)

        # Header
        title = QLabel(
            "Chat Exporter"
        )
        title.setObjectName(
            "appTitle"
        )

        subtitle = QLabel(
            f"Version {APP_VERSION}"
        )
        subtitle.setObjectName(
            "muted"
        )

        page.addWidget(title)
        page.addWidget(subtitle)

        # URL panel
        url_panel = QFrame()
        url_panel.setObjectName(
            "panel"
        )

        url_layout = QVBoxLayout(
            url_panel
        )
        url_layout.setContentsMargins(
            20, 18, 20, 18
        )
        url_layout.setSpacing(10)

        url_label = QLabel(
            "ChatGPT Share URL"
        )
        url_label.setObjectName(
            "sectionTitle"
        )

        url_row = QHBoxLayout()
        url_row.setSpacing(10)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText(
            "https://chatgpt.com/share/…"
        )
        self.url_input.returnPressed.connect(
            self.fetch_conversation
        )

        self.fetch_button = QPushButton(
            "Fetch Chat"
        )
        self.fetch_button.clicked.connect(
            self.fetch_conversation
        )

        url_row.addWidget(
            self.url_input,
            1
        )
        url_row.addWidget(
            self.fetch_button
        )

        url_layout.addWidget(
            url_label
        )
        url_layout.addLayout(
            url_row
        )

        page.addWidget(
            url_panel
        )

        # Output mode panel
        mode_panel = QFrame()
        mode_panel.setObjectName(
            "panel"
        )

        mode_layout = QVBoxLayout(
            mode_panel
        )
        mode_layout.setContentsMargins(
            20, 18, 20, 18
        )
        mode_layout.setSpacing(16)

        mode_label = QLabel(
            "Output mode"
        )
        mode_label.setObjectName(
            "sectionTitle"
        )

        mode_layout.addWidget(
            mode_label
        )

        self.mode_group = QButtonGroup(
            self
        )
        self.mode_group.setExclusive(
            True
        )

        self.clean_radio = QRadioButton()
        self.raw_radio = QRadioButton()
        self.refs_radio = QRadioButton()

        self.clean_radio.setChecked(
            True
        )

        self.mode_group.addButton(
            self.clean_radio
        )
        self.mode_group.addButton(
            self.raw_radio
        )
        self.mode_group.addButton(
            self.refs_radio
        )

        cards = QHBoxLayout()
        cards.setSpacing(12)

        self.clean_card = ModeCard(
            "Clean HTML",
            "Hide ChatGPT reference markers for publishing and copy/paste.",
            self.clean_radio
        )

        self.raw_card = ModeCard(
            "Preserve Raw",
            "Keep citation and reference tokens intact for archival use.",
            self.raw_radio
        )

        self.refs_card = ModeCard(
            "Convert Ref Data",
            "Experimental: convert detected tokens into numbered notes.",
            self.refs_radio
        )

        cards.addWidget(
            self.clean_card
        )
        cards.addWidget(
            self.raw_card
        )
        cards.addWidget(
            self.refs_card
        )

        mode_layout.addLayout(
            cards
        )

        # Action row
        actions = QHBoxLayout()
        actions.setSpacing(10)

        self.export_button = QPushButton(
            "Export Chat"
        )
        self.export_button.setObjectName(
            "primaryButton"
        )
        self.export_button.clicked.connect(
            self.export_conversation
        )

        self.copy_button = QPushButton(
            "Copy HTML"
        )
        self.copy_button.clicked.connect(
            self.copy_html
        )

        self.html_button = QPushButton(
            "Download HTML"
        )
        self.html_button.clicked.connect(
            self.save_html
        )

        self.md_button = QPushButton(
            "Download Markdown"
        )
        self.md_button.clicked.connect(
            self.save_markdown
        )

        actions.addWidget(
            self.export_button
        )
        actions.addWidget(
            self.copy_button
        )
        actions.addWidget(
            self.html_button
        )
        actions.addWidget(
            self.md_button
        )
        actions.addStretch()

        mode_layout.addLayout(
            actions
        )

        self.status = QLabel(
            "Paste a ChatGPT Share URL to begin."
        )
        self.status.setObjectName(
            "status"
        )
        self.status.setWordWrap(
            True
        )

        mode_layout.addWidget(
            self.status
        )

        page.addWidget(
            mode_panel
        )

        # Preview panel
        preview_panel = QFrame()
        preview_panel.setObjectName(
            "panel"
        )

        preview_layout = QVBoxLayout(
            preview_panel
        )
        preview_layout.setContentsMargins(
            20, 18, 20, 20
        )
        preview_layout.setSpacing(10)

        preview_label = QLabel(
            "Preview"
        )
        preview_label.setObjectName(
            "sectionTitle"
        )

        self.preview = SmartPreview(
            self.page_scroll
        )
        self.preview.setOpenExternalLinks(
            True
        )
        self.preview.setMinimumHeight(
            650
        )
        self.preview.setPlaceholderText(
            "The exported conversation will appear here."
        )

        preview_layout.addWidget(
            preview_label
        )
        preview_layout.addWidget(
            self.preview,
            1
        )

        page.addWidget(
            preview_panel,
            1
        )

        self.set_output_actions_enabled(
            False
        )

    # ----------------------------------------------

    def apply_styles(self):
        self.setStyleSheet("""
        QMainWindow,
        QWidget {
            background: #15171a;
            color: #eef1f4;
            font-size: 15px;
        }

        QScrollArea {
            background: #15171a;
            border: none;
        }

        QWidget#pageRoot {
            background: #15171a;
        }

        QLabel#appTitle {
            font-size: 29px;
            font-weight: 700;
        }

        QLabel#muted {
            color: #9fa7b1;
            font-size: 13px;
        }

        QLabel#sectionTitle {
            font-size: 18px;
            font-weight: 700;
        }

        QFrame#panel {
            background: #1d2024;
            border: 1px solid #343a42;
            border-radius: 14px;
        }

        QLineEdit {
            background: #111316;
            color: #eef1f4;
            border: 1px solid #343a42;
            border-radius: 9px;
            padding: 11px 12px;
            min-height: 24px;
            selection-background-color: #6fa0ff;
        }

        QLineEdit:focus {
            border: 1px solid #8fb7ff;
        }

        QPushButton {
            background: #24282d;
            color: #eef1f4;
            border: 1px solid #343a42;
            border-radius: 9px;
            padding: 11px 16px;
            min-height: 24px;
        }

        QPushButton:hover {
            border-color: #59616c;
        }

        QPushButton:pressed {
            background: #2b3036;
        }

        QPushButton:disabled {
            color: #777d84;
            background: #1d2024;
            border-color: #2a2f35;
        }

        QPushButton#primaryButton {
            background: #dbe7ff;
            color: #172033;
            border-color: #dbe7ff;
            font-weight: 700;
            padding-left: 20px;
            padding-right: 20px;
        }

        QPushButton#primaryButton:hover {
            background: #e6eeff;
        }

        QFrame#modeCard {
            background: #191c20;
            border: 1px solid #3a414a;
            border-radius: 12px;
        }

        QFrame#modeCard[selected="true"] {
            background: #222d40;
            border: 2px solid #8fb7ff;
        }

        QLabel#modeTitle {
            font-size: 18px;
            font-weight: 700;
            background: transparent;
        }

        QLabel#modeDescription {
            color: #abb3be;
            font-size: 14px;
            background: transparent;
        }

        QRadioButton {
            background: transparent;
            spacing: 0px;
        }

        QRadioButton::indicator {
            width: 18px;
            height: 18px;
            border: 2px solid #8b9198;
            border-radius: 10px;
            background: transparent;
        }

        QRadioButton::indicator:checked {
            border: 5px solid #ff862f;
            background: #fff;
        }

        QLabel#status {
            color: #a9b0b8;
            padding-top: 2px;
        }

        QTextBrowser {
            background: #ffffff;
            color: #17191c;
            border: none;
            border-radius: 10px;
            padding: 18px;
            selection-background-color: #bcd2ff;
        }

        QScrollBar:vertical {
            background: #202328;
            width: 12px;
            margin: 2px;
        }

        QScrollBar::handle:vertical {
            background: #4b525c;
            min-height: 30px;
            border-radius: 5px;
        }

        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical {
            height: 0px;
        }
        """)

    # ----------------------------------------------

    def selected_mode(self):
        if self.raw_radio.isChecked():
            return "raw"

        if self.refs_radio.isChecked():
            return "refs"

        return "clean"

    # ----------------------------------------------

    def set_status(
        self,
        text,
        kind="normal"
    ):
        colors = {
            "normal": "#a9b0b8",
            "good": "#96d6a4",
            "warn": "#efc06d",
            "bad": "#ef8d8d",
        }

        color = colors.get(
            kind,
            colors["normal"]
        )

        self.status.setText(
            text
        )

        self.status.setStyleSheet(
            f"color: {color};"
        )

    # ----------------------------------------------

    def set_fetching(self, fetching):
        self.fetch_button.setDisabled(
            fetching
        )
        self.url_input.setDisabled(
            fetching
        )

        if fetching:
            self.fetch_button.setText(
                "Fetching…"
            )
        else:
            self.fetch_button.setText(
                "Fetch Chat"
            )

    # ----------------------------------------------

    def set_output_actions_enabled(
        self,
        enabled
    ):
        self.copy_button.setEnabled(
            enabled
        )
        self.html_button.setEnabled(
            enabled
        )
        self.md_button.setEnabled(
            enabled
        )

    # ----------------------------------------------

    def fetch_conversation(self):
        url = self.url_input.text().strip()

        if not url:
            self.set_status(
                "Paste a ChatGPT Share URL first.",
                "warn"
            )
            return

        if "chatgpt.com/share/" not in url:
            self.set_status(
                "That doesn't look like a ChatGPT Share URL.",
                "warn"
            )
            return

        self.page_html = None
        self.conversation = None
        self.export_html = ""
        self.export_markdown = ""
        self.preview.clear()

        self.set_output_actions_enabled(
            False
        )

        self.set_status(
            "Reading conversation…"
        )

        self.set_fetching(
            True
        )

        self.fetch_thread = QThread(
            self
        )
        self.fetch_worker = FetchWorker(
            url
        )

        self.fetch_worker.moveToThread(
            self.fetch_thread
        )

        self.fetch_thread.started.connect(
            self.fetch_worker.run
        )

        self.fetch_worker.finished.connect(
            self.fetch_finished
        )

        self.fetch_worker.failed.connect(
            self.fetch_failed
        )

        self.fetch_worker.finished.connect(
            self.fetch_thread.quit
        )

        self.fetch_worker.failed.connect(
            self.fetch_thread.quit
        )

        self.fetch_thread.finished.connect(
            self.fetch_worker.deleteLater
        )

        self.fetch_thread.finished.connect(
            self.fetch_thread.deleteLater
        )

        self.fetch_thread.start()

    # ----------------------------------------------

    def fetch_finished(self, html):
        self.set_fetching(
            False
        )

        try:
            self.page_html = html
            self.conversation = (
                parse_conversation(
                    html
                )
            )

            title = self.conversation[
                "title"
            ]

            count = len(
                self.conversation[
                    "messages"
                ]
            )

            self.set_status(
                f'Loaded "{title}" · {count} messages. '
                f'Choose an output mode and click Export Chat.',
                "good"
            )

        except Exception as error:
            self.page_html = None
            self.conversation = None

            self.set_status(
                "Could not parse conversation: "
                + str(error),
                "bad"
            )

    # ----------------------------------------------

    def fetch_failed(self, message):
        self.set_fetching(
            False
        )

        self.set_status(
            message,
            "bad"
        )

    # ----------------------------------------------

    def export_conversation(self):
        if not self.conversation:
            # Make Export Chat convenient:
            # if nothing has been fetched yet,
            # fetch the URL rather than simply failing.
            self.fetch_conversation()
            return

        try:
            mode = self.selected_mode()

            (
                markdown_text,
                refs,
            ) = make_markdown(
                self.conversation[
                    "messages"
                ],
                mode,
                self.conversation.get(
                    "citation_lookup",
                    {}
                )
            )

            html_document = (
                make_html_document(
                    self.conversation[
                        "title"
                    ],
                    markdown_text,
                    refs,
                    mode
                )
            )

            self.export_markdown = (
                markdown_text
            )

            self.export_html = (
                html_document
            )

            preview_html = (
                markdown_body_to_html(
                    markdown_text
                )
            )

            if mode == "refs" and refs:
                ref_items = []

                for index, ref in enumerate(
                    refs,
                    start=1
                ):
                    ref_items.append(
                        "<li>"
                        + reference_description(
                            ref
                        )
                        + "</li>"
                    )

                preview_html += (
                    "<hr><h2>References</h2>"
                    "<ol>"
                    + "".join(ref_items)
                    + "</ol>"
                )

            self.preview.setHtml(
                preview_html
            )

            self.set_output_actions_enabled(
                True
            )

            count = len(
                self.conversation[
                    "messages"
                ]
            )

            if mode == "refs":
                detail = (
                    f" · {len(refs)} "
                    f"reference token"
                    + (
                        ""
                        if len(refs) == 1
                        else "s"
                    )
                    + " converted"
                )
            else:
                detail = ""

            self.set_status(
                f"Exported {count} messages{detail}.",
                "good"
            )

        except Exception as error:
            self.set_status(
                "Could not export conversation: "
                + str(error),
                "bad"
            )

    # ----------------------------------------------

    def copy_html(self):
        if not self.export_html:
            return

        mime = QMimeData()

        mime.setHtml(
            self.export_html
        )

        mime.setText(
            self.export_markdown
        )

        QApplication.clipboard().setMimeData(
            mime
        )

        self.set_status(
            "Copied Substack-ready rich HTML to clipboard.",
            "good"
        )

    # ----------------------------------------------

    def save_html(self):
        if not self.export_html:
            return

        filename = safe_filename(
            self.conversation[
                "title"
            ],
            ".html"
        )

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save HTML",
            filename,
            "HTML files (*.html)"
        )

        if not path:
            return

        Path(path).write_text(
            self.export_html,
            encoding="utf-8"
        )

        self.set_status(
            f"Saved {Path(path).name}.",
            "good"
        )

    # ----------------------------------------------

    def save_markdown(self):
        if not self.export_markdown:
            return

        filename = safe_filename(
            self.conversation[
                "title"
            ],
            ".md"
        )

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Markdown",
            filename,
            "Markdown files (*.md)"
        )

        if not path:
            return

        Path(path).write_text(
            self.export_markdown,
            encoding="utf-8"
        )

        self.set_status(
            f"Saved {Path(path).name}.",
            "good"
        )


# ==================================================
# Main
# ==================================================

def main():
    app = QApplication(
        sys.argv
    )

    app.setApplicationName(
        APP_NAME
    )

    app.setOrganizationName(
        "Chat Exporter"
    )

    window = ChatExporterWindow()
    window.show()

    sys.exit(
        app.exec()
    )


if __name__ == "__main__":
    main()

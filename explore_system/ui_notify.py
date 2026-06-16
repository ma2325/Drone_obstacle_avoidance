#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""非阻塞 UI 通知：Toast + 状态栏；可配置自动确认（便于录演示）。"""

from __future__ import annotations

import html
import json
import os
from typing import Optional

from python_qt_binding.QtCore import QObject, QTimer, QEvent, Qt
try:
    from python_qt_binding.QtWidgets import QLabel, QMessageBox, QMainWindow, QApplication
except ImportError:
    from PyQt5.QtWidgets import QLabel, QMessageBox, QMainWindow, QApplication

_CONFIG: Optional[dict] = None
_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui_config.json")

_DEFAULTS = {
    "toast_duration_ms": 4500,
    "toast_warning_ms": 5500,
    "toast_error_ms": 9000,
    "auto_confirm_actions": [],
    "errors_use_modal_dialog": True,
    "mirror_to_status_bar": True,
    "status_bar_ms": 6000,
}


def get_ui_config() -> dict:
    global _CONFIG
    if _CONFIG is not None:
        return _CONFIG
    cfg = dict(_DEFAULTS)
    try:
        if os.path.isfile(_CONFIG_PATH):
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                user = json.load(f)
            if isinstance(user, dict):
                cfg.update(user)
    except Exception:
        pass
    _CONFIG = cfg
    return cfg


def reload_ui_config() -> dict:
    global _CONFIG
    _CONFIG = None
    return get_ui_config()


def resolve_main_window(widget) -> object:
    w = widget
    while w is not None:
        if isinstance(w, QMainWindow):
            return w
        w = w.parentWidget() if hasattr(w, "parentWidget") else None
    return widget


_STYLES = {
    "info": (
        "background-color: rgba(30, 35, 48, 0.96); color: #ECF0F1; "
        "border: 2px solid #3498DB; border-radius: 8px; padding: 12px 16px; font-family: sans-serif;"
    ),
    "warning": (
        "background-color: rgba(40, 35, 30, 0.96); color: #FCEFE0; "
        "border: 2px solid #E67E22; border-radius: 8px; padding: 12px 16px; font-family: sans-serif;"
    ),
    "error": (
        "background-color: rgba(45, 28, 28, 0.96); color: #FADBD8; "
        "border: 2px solid #E74C3C; border-radius: 8px; padding: 12px 16px; font-family: sans-serif;"
    ),
}


class _ToastController(QObject):
    def __init__(self, main_window: QMainWindow):
        super().__init__(main_window)
        self._w = main_window
        self._label = QLabel(main_window)
        self._label.setObjectName("explore_system_toast")
        self._label.setWordWrap(True)
        self._label.setMaximumWidth(440)
        self._label.setTextFormat(Qt.RichText)
        self._label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self._label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._label.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._label.hide)
        main_window.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self._w and event.type() == QEvent.Resize and self._label.isVisible():
            self._reposition()
        return False

    def _reposition(self):
        self._label.adjustSize()
        m = 24
        sb = 0
        try:
            sbw = self._w.statusBar()
            if sbw is not None and sbw.isVisible():
                sb = sbw.height()
        except Exception:
            pass
        x = self._w.width() - self._label.width() - m
        y = self._w.height() - self._label.height() - m - sb
        self._label.move(max(m, x), max(m, y))

    def show_toast(self, title: str, body: str, level: str = "info", duration_ms: Optional[int] = None):
        cfg = get_ui_config()
        if duration_ms is None:
            if level == "warning":
                duration_ms = int(cfg.get("toast_warning_ms", 5500))
            elif level == "error":
                duration_ms = int(cfg.get("toast_error_ms", 9000))
            else:
                duration_ms = int(cfg.get("toast_duration_ms", 4500))
        parts = []
        if title:
            parts.append(f"<b style='font-size:13pt;'>{html.escape(str(title))}</b>")
        body_html = html.escape(str(body)).replace("\n", "<br/>")
        parts.append(f"<span style='font-size:11pt;'>{body_html}</span>")
        self._label.setText("<br/>".join(parts))
        self._label.setStyleSheet(_STYLES.get(level, _STYLES["info"]))
        self._label.adjustSize()
        self._reposition()
        self._label.raise_()
        self._label.show()
        self._timer.stop()
        self._timer.start(int(duration_ms))


def _get_or_create_toast_controller(main_window: QMainWindow) -> _ToastController:
    attr = "_explore_toast_controller"
    if not hasattr(main_window, attr) or getattr(main_window, attr) is None:
        setattr(main_window, attr, _ToastController(main_window))
    return getattr(main_window, attr)


def notify(anchor_widget, title: str, body: str, level: str = "info", duration_ms: Optional[int] = None):
    """右下角 Toast + 可选状态栏；不阻塞操作。"""
    cfg = get_ui_config()
    plain = f"{title}: {body}" if title else str(body)
    plain_one_line = " ".join(plain.split())
    if cfg.get("mirror_to_status_bar", True):
        try:
            main_w = resolve_main_window(anchor_widget)
            if hasattr(main_w, "statusBar") and main_w.statusBar():
                main_w.statusBar().showMessage(plain_one_line[:500], int(cfg.get("status_bar_ms", 6000)))
        except Exception:
            pass
    main_w = resolve_main_window(anchor_widget)
    if isinstance(main_w, QMainWindow):
        try:
            ctrl = _get_or_create_toast_controller(main_w)
            ctrl.show_toast(title, body, level, duration_ms)
        except Exception:
            pass
    try:
        QApplication.processEvents()
    except Exception:
        pass


def notify_error(anchor_widget, title: str, body: str):
    """错误：默认仍可模态 critical；可在 ui_config 中改为非模态框。"""
    cfg = get_ui_config()
    if cfg.get("errors_use_modal_dialog", True):
        QMessageBox.critical(anchor_widget, title, body)
        return
    mb = QMessageBox(anchor_widget)
    mb.setWindowTitle(title)
    mb.setText(body)
    mb.setIcon(QMessageBox.Critical)
    mb.setModal(False)
    mb.show()
    try:
        QApplication.processEvents()
    except Exception:
        pass


def confirm(anchor_widget, action_id: str, title: str, text: str, default_no: bool = True) -> bool:
    """确认框；action_id 在 auto_confirm_actions 内则直接返回 True（录演示用）。"""
    if action_id in get_ui_config().get("auto_confirm_actions", []):
        return True
    default_btn = QMessageBox.No if default_no else QMessageBox.Yes
    reply = QMessageBox.question(
        anchor_widget,
        title,
        text,
        QMessageBox.Yes | QMessageBox.No,
        default_btn,
    )
    return reply == QMessageBox.Yes

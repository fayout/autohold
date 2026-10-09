"""
AutoHold Pro - Надежное зажатие клавиш мыши (Alt + ЛКМ / Alt + ПКМ, F6, F7, F8)
Разработано для фиксации зажатия клавиши на выбранном окне (игры, Minecraft OneBlock, программы).

Поддерживает запуск как с консолью, так и без консоли (pythonw / .pyw).
"""

import sys
import os

# Безопасная работа с pythonw (без консоли: sys.stdout и sys.stderr равны None)
if sys.stdout is None:
    try:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    except Exception:
        pass
if sys.stderr is None:
    try:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    except Exception:
        pass
if sys.stdin is None:
    try:
        sys.stdin = open(os.devnull, "r", encoding="utf-8")
    except Exception:
        pass

import time
import threading
import ctypes
from ctypes import wintypes
import tkinter as tk
from tkinter import ttk, messagebox
import winsound
from pynput import mouse, keyboard as pynput_kb

# Включение High-DPI
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Win32 константы
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP   = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP   = 0x0205
WM_MOUSEMOVE   = 0x0200

MK_LBUTTON     = 0x0001
MK_RBUTTON     = 0x0002

VK_MENU        = 0x12  # Alt
VK_LMENU       = 0xA4  # Левый Alt
VK_RMENU       = 0xA5  # Правый Alt
VK_LBUTTON     = 0x01
VK_RBUTTON     = 0x02
VK_F6          = 0x75  # F6
VK_F7          = 0x76  # F7
VK_F8          = 0x77  # F8
GA_ROOT        = 2

MOUSEEVENTF_LEFTDOWN   = 0x0002
MOUSEEVENTF_LEFTUP     = 0x0004
MOUSEEVENTF_RIGHTDOWN  = 0x0008
MOUSEEVENTF_RIGHTUP    = 0x0010


def is_alt_key_object(key):
    """Универсальная проверка, является ли объект клавиши pynput клавишей Alt (для любых раскладок)"""
    if key in (pynput_kb.Key.alt, pynput_kb.Key.alt_l, pynput_kb.Key.alt_r, pynput_kb.Key.alt_gr):
        return True
    vk = getattr(key, 'vk', None)
    if vk in (18, 164, 165):
        return True
    if 'alt' in str(key).lower():
        return True
    return False


def get_process_name_by_hwnd(hwnd):
    """Получить имя исполняемого файла (.exe) по HWND окна"""
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == 0:
        return "Unknown"
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    hproc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not hproc:
        return f"PID {pid.value}"
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(hproc, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value)
        return f"PID {pid.value}"
    finally:
        kernel32.CloseHandle(hproc)


def get_all_visible_windows():
    """Получить список всех видимых окон на десктопе"""
    windows = []
    seen = set()

    def check_and_add(hwnd):
        if hwnd in seen:
            return
        if not user32.IsWindowVisible(hwnd):
            return
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return
        buff = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buff, length + 1)
        title = buff.value.strip()
        if not title:
            return

        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        width = rect.right - rect.left
        height = rect.bottom - rect.top
        if width <= 20 or height <= 20:
            return

        ex_style = user32.GetWindowLongW(hwnd, -20)
        if ex_style & 0x00000080:  # WS_EX_TOOLWINDOW
            return

        seen.add(hwnd)
        pname = get_process_name_by_hwnd(hwnd)
        windows.append({
            "hwnd": hwnd,
            "title": title,
            "pname": pname,
            "display": f"[{pname}] {title}"
        })

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    hdesk = user32.OpenDesktopW("default", 0, False, 0x0040 | 0x0001)
    if hdesk:
        user32.EnumDesktopWindows(hdesk, WNDENUMPROC(lambda h, l: (check_and_add(h), True)[1]), 0)
        user32.CloseDesktop(hdesk)

    user32.EnumWindows(WNDENUMPROC(lambda h, l: (check_and_add(h), True)[1]), 0)
    windows.sort(key=lambda x: (x["pname"].lower(), x["title"].lower()))
    return windows


def find_input_target_hwnds(top_hwnd):
    """Находит фактические HWND для отправки сообщений (включая Canvas в играх)"""
    if not top_hwnd or not user32.IsWindow(top_hwnd):
        return []

    children = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def child_cb(chwnd, lparam):
        if user32.IsWindowVisible(chwnd):
            children.append(chwnd)
        return True

    user32.EnumChildWindows(top_hwnd, WNDENUMPROC(child_cb), 0)

    canvas_hwnds = []
    for ch in children:
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(ch, buf, 256)
        cls = buf.value.lower()
        if "canvas" in cls or "render" in cls or "gl" in cls:
            canvas_hwnds.append(ch)

    if canvas_hwnds:
        return canvas_hwnds

    if children:
        return [children[0], top_hwnd]

    return [top_hwnd]


class AutoHoldApp:
    def __init__(self, root):
        self.root = root
        self.root.title("AutoHold Pro — Зажатие клавиш мыши на окне")
        self.root.geometry("620x730")
        self.root.minsize(580, 680)

        # Переменные состояния
        self.target_window_data = None
        self.windows_cache = []

        self.lmb_held = False
        self.rmb_held = False
        self.hold_start_time = None
        self.physical_lmb_down = False
        self.physical_rmb_down = False

        self.alt_is_down = False
        self.last_lmb_toggle = 0
        self.last_rmb_toggle = 0
        self.is_picking = False
        self.lock = threading.Lock()
        self.worker_thread = None
        self.worker_running = False

        # Опции
        self.var_mode = tk.StringVar(value="smart_lock")  # Умная фиксация на окне
        self.var_sound = tk.BooleanVar(value=True)
        self.var_autotarget = tk.BooleanVar(value=True)   # Автоопределение окна
        self.var_ontop = tk.BooleanVar(value=False)
        self.var_interval = tk.StringVar(value="50")
        self.var_search = tk.StringVar(value="")

        # Цвета интерфейса
        self.bg_main = "#181820"
        self.bg_card = "#22222d"
        self.bg_card_inner = "#2a2a38"
        self.text_primary = "#f3f4f6"
        self.text_secondary = "#9ca3af"

        self.root.configure(bg=self.bg_main)
        self.setup_styles()
        self.build_ui()

        # 1. Запуск слушателя клавиатуры (pynput)
        self.kb_listener = pynput_kb.Listener(
            on_press=self.on_kb_press,
            on_release=self.on_kb_release
        )
        self.kb_listener.start()

        # 2. Запуск слушателя мыши (pynput)
        self.mouse_listener = mouse.Listener(on_click=self.on_mouse_click)
        self.mouse_listener.start()

        # 3. Дополнительный аппаратный опросник для 100% надежности
        self.hotkey_poller_running = True
        self.hotkey_poller_thread = threading.Thread(target=self._hotkey_poller_loop, daemon=True)
        self.hotkey_poller_thread.start()

        # Заполняем список окон
        self.refresh_windows_list()

        # Таймер обновления интерфейса
        self.update_ui_timer()

        # Обработка закрытия окна
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def is_alt_pressed_now(self):
        """Многоуровневая проверка зажатия клавиши Alt"""
        return bool(
            self.alt_is_down or
            (user32.GetAsyncKeyState(VK_MENU) & 0x8000) or
            (user32.GetAsyncKeyState(VK_LMENU) & 0x8000) or
            (user32.GetAsyncKeyState(VK_RMENU) & 0x8000)
        )

    def on_kb_press(self, key):
        if is_alt_key_object(key):
            self.alt_is_down = True
        elif key == pynput_kb.Key.f6:
            self.root.after(0, self.toggle_lmb)
        elif key == pynput_kb.Key.f7:
            self.root.after(0, self.toggle_rmb)
        elif key == pynput_kb.Key.f8:
            self.root.after(0, self.stop_all)
        elif key == pynput_kb.Key.esc:
            if self.lmb_held or self.rmb_held:
                self.root.after(0, self.stop_all)

    def on_kb_release(self, key):
        if is_alt_key_object(key):
            self.alt_is_down = False

    def on_mouse_click(self, x, y, button, pressed):
        if not pressed:
            return

        if self.is_picking:
            self.is_picking = False
            self.root.after(0, self.handle_picker_completed)
            return

        # Проверяем зажатие Alt
        if self.is_alt_pressed_now():
            if button == mouse.Button.left:
                self.root.after(0, self.toggle_lmb)
            elif button == mouse.Button.right:
                self.root.after(0, self.toggle_rmb)

    def _hotkey_poller_loop(self):
        """Фоновый поток для гарантированного отслеживания Alt + клик и F8"""
        prev_lmb = False
        prev_rmb = False
        prev_f8 = False

        while self.hotkey_poller_running:
            # F8 экстренный стоп
            f8_now = bool(user32.GetAsyncKeyState(VK_F8) & 0x8000)
            if f8_now and not prev_f8:
                self.root.after(0, self.stop_all)
            prev_f8 = f8_now

            # Проверка Alt + клик на уровне GetAsyncKeyState
            alt_now = self.is_alt_pressed_now()
            lmb_now = bool(user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)
            rmb_now = bool(user32.GetAsyncKeyState(VK_RBUTTON) & 0x8000)

            if alt_now and not self.is_picking:
                if lmb_now and not prev_lmb:
                    self.root.after(0, self.toggle_lmb)
                if rmb_now and not prev_rmb:
                    self.root.after(0, self.toggle_rmb)

            prev_lmb = lmb_now
            prev_rmb = rmb_now
            time.sleep(0.01)

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")

        style.configure("TFrame", background=self.bg_main)
        style.configure("Card.TFrame", background=self.bg_card, relief="flat")
        style.configure("CardInner.TFrame", background=self.bg_card_inner, relief="flat")

        style.configure("TLabel", background=self.bg_main, foreground=self.text_primary, font=("Segoe UI", 10))
        style.configure("Card.TLabel", background=self.bg_card, foreground=self.text_primary, font=("Segoe UI", 10))
        style.configure("CardSec.TLabel", background=self.bg_card, foreground=self.text_secondary, font=("Segoe UI", 9))

        style.configure("Header.TLabel", background=self.bg_main, foreground=self.text_primary, font=("Segoe UI", 14, "bold"))
        style.configure("SubHeader.TLabel", background=self.bg_main, foreground=self.text_secondary, font=("Segoe UI", 9))

        style.configure("TCheckbutton", background=self.bg_card, foreground=self.text_primary, font=("Segoe UI", 9))
        style.map("TCheckbutton", background=[("active", self.bg_card)])

        style.configure("TRadiobutton", background=self.bg_card, foreground=self.text_primary, font=("Segoe UI", 9))
        style.map("TRadiobutton", background=[("active", self.bg_card)])

        style.configure("TCombobox", padding=5, font=("Segoe UI", 10))

    def build_ui(self):
        container = ttk.Frame(self.root, padding=12)
        container.pack(fill="both", expand=True)

        # 1. Заголовок
        header_frame = ttk.Frame(container)
        header_frame.pack(fill="x", pady=(0, 10))

        title_lbl = ttk.Label(header_frame, text="🖱️ AutoHold Pro", style="Header.TLabel")
        title_lbl.pack(anchor="w")
        sub_lbl = ttk.Label(
            header_frame,
            text="Зажатие ЛКМ / ПКМ с фиксацией на окне (Minecraft, игры, программы)",
            style="SubHeader.TLabel"
        )
        sub_lbl.pack(anchor="w")

        # 2. Карточка выбора окна
        win_card = ttk.Frame(container, style="Card.TFrame", padding=12)
        win_card.pack(fill="x", pady=5)

        wc_header = ttk.Frame(win_card, style="Card.TFrame")
        wc_header.pack(fill="x", pady=(0, 6))
        ttk.Label(wc_header, text="🎯 ЦЕЛЕВОЕ ОКНО", font=("Segoe UI", 10, "bold"), style="Card.TLabel").pack(side="left")

        btn_box = ttk.Frame(wc_header, style="Card.TFrame")
        btn_box.pack(side="right")

        btn_pick = tk.Button(
            btn_box, text="🎯 Указать кликом", bg="#374151", fg="white", activebackground="#4b5563",
            activeforeground="white", font=("Segoe UI", 8, "bold"), relief="flat", padx=8, pady=2,
            command=self.start_window_picker
        )
        btn_pick.pack(side="left", padx=3)

        btn_refresh = tk.Button(
            btn_box, text="🔄 Обновить", bg="#374151", fg="white", activebackground="#4b5563",
            activeforeground="white", font=("Segoe UI", 8, "bold"), relief="flat", padx=8, pady=2,
            command=self.refresh_windows_list
        )
        btn_refresh.pack(side="left", padx=3)

        # Поиск
        search_box = ttk.Frame(win_card, style="Card.TFrame")
        search_box.pack(fill="x", pady=(0, 5))
        ttk.Label(search_box, text="Быстрый фильтр:", style="CardSec.TLabel").pack(side="left", padx=(0, 6))
        self.entry_search = tk.Entry(
            search_box, textvariable=self.var_search, bg=self.bg_card_inner, fg="white",
            insertbackground="white", relief="flat", font=("Segoe UI", 9)
        )
        self.entry_search.pack(side="left", fill="x", expand=True)
        self.var_search.trace_add("write", lambda *args: self.filter_windows())

        # Выпадающий список
        self.combo_windows = ttk.Combobox(win_card, state="readonly", font=("Segoe UI", 9))
        self.combo_windows.pack(fill="x", pady=4)
        self.combo_windows.bind("<<ComboboxSelected>>", self.on_window_selected)

        # Информация
        self.lbl_selected_info = ttk.Label(
            win_card, text="Окно не выбрано.", style="CardSec.TLabel"
        )
        self.lbl_selected_info.pack(anchor="w", pady=(2, 0))

        # 3. Карточка статуса
        status_card = ttk.Frame(container, style="Card.TFrame", padding=12)
        status_card.pack(fill="x", pady=6)

        ttk.Label(status_card, text="📊 СТАТУС ЗАЖАТИЯ", font=("Segoe UI", 10, "bold"), style="Card.TLabel").pack(anchor="w")

        self.lbl_status_badge = tk.Label(
            status_card, text="⏸️ ОЖИДАНИЕ (Кнопки не зажаты)", bg="#374151", fg="#e5e7eb",
            font=("Segoe UI", 11, "bold"), pady=8, relief="flat"
        )
        self.lbl_status_badge.pack(fill="x", pady=6)

        timer_box = ttk.Frame(status_card, style="Card.TFrame")
        timer_box.pack(fill="x")
        self.lbl_timer = ttk.Label(timer_box, text="Время зажатия: 00:00:00", font=("Segoe UI", 9), style="CardSec.TLabel")
        self.lbl_timer.pack(side="left")
        self.lbl_hotkeys_hint = ttk.Label(
            timer_box, text="Хоткеи: Alt+ЛКМ (или F6) | Alt+ПКМ (или F7) | F8: Стоп",
            font=("Segoe UI", 9, "bold"), foreground="#60a5fa", background=self.bg_card
        )
        self.lbl_hotkeys_hint.pack(side="right")

        # 4. Кнопки управления
        ctrl_card = ttk.Frame(container, style="Card.TFrame", padding=10)
        ctrl_card.pack(fill="x", pady=4)

        ctrl_grid = ttk.Frame(ctrl_card, style="Card.TFrame")
        ctrl_grid.pack(fill="x")

        self.btn_toggle_lmb = tk.Button(
            ctrl_grid, text="▶ Зажать ЛКМ (Alt+ЛКМ / F6)", bg="#059669", fg="white",
            activebackground="#10b981", activeforeground="white", font=("Segoe UI", 9, "bold"),
            relief="flat", pady=6, command=self.toggle_lmb
        )
        self.btn_toggle_lmb.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.btn_toggle_rmb = tk.Button(
            ctrl_grid, text="▶ Зажать ПКМ (Alt+ПКМ / F7)", bg="#7c3aed", fg="white",
            activebackground="#8b5cf6", activeforeground="white", font=("Segoe UI", 9, "bold"),
            relief="flat", pady=6, command=self.toggle_rmb
        )
        self.btn_toggle_rmb.pack(side="left", fill="x", expand=True, padx=4)

        self.btn_stop_all = tk.Button(
            ctrl_grid, text="⏹ СТОП ВСЁ (F8)", bg="#dc2626", fg="white",
            activebackground="#ef4444", activeforeground="white", font=("Segoe UI", 9, "bold"),
            relief="flat", pady=6, command=self.stop_all
        )
        self.btn_stop_all.pack(side="left", fill="x", expand=True, padx=(4, 0))

        # 5. Режимы работы
        settings_card = ttk.Frame(container, style="Card.TFrame", padding=12)
        settings_card.pack(fill="x", pady=6)

        ttk.Label(settings_card, text="⚙️ РЕЖИМ РАБОТЫ И НАСТРОЙКИ", font=("Segoe UI", 10, "bold"), style="Card.TLabel").pack(anchor="w", pady=(0, 4))

        modes_frame = ttk.Frame(settings_card, style="Card.TFrame")
        modes_frame.pack(fill="x")

        r1 = ttk.Radiobutton(
            modes_frame,
            text="Умная фиксация на окне (Рекомендуется: копает в игре, освобождает мышь при сворачивании)",
            variable=self.var_mode,
            value="smart_lock"
        )
        r1.pack(anchor="w", pady=1)

        r2 = ttk.Radiobutton(
            modes_frame,
            text="Прямой постоянный зажим (Direct Hold: удерживает ЛКМ/ПКМ намертво везде)",
            variable=self.var_mode,
            value="direct_hold"
        )
        r2.pack(anchor="w", pady=1)

        r3 = ttk.Radiobutton(
            modes_frame,
            text="Фоновый режим PostMessage (Отправляет Win32 сообщения без захвата физической мыши)",
            variable=self.var_mode,
            value="background_postmessage"
        )
        r3.pack(anchor="w", pady=1)

        clicker_row = ttk.Frame(modes_frame, style="Card.TFrame")
        clicker_row.pack(fill="x", pady=1)
        r4 = ttk.Radiobutton(
            clicker_row,
            text="Автокликер (Серия быстрых кликов с интервалом:",
            variable=self.var_mode,
            value="clicker"
        )
        r4.pack(side="left")
        entry_int = tk.Entry(
            clicker_row, textvariable=self.var_interval, width=5, bg=self.bg_card_inner,
            fg="white", insertbackground="white", relief="flat", font=("Segoe UI", 9)
        )
        entry_int.pack(side="left", padx=4)
        ttk.Label(clicker_row, text="мс)", style="CardSec.TLabel").pack(side="left")

        # Опции
        chk_frame = ttk.Frame(settings_card, style="Card.TFrame")
        chk_frame.pack(fill="x", pady=(6, 0))

        c_sound = ttk.Checkbutton(chk_frame, text="Звуковой сигнал (Бип)", variable=self.var_sound)
        c_sound.pack(side="left", padx=(0, 14))

        c_auto = ttk.Checkbutton(chk_frame, text="Автозахват активного окна", variable=self.var_autotarget)
        c_auto.pack(side="left", padx=(0, 14))

        c_top = ttk.Checkbutton(chk_frame, text="Поверх всех окон", variable=self.var_ontop, command=self.apply_topmost)
        c_top.pack(side="left")

        # 6. Журнал событий
        log_card = ttk.Frame(container, style="Card.TFrame", padding=10)
        log_card.pack(fill="both", expand=True, pady=6)

        ttk.Label(log_card, text="📜 ЖУРНАЛ ДЕЙСТВИЙ", font=("Segoe UI", 10, "bold"), style="Card.TLabel").pack(anchor="w", pady=(0, 4))

        self.txt_log = tk.Text(
            log_card, height=6, bg="#111116", fg="#d1d5db", relief="flat", font=("Consolas", 9),
            wrap="word", padx=6, pady=4
        )
        self.txt_log.pack(fill="both", expand=True)

        tip_lbl = ttk.Label(
            container,
            text="💡 Хоткеи: Левый Alt + ЛКМ / ПКМ, а также клавиши F6 (ЛКМ), F7 (ПКМ) и F8 (Стоп).",
            style="SubHeader.TLabel"
        )
        tip_lbl.pack(anchor="w", pady=(2, 0))

        self.log("AutoHold Pro готов. Горячие клавиши: Alt + ЛКМ (или F6), Alt + ПКМ (или F7), F8.")

    def log(self, text):
        now_str = time.strftime("%H:%M:%S")
        msg = f"[{now_str}] {text}\n"
        self.txt_log.insert("end", msg)
        self.txt_log.see("end")

    def play_sound(self, on=True):
        if not self.var_sound.get():
            return
        def _snd():
            try:
                if on:
                    winsound.Beep(1200, 100)
                else:
                    winsound.Beep(650, 100)
            except Exception:
                pass
        threading.Thread(target=_snd, daemon=True).start()

    def apply_topmost(self):
        self.root.attributes("-topmost", self.var_ontop.get())

    def refresh_windows_list(self):
        self.windows_cache = get_all_visible_windows()
        self.filter_windows()

        if not self.target_window_data:
            mc_window = None
            for w in self.windows_cache:
                if ("oneblock" in w["title"].lower() or "minecraft" in w["title"].lower()) and "antigravity" not in w["pname"].lower():
                    mc_window = w
                    break

            if mc_window:
                self.target_window_data = mc_window
                self.combo_windows.set(mc_window["display"])
                self.on_window_selected()

    def filter_windows(self):
        query = self.var_search.get().strip().lower()
        if not query:
            filtered = self.windows_cache
        else:
            filtered = [
                w for w in self.windows_cache
                if query in w["title"].lower() or query in w["pname"].lower()
            ]

        display_list = [w["display"] for w in filtered]
        self.combo_windows["values"] = display_list

        if self.target_window_data:
            current_hwnd = self.target_window_data["hwnd"]
            for idx, w in enumerate(filtered):
                if w["hwnd"] == current_hwnd:
                    self.combo_windows.current(idx)
                    return

    def on_window_selected(self, event=None):
        sel_idx = self.combo_windows.current()
        if sel_idx < 0:
            return
        values = self.combo_windows["values"]
        if sel_idx >= len(values):
            return
        display_val = values[sel_idx]

        for w in self.windows_cache:
            if w["display"] == display_val:
                self.target_window_data = w
                break

        if self.target_window_data:
            hwnd = self.target_window_data["hwnd"]
            input_hwnds = find_input_target_hwnds(hwnd)
            target_str = ", ".join([f"{h:#08x}" for h in input_hwnds])
            self.lbl_selected_info.config(
                text=f"Выбрано: {self.target_window_data['display']} (HWND: {hwnd:#08x}, Цель: {target_str})"
            )
            self.log(f"Выбрано целевое окно: {self.target_window_data['display']}")

    def check_and_update_foreground_target(self):
        """Если включен автозахват и мы находимся в другом окне (например Minecraft), фиксируем его"""
        if not self.var_autotarget.get():
            return

        fg_hwnd = user32.GetForegroundWindow()
        if not fg_hwnd:
            return

        my_root = self.root.winfo_id()
        if fg_hwnd == my_root or user32.GetAncestor(fg_hwnd, GA_ROOT) == my_root:
            return

        root_hwnd = user32.GetAncestor(fg_hwnd, GA_ROOT) or fg_hwnd
        if not self.target_window_data or self.target_window_data["hwnd"] != root_hwnd:
            self._apply_picked_window(root_hwnd)

    def start_window_picker(self):
        self.is_picking = True
        self.lbl_selected_info.config(
            text="🎯 Кликните ЛКМ по любому окну на экране, чтобы зафиксировать его...",
            foreground="#fbbf24"
        )
        self.log("Режим пипетки: кликните по нужному окну.")

    def handle_picker_completed(self):
        time.sleep(0.08)
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        val = (int(pt.y) << 32) | (int(pt.x) & 0xFFFFFFFF)
        user32.WindowFromPoint.argtypes = [ctypes.c_uint64]
        user32.WindowFromPoint.restype = wintypes.HWND
        hwnd_under = user32.WindowFromPoint(val)

        if not hwnd_under:
            return

        root_hwnd = user32.GetAncestor(hwnd_under, GA_ROOT) or hwnd_under
        self._apply_picked_window(root_hwnd)

    def _apply_picked_window(self, hwnd):
        self.refresh_windows_list()
        matched = None
        for w in self.windows_cache:
            if w["hwnd"] == hwnd:
                matched = w
                break

        if not matched:
            title = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, title, 512)
            pname = get_process_name_by_hwnd(hwnd)
            matched = {
                "hwnd": hwnd,
                "title": title.value.strip() or "Без названия",
                "pname": pname,
                "display": f"[{pname}] {title.value.strip() or 'Без названия'}"
            }
            self.windows_cache.insert(0, matched)
            self.combo_windows["values"] = [w["display"] for w in self.windows_cache]

        self.target_window_data = matched
        self.combo_windows.set(matched["display"])
        self.on_window_selected()
        self.lbl_selected_info.config(foreground=self.text_secondary)
        self.log(f"Окно зафиксировано: {matched['display']}")

    # --- Управление зажатием ---
    def toggle_lmb(self):
        # Дебаунс 250мс для предотвращения повторного срабатывания
        now = time.time()
        if now - self.last_lmb_toggle < 0.25:
            return
        self.last_lmb_toggle = now

        self.check_and_update_foreground_target()

        with self.lock:
            if self.lmb_held:
                self._stop_lmb()
            else:
                self._start_lmb()
        self.update_ui_state()

    def toggle_rmb(self):
        now = time.time()
        if now - self.last_rmb_toggle < 0.25:
            return
        self.last_rmb_toggle = now

        self.check_and_update_foreground_target()

        with self.lock:
            if self.rmb_held:
                self._stop_rmb()
            else:
                self._start_rmb()
        self.update_ui_state()

    def _start_lmb(self):
        if not self.target_window_data:
            self.log("⚠️ Не выбрано целевое окно!")
            return

        self.lmb_held = True
        if not self.rmb_held:
            self.hold_start_time = time.time()

        self.play_sound(on=True)
        self.log(f"🟢 [ХОТКЕЙ] ЗАЖАТА ЛКМ на окне: {self.target_window_data['display']}")
        self.ensure_worker_running()

    def _stop_lmb(self):
        if not self.lmb_held:
            return
        self.lmb_held = False
        self.play_sound(on=False)
        self.log("⚪ [ХОТКЕЙ] Отпущена ЛКМ")

        self.release_hardware_lmb()
        self.send_postmessage_up("LMB")

        if not self.lmb_held and not self.rmb_held:
            self.hold_start_time = None

    def _start_rmb(self):
        if not self.target_window_data:
            self.log("⚠️ Не выбрано целевое окно!")
            return

        self.rmb_held = True
        if not self.lmb_held:
            self.hold_start_time = time.time()

        self.play_sound(on=True)
        self.log(f"🟣 [ХОТКЕЙ] ЗАЖАТА ПКМ на окне: {self.target_window_data['display']}")
        self.ensure_worker_running()

    def _stop_rmb(self):
        if not self.rmb_held:
            return
        self.rmb_held = False
        self.play_sound(on=False)
        self.log("⚪ [ХОТКЕЙ] Отпущена ПКМ")

        self.release_hardware_rmb()
        self.send_postmessage_up("RMB")

        if not self.lmb_held and not self.rmb_held:
            self.hold_start_time = None

    def stop_all(self):
        with self.lock:
            was_active = self.lmb_held or self.rmb_held
            self.lmb_held = False
            self.rmb_held = False
            self.hold_start_time = None

            self.release_hardware_lmb()
            self.release_hardware_rmb()
            self.send_postmessage_up("LMB")
            self.send_postmessage_up("RMB")

            if was_active:
                self.play_sound(on=False)
                self.log("🛑 ВСЕ ЗАЖАТИЯ ОСТАНОВЛЕНЫ (F8)")
        self.update_ui_state()

    def release_hardware_lmb(self):
        if self.physical_lmb_down:
            user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            self.physical_lmb_down = False

    def release_hardware_rmb(self):
        if self.physical_rmb_down:
            user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
            self.physical_rmb_down = False

    def press_hardware_lmb(self):
        if not self.physical_lmb_down:
            user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            self.physical_lmb_down = True

    def press_hardware_rmb(self):
        if not self.physical_rmb_down:
            user32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
            self.physical_rmb_down = True

    def send_postmessage_up(self, button):
        if not self.target_window_data:
            return
        top_hwnd = self.target_window_data["hwnd"]
        hwnds = find_input_target_hwnds(top_hwnd)
        msg = WM_LBUTTONUP if button == "LMB" else WM_RBUTTONUP

        for h in hwnds:
            rect = wintypes.RECT()
            user32.GetClientRect(h, ctypes.byref(rect))
            cx = max(1, (rect.right - rect.left) // 2)
            cy = max(1, (rect.bottom - rect.top) // 2)
            lparam = (cy << 16) | (cx & 0xFFFF)
            user32.PostMessageW(h, msg, 0, lparam)

    def ensure_worker_running(self):
        if not self.worker_running:
            self.worker_running = True
            self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
            self.worker_thread.start()

    def _worker_loop(self):
        """Главный цикл зажатия"""
        while self.worker_running:
            with self.lock:
                l_down = self.lmb_held
                r_down = self.rmb_held
                mode = self.var_mode.get()
                target_hwnd = self.target_window_data["hwnd"] if self.target_window_data else None

            if not l_down and not r_down:
                break

            fg_hwnd = user32.GetForegroundWindow()
            is_target_focused = (
                fg_hwnd == target_hwnd or
                (target_hwnd and user32.GetAncestor(fg_hwnd, GA_ROOT) == target_hwnd)
            )

            # РЕЖИМ 1: Умная фиксация на окне
            if mode == "smart_lock":
                if is_target_focused:
                    # В окне игры: физический зажим мыши
                    if l_down:
                        self.press_hardware_lmb()
                    if r_down:
                        self.press_hardware_rmb()
                else:
                    # В другом окне: отпускаем мышь для пользователя
                    self.release_hardware_lmb()
                    self.release_hardware_rmb()

                    if target_hwnd:
                        hwnds = find_input_target_hwnds(target_hwnd)
                        wparam = (MK_LBUTTON if l_down else 0) | (MK_RBUTTON if r_down else 0)
                        for h in hwnds:
                            rect = wintypes.RECT()
                            user32.GetClientRect(h, ctypes.byref(rect))
                            cx = max(1, (rect.right - rect.left) // 2)
                            cy = max(1, (rect.bottom - rect.top) // 2)
                            lparam = (cy << 16) | (cx & 0xFFFF)
                            user32.PostMessageW(h, WM_MOUSEMOVE, wparam, lparam)
                time.sleep(0.04)

            # РЕЖИМ 2: Прямой постоянный зажим
            elif mode == "direct_hold":
                if l_down:
                    self.press_hardware_lmb()
                if r_down:
                    self.press_hardware_rmb()
                time.sleep(0.04)

            # РЕЖИМ 3: Фоновый PostMessage
            elif mode == "background_postmessage":
                self.release_hardware_lmb()
                self.release_hardware_rmb()
                if target_hwnd:
                    hwnds = find_input_target_hwnds(target_hwnd)
                    for h in hwnds:
                        rect = wintypes.RECT()
                        user32.GetClientRect(h, ctypes.byref(rect))
                        cx = max(1, (rect.right - rect.left) // 2)
                        cy = max(1, (rect.bottom - rect.top) // 2)
                        lparam = (cy << 16) | (cx & 0xFFFF)
                        if l_down:
                            user32.PostMessageW(h, WM_LBUTTONDOWN, MK_LBUTTON, lparam)
                        if r_down:
                            user32.PostMessageW(h, WM_RBUTTONDOWN, MK_RBUTTON, lparam)
                time.sleep(0.08)

            # РЕЖИМ 4: Автокликер
            elif mode == "clicker":
                try:
                    interval_sec = max(0.01, float(self.var_interval.get()) / 1000.0)
                except Exception:
                    interval_sec = 0.05

                if is_target_focused:
                    if l_down:
                        user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                        time.sleep(0.005)
                        user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                    if r_down:
                        user32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
                        time.sleep(0.005)
                        user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
                elif target_hwnd:
                    hwnds = find_input_target_hwnds(target_hwnd)
                    for h in hwnds:
                        rect = wintypes.RECT()
                        user32.GetClientRect(h, ctypes.byref(rect))
                        cx = max(1, (rect.right - rect.left) // 2)
                        cy = max(1, (rect.bottom - rect.top) // 2)
                        lparam = (cy << 16) | (cx & 0xFFFF)
                        if l_down:
                            user32.PostMessageW(h, WM_LBUTTONDOWN, MK_LBUTTON, lparam)
                            time.sleep(0.005)
                            user32.PostMessageW(h, WM_LBUTTONUP, 0, lparam)
                        if r_down:
                            user32.PostMessageW(h, WM_RBUTTONDOWN, MK_RBUTTON, lparam)
                            time.sleep(0.005)
                            user32.PostMessageW(h, WM_RBUTTONUP, 0, lparam)

                time.sleep(interval_sec)

        self.release_hardware_lmb()
        self.release_hardware_rmb()
        self.worker_running = False

    def update_ui_state(self):
        if self.lmb_held and self.rmb_held:
            self.lbl_status_badge.config(
                text="⚡ ЛКМ + ПКМ ЗАЖАТЫ (АКТИВНО)", bg="#d97706", fg="white"
            )
            self.btn_toggle_lmb.config(text="⏹ Отпустить ЛКМ", bg="#b91c1c")
            self.btn_toggle_rmb.config(text="⏹ Отпустить ПКМ", bg="#b91c1c")
        elif self.lmb_held:
            self.lbl_status_badge.config(
                text="🟢 ЛКМ ЗАЖАТА (Левая кнопка удерживается)", bg="#059669", fg="white"
            )
            self.btn_toggle_lmb.config(text="⏹ Отпустить ЛКМ", bg="#b91c1c")
            self.btn_toggle_rmb.config(text="▶ Зажать ПКМ (Alt+ПКМ / F7)", bg="#7c3aed")
        elif self.rmb_held:
            self.lbl_status_badge.config(
                text="🟣 ПКМ ЗАЖАТА (Правая кнопка удерживается)", bg="#7c3aed", fg="white"
            )
            self.btn_toggle_lmb.config(text="▶ Зажать ЛКМ (Alt+ЛКМ / F6)", bg="#059669")
            self.btn_toggle_rmb.config(text="⏹ Отпустить ПКМ", bg="#b91c1c")
        else:
            self.lbl_status_badge.config(
                text="⏸️ ОЖИДАНИЕ (Кнопки не зажаты)", bg="#374151", fg="#e5e7eb"
            )
            self.btn_toggle_lmb.config(text="▶ Зажать ЛКМ (Alt+ЛКМ / F6)", bg="#059669")
            self.btn_toggle_rmb.config(text="▶ Зажать ПКМ (Alt+ПКМ / F7)", bg="#7c3aed")

    def update_ui_timer(self):
        if self.hold_start_time and (self.lmb_held or self.rmb_held):
            elapsed = int(time.time() - self.hold_start_time)
            hrs = elapsed // 3600
            mins = (elapsed % 3600) // 60
            secs = elapsed % 60
            self.lbl_timer.config(text=f"Время зажатия: {hrs:02d}:{mins:02d}:{secs:02d}")
        else:
            self.lbl_timer.config(text="Время зажатия: 00:00:00")

        self.root.after(200, self.update_ui_timer)

    def on_close(self):
        self.stop_all()
        self.hotkey_poller_running = False
        try:
            self.kb_listener.stop()
        except Exception:
            pass
        try:
            self.mouse_listener.stop()
        except Exception:
            pass
        self.root.destroy()


def main():
    root = tk.Tk()
    app = AutoHoldApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

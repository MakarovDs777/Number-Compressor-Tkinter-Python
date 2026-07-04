import tkinter as tk
from tkinter import filedialog, messagebox
import numpy as np
from PIL import Image, ImageTk
import os
import re

# Глобальные переменные
image_data = None
canvas_img_refs = []  # ссылки на PhotoImage чтобы не удалялись
current_width = None
current_height = None


# ============================================================
#  СЖАТИЕ / РАЗЖАТИЕ — «кортежный» формат
# ============================================================
#
#  Идея:
#    Вход:  числа через пробел, например:
#           "252 1 253 5 128 3"
#
#    Сжатие:
#      - Многозначные (>9) остаются как есть.
#      - Однозначные (0–9) заменяются на Q0..Q9,
#        а пробел ПЕРЕД таким числом удаляется.
#      - Результат — сплошная строка без пробелов:
#           "252Q1253Q5128Q3"
#
#    Разжатие:
#      - "252Q1253Q5128Q3" -> "252 1 253 5 128 3"
# ============================================================

# Таблицы кодирования
DIGIT_TO_Q = {0: "Q0", 1: "Q1", 2: "Q2", 3: "Q3", 4: "Q4",
              5: "Q5", 6: "Q6", 7: "Q7", 8: "Q8", 9: "Q9"}

Q_TO_DIGIT = {v: k for k, v in DIGIT_TO_Q.items()}


def parse_space_numbers(text: str):
    """
    Разбирает строку чисел, разделённых пробелами / переносами строк.
    Возвращает список int.
    """
    nums = []
    for token in text.split():
        token = token.strip()
        if not token:
            continue
        try:
            nums.append(int(token))
        except ValueError:
            raise ValueError(f"Не число: '{token}'")
    return nums


def compress_to_compact(numbers: list):
    """
    [252, 1, 253, 5, 128, 3]  ->  "252Q1253Q5128Q3"

    Каждое однозначное число заменяется на Q-код,
    многозначное — остаётся строкой. Всё сливается без пробелов.
    """
    parts = []
    for n in numbers:
        if 0 <= n <= 9:
            parts.append(DIGIT_TO_Q[n])
        else:
            parts.append(str(n))
    return "".join(parts)


def decompact_to_numbers(compact: str):
    """
    "252Q1253Q5128Q3"  ->  [252, 1, 253, 5, 128, 3]
    """
    nums = []
    i = 0
    n = len(compact)

    while i < n:
        ch = compact[i]

        # Проверяем двухсимвольный код Qx
        if ch == "Q" and i + 1 < n:
            code = "Q" + compact[i + 1]
            if code in Q_TO_DIGIT:
                nums.append(Q_TO_DIGIT[code])
                i += 2
                continue

        # Иначе читаем обычное число (может начинаться с минуса)
        j = i
        if compact[j] == "-":
            j += 1
        while j < n and compact[j].isdigit():
            j += 1
        if j == i:
            raise ValueError(f"Неожиданный символ в позиции {i}: '{compact[i]}'")
        nums.append(int(compact[i:j]))
        i = j

    return nums


# ============================================================
#  БУФЕР ОБМЕНА / КОНТЕКСТНОЕ МЕНЮ
# ============================================================

def setup_clipboard_bindings(widget):
    """Ctrl+C/V/X/A, Command+C/V/X/A, контекстное меню."""

    def gen(event_name):
        return lambda e: (widget.event_generate(event_name), "break")

    widget.bind("<Control-c>", gen("<<Copy>>"))
    widget.bind("<Control-x>", gen("<<Cut>>"))
    widget.bind("<Control-v>", gen("<<Paste>>"))
    widget.bind("<Control-a>", lambda e: (widget.tag_add("sel", "1.0", "end"), "break"))

    widget.bind("<Command-c>", gen("<<Copy>>"))
    widget.bind("<Command-x>", gen("<<Cut>>"))
    widget.bind("<Command-v>", gen("<<Paste>>"))
    widget.bind("<Command-a>", lambda e: (widget.tag_add("sel", "1.0", "end"), "break"))

    widget.bind("<Button-1>", lambda e: widget.focus_set())

    menu = tk.Menu(widget, tearoff=0)
    menu.add_command(label="Копировать", command=lambda: widget.event_generate("<<Copy>>"))
    menu.add_command(label="Вставить", command=lambda: widget.event_generate("<<Paste>>"))
    menu.add_command(label="Вырезать", command=lambda: widget.event_generate("<<Cut>>"))
    menu.add_separator()
    menu.add_command(label="Выделить всё", command=lambda: widget.tag_add("sel", "1.0", "end"))

    def show_menu(event):
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    widget.bind("<Button-3>", show_menu)
    widget.bind("<Button-2>", show_menu)


# ============================================================
#  РАБОТА С ИЗОБРАЖЕНИЯМИ
# ============================================================

def load_image():
    """Открыть файл изображения, показать и заполнить табло числами через пробел."""
    global image_data, current_width, current_height
    path = filedialog.askopenfilename(
        filetypes=[("Image files", "*.png;*.jpg;*.jpeg;*.bmp;*.gif"), ("All files", "*.*")]
    )
    if not path:
        return
    try:
        img = Image.open(path).convert("RGB")
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось открыть изображение: {e}")
        return

    image_data = np.array(img)
    current_height, current_width = image_data.shape[:2]
    width_var.set(str(current_width))

    # Показать изображение
    win = tk.Toplevel(root)
    win.title(f"Изображение — {os.path.basename(path)}")
    canvas = tk.Canvas(win, width=img.width, height=img.height)
    canvas.pack()
    photo = ImageTk.PhotoImage(img)
    canvas.create_image(0, 0, anchor=tk.NW, image=photo)
    canvas_img_refs.append(photo)

    # Заполнить табло числами через пробел
    fill_text_from_array(image_data)


def fill_text_from_array(arr):
    """arr (H,W,3) -> текст: 'R G B R G B ...' (row-major)."""
    h, w = arr.shape[:2]
    total = h * w
    if total > 500_000:
        if not messagebox.askyesno(
            "Большое изображение",
            f"{total} пикселей ({total * 3} чисел). Может тормозить. Продолжить?",
        ):
            return

    flat = []
    for row in arr:
        for px in row:
            flat.extend([int(px[0]), int(px[1]), int(px[2])])

    text_widget.config(state="normal")
    text_widget.delete("1.0", tk.END)
    text_widget.insert("1.0", " ".join(str(v) for v in flat))


def open_image_from_text():
    """Парсит числа из табло и показывает изображение."""
    txt = text_widget.get("1.0", tk.END)

    # Пробуем распознать: либо обычные числа через пробел, либо сжатый формат
    stripped = txt.strip()
    if "Q" in stripped and " " not in stripped:
        # Похоже на сжатый формат — разжимаем
        try:
            numbers = decompact_to_numbers(stripped)
        except ValueError as e:
            messagebox.showerror("Ошибка распаковки", str(e))
            return
    else:
        try:
            numbers = parse_space_numbers(txt)
        except ValueError as e:
            messagebox.showerror("Ошибка парсинга", str(e))
            return

    # Собираем триплеты
    if len(numbers) % 3 != 0:
        messagebox.showerror(
            "Ошибка",
            f"Количество чисел ({len(numbers)}) не кратно 3. Нужны триплеты R G B.",
        )
        return

    pixels = []
    for i in range(0, len(numbers), 3):
        r, g, b = numbers[i], numbers[i + 1], numbers[i + 2]
        for v in (r, g, b):
            if v < 0 or v > 255:
                messagebox.showerror(
                    "Ошибка", f"Значение {v} вне диапазона 0–255 (триплет {i // 3 + 1})."
                )
                return
        pixels.append([r, g, b])

    # Ширина
    w_text = width_var.get().strip()
    if w_text:
        try:
            w = int(w_text)
            if w <= 0:
                raise ValueError()
        except:
            messagebox.showerror("Ошибка", "Ширина должна быть положительным целым числом.")
            return
    else:
        n = len(pixels)
        sq = int(np.sqrt(n))
        if sq * sq == n:
            w = sq
        else:
            messagebox.showinfo(
                "Уточнение",
                "Ширина не указана и количество пикселей не является квадратом. Укажите ширину.",
            )
            return

    if len(pixels) % w != 0:
        messagebox.showerror(
            "Ошибка",
            f"Количество пикселей ({len(pixels)}) не делится на ширину ({w}).",
        )
        return

    arr = np.array(pixels, dtype=np.uint8)
    h = arr.shape[0] // w
    arr = arr.reshape((h, w, 3))
    img = Image.fromarray(arr)

    win = tk.Toplevel(root)
    win.title("Изображение из RGB")
    canvas = tk.Canvas(win, width=img.width, height=img.height)
    canvas.pack()
    photo = ImageTk.PhotoImage(img)
    canvas.create_image(0, 0, anchor=tk.NW, image=photo)
    canvas_img_refs.append(photo)


# ============================================================
#  КНОПКИ
# ============================================================

def clear_text():
    text_widget.config(state="normal")
    text_widget.delete("1.0", tk.END)


def save_text():
    txt = text_widget.get("1.0", tk.END).strip()
    if not txt:
        messagebox.showwarning("Пусто", "Нечего сохранять.")
        return
    path = filedialog.asksaveasfilename(
        defaultextension=".txt",
        filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        title="Сохранить как...",
    )
    if not path:
        return
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(txt)
        messagebox.showinfo("Сохранено", f"Файл сохранён:\n{path}")
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось сохранить:\n{e}")


def do_compress():
    """Сжать: числа через пробел -> компактный кортежный формат."""
    txt = text_widget.get("1.0", tk.END).strip()
    if not txt:
        messagebox.showwarning("Пусто", "Нечего сжимать.")
        return
    try:
        nums = parse_space_numbers(txt)
    except ValueError as e:
        messagebox.showerror("Ошибка", str(e))
        return

    result = compress_to_compact(nums)

    text_widget.config(state="normal")
    text_widget.delete("1.0", tk.END)
    text_widget.insert("1.0", result)


def do_decompress():
    """Разжать: кортежный формат -> числа через пробел."""
    txt = text_widget.get("1.0", tk.END).strip()
    if not txt:
        messagebox.showwarning("Пусто", "Нечего разжимать.")
        return
    try:
        nums = decompact_to_numbers(txt)
    except ValueError as e:
        messagebox.showerror("Ошибка", str(e))
        return

    result = " ".join(str(n) for n in nums)

    text_widget.config(state="normal")
    text_widget.delete("1.0", tk.END)
    text_widget.insert("1.0", result)


def split_image_to_rgb_lents():
    """
    Выбирает изображение, нарезает на ленты шириной lent_width,
    сохраняет в RGB_Lents на рабочем столе:
      Lent_1.txt — R, Lent_2.txt — G, Lent_3.txt — B.
    """
    path = filedialog.askopenfilename(
        filetypes=[("Image files", "*.png;*.jpg;*.jpeg;*.bmp;*.gif"), ("All files", "*.*")],
        title="Выберите изображение для разделения на RGB-ленты",
    )
    if not path:
        return

    try:
        img = Image.open(path).convert("RGB")
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось открыть изображение: {e}")
        return

    arr = np.array(img)
    img_h, img_w = arr.shape[:2]

    w_str = width_var.get().strip()
    if not w_str:
        messagebox.showerror("Ошибка", "Укажите ширину ленты.")
        return
    try:
        lent_width = int(w_str)
        if lent_width <= 0:
            raise ValueError()
    except:
        messagebox.showerror("Ошибка", "Ширина ленты — положительное целое число.")
        return

    if img_w % lent_width != 0:
        messagebox.showerror(
            "Ошибка",
            f"Ширина изображения ({img_w}) не делится на ширину ленты ({lent_width}).",
        )
        return

    r_vals, g_vals, b_vals = [], [], []
    blocks_per_row = img_w // lent_width

    for row_idx in range(img_h):
        for block_idx in range(blocks_per_row):
            sc = block_idx * lent_width
            ec = sc + lent_width
            block = arr[row_idx, sc:ec, :]
            for px in block:
                r_vals.append(int(px[0]))
                g_vals.append(int(px[1]))
                b_vals.append(int(px[2]))

    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    save_dir = os.path.join(desktop, "RGB_Lents")
    os.makedirs(save_dir, exist_ok=True)

    for fname, values in [
        ("Lent_1.txt", r_vals),
        ("Lent_2.txt", g_vals),
        ("Lent_3.txt", b_vals),
    ]:
        with open(os.path.join(save_dir, fname), "w", encoding="utf-8") as f:
            f.write("\n".join(str(v) for v in values))

    messagebox.showinfo(
        "Готово",
        f"Файлы сохранены в:\n{save_dir}\n\n"
        f"Lent_1.txt — R\nLent_2.txt — G\nLent_3.txt — B\n"
        f"Значений в каждом: {len(r_vals)}\nШирина ленты: {lent_width} px",
    )


# ============================================================
#  GUI
# ============================================================

root = tk.Tk()
root.title("RGB редактор — кортежное сжатие")
root.geometry("950x700")

top_frame = tk.Frame(root)
top_frame.pack(fill=tk.X, padx=8, pady=6)

# --- Ряд 1: основные кнопки ---
row1 = tk.Frame(top_frame)
row1.pack(fill=tk.X)

tk.Button(row1, text="Загрузить изображение", command=load_image).pack(side=tk.LEFT, padx=(0, 6))
tk.Label(row1, text="Ширина (px):").pack(side=tk.LEFT)
width_var = tk.StringVar()
tk.Entry(row1, textvariable=width_var, width=8).pack(side=tk.LEFT, padx=(4, 12))
tk.Button(row1, text="Открыть изображение", command=open_image_from_text).pack(side=tk.LEFT, padx=(0, 6))
tk.Button(row1, text="Очистить", command=clear_text).pack(side=tk.LEFT, padx=(0, 6))
tk.Button(row1, text="Сохранить .txt", command=save_text).pack(side=tk.LEFT, padx=(0, 12))

# --- Сжатие / Разжатие (выделены визуально) ---
tk.Button(row1, text="▶ Сжать (в Q-кортеж)", command=do_compress,
          bg="#e0e0ff").pack(side=tk.LEFT, padx=(0, 6))
tk.Button(row1, text="◀ Разжать (из Q-кортежа)", command=do_decompress,
          bg="#ffe0e0").pack(side=tk.LEFT, padx=(0, 6))

# --- Ряд 2: ленты ---
row2 = tk.Frame(top_frame)
row2.pack(fill=tk.X, pady=(6, 0))
tk.Button(row2, text="Разделить на RGB-ленты", command=split_image_to_rgb_lents).pack(side=tk.LEFT)

# --- Текстовая область ---
text_frame = tk.Frame(root)
text_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

text_widget = tk.Text(text_frame, wrap=tk.NONE, font=("Consolas", 11))
yscroll = tk.Scrollbar(text_frame, orient=tk.VERTICAL, command=text_widget.yview)
xscroll = tk.Scrollbar(text_frame, orient=tk.HORIZONTAL, command=text_widget.xview)
text_widget.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
yscroll.pack(side=tk.RIGHT, fill=tk.Y)
xscroll.pack(side=tk.BOTTOM, fill=tk.X)
text_widget.pack(fill=tk.BOTH, expand=True)

setup_clipboard_bindings(text_widget)

# --- Подсказка ---
tk.Label(
    root,
    text=(
        "Формат ввода: числа через пробел (R G B R G B ...).\n"
        "«Сжать» — однозначные (0–9) → Q0..Q9, пробелы убираются. Пример: 252 1 5 → 252Q1Q5\n"
        "«Разжать» — обратно: 252Q1Q5 → 252 1 5\n"
        "Если поле «Ширина» пустое — пытаемся подобрать квадрат."
    ),
    anchor="w",
    justify="left",
).pack(fill=tk.X, padx=8, pady=(0, 8))

root.mainloop()

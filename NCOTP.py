
import tkinter as tk
from tkinter import filedialog, messagebox
import numpy as np
from PIL import Image, ImageTk
import os

# Глобальные переменные
image_data = None
canvas_img_refs = []  # ссылки на PhotoImage чтобы не удалялись
current_width = None
current_height = None


# ------------------------------------------------------------
#  КОДИРОВАНИЕ / ДЕКОДИРОВАНИЕ  (кортежный формат)
# ------------------------------------------------------------

# Таблица для однозначных чисел 0..9
DIGIT_TO_CODE = {
    0: "Q0", 1: "Q1", 2: "Q2", 3: "Q3", 4: "Q4",
    5: "Q5", 6: "Q6", 7: "Q7", 8: "Q8", 9: "Q9",
}

# Обратная таблица: "Q0" -> 0, "Q1" -> 1, ...
CODE_TO_DIGIT = {v: k for k, v in DIGIT_TO_CODE.items()}


def parse_space_separated_numbers(text: str):
    """
    Разбирает входной текст: числа, разделённые пробелами и/или переносами строк.
    Возвращает список целых чисел.
    Пример: "252 1 253 5 128 3" -> [252, 1, 253, 5, 128, 3]
    """
    numbers = []
    for token in text.split():
        token = token.strip()
        if not token:
            continue
        try:
            numbers.append(int(token))
        except ValueError:
            raise ValueError(f"Не удалось распознать число: '{token}'")
    return numbers


def encode_compact(numbers: list):
    """
    Кодирует список чисел в компактную «кортежную» строку:
      - многозначные (>9)       — как есть
      - однозначные  (0..9)     — Q0..Q9
    Всё слитно, без пробелов.
    Пример: [252, 1, 253, 5, 128, 3] -> "252Q1253Q5128Q3"
    """
    parts = []
    for n in numbers:
        if 0 <= n <= 9:
            parts.append(DIGIT_TO_CODE[n])
        else:
            parts.append(str(n))
    return "".join(parts)


def decode_compact(compact: str):
    """
    Обратное преобразование: "252Q1253Q5128Q3" -> [252, 1, 253, 5, 128, 3]
    """
    numbers = []
    i = 0
    n = len(compact)

    while i < n:
        ch = compact[i]

        # Проверяем, не начинается ли с "Q" двухсимвольный код
        if ch == "Q" and i + 1 < n:
            code = "Q" + compact[i + 1]
            if code in CODE_TO_DIGIT:
                numbers.append(CODE_TO_DIGIT[code])
                i += 2
                continue

        # Иначе читаем многозначное число (возможно отрицательное)
        j = i
        if compact[j] == "-":
            j += 1
        while j < n and compact[j].isdigit():
            j += 1
        if j == i:
            raise ValueError(f"Неожиданный символ в позиции {i}: '{compact[i]}'")
        numbers.append(int(compact[i:j]))
        i = j

    return numbers


# ------------------------------------------------------------
#  БУФЕР ОБМЕНА / КОНТЕКСТНОЕ МЕНЮ
# ------------------------------------------------------------

def setup_clipboard_bindings(widget):
    """Настроить привязки для копирования/вставки/вырезания и SelectAll."""

    def gen(event_name):
        return lambda e: (widget.event_generate(event_name), "break")

    # Windows/Linux: Ctrl
    widget.bind("<Control-c>", gen("<<Copy>>"))
    widget.bind("<Control-x>", gen("<<Cut>>"))
    widget.bind("<Control-v>", gen("<<Paste>>"))
    widget.bind("<Control-a>", lambda e: (widget.tag_add("sel", "1.0", "end"), "break"))

    # macOS: Command
    widget.bind("<Command-c>", gen("<<Copy>>"))
    widget.bind("<Command-x>", gen("<<Cut>>"))
    widget.bind("<Command-v>", gen("<<Paste>>"))
    widget.bind("<Command-a>", lambda e: (widget.tag_add("sel", "1.0", "end"), "break"))

    # При клике — ставим фокус в виджет
    widget.bind("<Button-1>", lambda e: widget.focus_set())

    # Контекстное меню (правый клик)
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

    widget.bind("<Button-3>", show_menu)  # Windows/Linux
    widget.bind("<Button-2>", show_menu)  # macOS


# ------------------------------------------------------------
#  РАБОТА С ИЗОБРАЖЕНИЯМИ
# ------------------------------------------------------------

def load_image():
    """Открывает файл изображения, показывает его и заполняет табло RGB."""
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

    # Показать изображение в новом окне
    win = tk.Toplevel(root)
    win.title(f"Изображение — {path.split('/')[-1]}")
    canvas = tk.Canvas(win, width=img.width, height=img.height)
    canvas.pack()
    photo = ImageTk.PhotoImage(img)
    canvas.create_image(0, 0, anchor=tk.NW, image=photo)
    canvas_img_refs.append(photo)

    # Заполнить текстовое поле числами через пробел
    fill_text_from_image(image_data)


def fill_text_from_image(arr):
    """Заполняет text_widget числами из массива arr (h,w,3) — подряд через пробел."""
    h, w = arr.shape[:2]

    max_cells_warn = 500000
    total = h * w
    if total > max_cells_warn:
        if not messagebox.askyesno(
            "Большое изображение",
            f"Изображение содержит {total} пикселей ({total * 3} чисел). Это может замедлить интерфейс. Продолжить?",
        ):
            return

    # Собираем все числа подряд (row-major): R G B R G B ...
    flat = []
    for row in arr:
        for px in row:
            flat.extend([int(px[0]), int(px[1]), int(px[2])])

    text_widget.config(state="normal")
    text_widget.delete("1.0", tk.END)
    text_widget.insert("1.0", " ".join(str(v) for v in flat))
    # Оставляем текст доступным для редактирования


def parse_rgb_text(text):
    """
    Парсит текст с RGB-числами (через пробелы) и возвращает список [R,G,B] триплетов.
    """
    numbers = parse_space_separated_numbers(text)

    if len(numbers) % 3 != 0:
        raise ValueError(
            f"Количество чисел ({len(numbers)}) не кратно 3. "
            f"Каждый пиксель требует три значения R, G, B."
        )

    pixels = []
    for i in range(0, len(numbers), 3):
        r, g, b = numbers[i], numbers[i + 1], numbers[i + 2]
        for v in (r, g, b):
            if v < 0 or v > 255:
                raise ValueError(f"Пиксель {i // 3 + 1}: значение {v} вне диапазона 0–255")
        pixels.append([r, g, b])

    if not pixels:
        raise ValueError("Не найдено ни одного RGB-триплета.")
    return pixels


def open_image_from_text():
    """Парсит текст в табло и открывает окно с изображением на его основании."""
    txt = text_widget.get("1.0", tk.END)
    try:
        pixels = parse_rgb_text(txt)
    except ValueError as e:
        messagebox.showerror("Ошибка парсинга", str(e))
        return

    w_text = width_var.get().strip()
    if w_text:
        try:
            w = int(w_text)
            if w <= 0:
                raise ValueError()
        except:
            messagebox.showerror("Ошибка", "Поле ширины должно содержать положительное целое число.")
            return
    else:
        n = len(pixels)
        sq = int(np.sqrt(n))
        if sq * sq == n:
            w = sq
        else:
            messagebox.showinfo(
                "Уточнение",
                "Ширина не указана и длина не является квадратом. Пожалуйста, укажите ширину.",
            )
            return

    if len(pixels) % w != 0:
        messagebox.showerror(
            "Ошибка", f"Количество пикселей ({len(pixels)}) не делится на указанную ширину ({w})."
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


# ------------------------------------------------------------
#  КНОПКИ ОБРАБОТКИ ТЕКСТА
# ------------------------------------------------------------

def clear_text():
    text_widget.config(state="normal")
    text_widget.delete("1.0", tk.END)


def save_text_to_file():
    """Сохраняет содержимое текстового поля в выбранный файл (.txt)."""
    txt = text_widget.get("1.0", tk.END).strip()
    if not txt:
        messagebox.showwarning("Пусто", "Нечего сохранять — текстовое поле пусто.")
        return

    file_path = filedialog.asksaveasfilename(
        defaultextension=".txt",
        filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        title="Сохранить данные как...",
    )
    if not file_path:
        return

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(txt)
        messagebox.showinfo("Сохранено", f"Файл сохранён:\n{file_path}")
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось сохранить файл:\n{e}")


def compress_to_compact():
    """
    Сжимает содержимое текстового поля:
    числа через пробел -> компактный кортежный формат (без пробелов).
    """
    txt = text_widget.get("1.0", tk.END).strip()
    if not txt:
        messagebox.showwarning("Пусто", "Нечего сжимать — текстовое поле пусто.")
        return

    try:
        numbers = parse_space_separated_numbers(txt)
    except ValueError as e:
        messagebox.showerror("Ошибка парсинга", str(e))
        return

    compact = encode_compact(numbers)

    text_widget.config(state="normal")
    text_widget.delete("1.0", tk.END)
    text_widget.insert("1.0", compact)


def decompress_from_compact():
    """
    Разжимает компактный кортежный формат обратно в числа через пробел.
    """
    txt = text_widget.get("1.0", tk.END).strip()
    if not txt:
        messagebox.showwarning("Пусто", "Нечего разжимать — текстовое поле пусто.")
        return

    try:
        numbers = decode_compact(txt)
    except ValueError as e:
        messagebox.showerror("Ошибка распаковки", str(e))
        return

    plain = " ".join(str(n) for n in numbers)

    text_widget.config(state="normal")
    text_widget.delete("1.0", tk.END)
    text_widget.insert("1.0", plain)


def split_image_to_rgb_lents():
    """
    Выбирает изображение, нарезает его на ленты указанной ширины (по горизонтали,
    row-major), затем сохраняет на рабочий стол в папку 'RGB_Lents' три .txt файла:
    - Lent_1.txt: каждый 1-й индекс (R)
    - Lent_2.txt: каждый 2-й индекс (G)
    - Lent_3.txt: каждый 3-й индекс (B)

    Порядок обхода пикселей: строка за строкой, слева направо.
    Если ширина ленты меньше ширины изображения — строки режутся на несколько лент,
    которые выкладываются последовательно одна за другой.
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

    width_str = width_var.get().strip()
    if not width_str:
        messagebox.showerror("Ошибка", "Укажите ширину ленты в поле «Ширина (px)».")
        return

    try:
        lent_width = int(width_str)
        if lent_width <= 0:
            raise ValueError()
    except:
        messagebox.showerror("Ошибка", "Поле ширины должно содержать положительное целое число.")
        return

    if img_w % lent_width != 0:
        messagebox.showerror(
            "Ошибка",
            f"Ширина изображения ({img_w}) не делится на ширину ленты ({lent_width}) без остатка.\n"
            "Выберите другую ширину ленты.",
        )
        return

    r_values = []
    g_values = []
    b_values = []

    blocks_per_row = img_w // lent_width

    for row_idx in range(img_h):
        for block_idx in range(blocks_per_row):
            start_col = block_idx * lent_width
            end_col = start_col + lent_width
            block = arr[row_idx, start_col:end_col, :]

            for px in block:
                r_values.append(int(px[0]))
                g_values.append(int(px[1]))
                b_values.append(int(px[2]))

    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    save_dir = os.path.join(desktop, "RGB_Lents")
    os.makedirs(save_dir, exist_ok=True)

    filenames = {
        "Lent_1.txt": r_values,
        "Lent_2.txt": g_values,
        "Lent_3.txt": b_values,
    }

    for fname, values in filenames.items():
        full_path = os.path.join(save_dir, fname)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write("\n".join(str(v) for v in values))

    messagebox.showinfo(
        "Готово",
        f"Три текстовых файла сохранены в папку:\n{save_dir}\n\n"
        f"Файлы:\n"
        f" Lent_1.txt — канал R\n"
        f" Lent_2.txt — канал G\n"
        f" Lent_3.txt — канал B\n\n"
        f"Всего значений в каждом файле: {len(r_values)}\n"
        f"Ширина ленты: {lent_width} px",
    )


# ------------------------------------------------------------
#  GUI
# ------------------------------------------------------------

root = tk.Tk()
root.title("RGB редактор — кортежное сжатие")
root.geometry("900x700")

top_frame = tk.Frame(root)
top_frame.pack(fill=tk.X, padx=8, pady=6)

load_btn = tk.Button(top_frame, text="Загрузить изображение", command=load_image)
load_btn.pack(side=tk.LEFT, padx=(0, 6))

width_label = tk.Label(top_frame, text="Ширина (px):")
width_label.pack(side=tk.LEFT)
width_var = tk.StringVar()
width_entry = tk.Entry(top_frame, textvariable=width_var, width=8)
width_entry.pack(side=tk.LEFT, padx=(4, 12))

open_from_text_btn = tk.Button(top_frame, text="Открыть изображение из RGB", command=open_image_from_text)
open_from_text_btn.pack(side=tk.LEFT, padx=(0, 6))

clear_btn = tk.Button(top_frame, text="Очистить табло", command=clear_text)
clear_btn.pack(side=tk.LEFT, padx=(0, 6))

save_btn = tk.Button(top_frame, text="Сохранить как .txt", command=save_text_to_file)
save_btn.pack(side=tk.LEFT, padx=(0, 6))

# --- НОВЫЕ КНОПКИ ---
compress_btn = tk.Button(top_frame, text="Сжать (в кортеж)", command=compress_to_compact)
compress_btn.pack(side=tk.LEFT, padx=(0, 6))

decompress_btn = tk.Button(top_frame, text="Разжать (из кортежа)", command=decompress_from_compact)
decompress_btn.pack(side=tk.LEFT, padx=(0, 6))

split_btn = tk.Button(top_frame, text="Разделить на RGB-ленты", command=split_image_to_rgb_lents)
split_btn.pack(side=tk.LEFT)

# Текстовая область
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

# Подсказка
hint = tk.Label(
    root,
    text=(
        "Формат ввода: числа через пробел (R G B R G B ...). "
        "«Сжать» — переводит в кортежный формат (252Q1253Q5...). "
        "«Разжать» — обратно в числа через пробел. "
        "Если поле «Ширина» пустое — пытаемся подобрать квадрат."
    ),
    anchor="w",
    justify="left",
)
hint.pack(fill=tk.X, padx=8, pady=(0, 8))

root.mainloop()

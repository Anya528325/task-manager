# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import sqlite3
from datetime import datetime, timedelta
import csv
import calendar
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

class Database:
    def __init__(self):
        self.conn = sqlite3.connect('tasks.db')
        self.create_table()
    
    def create_table(self):
        cursor = self.conn.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            due_date TEXT NOT NULL,
            status TEXT DEFAULT 'Новая',
            category TEXT DEFAULT 'Общие'
        )
        ''')
        self.conn.commit()
    
    def add_task(self, title, description, due_date, category):
        cursor = self.conn.cursor()
        cursor.execute("INSERT INTO tasks (title, description, due_date, category) VALUES (?, ?, ?, ?)",
                      (title, description, due_date, category))
        self.conn.commit()
        return cursor.lastrowid
    
    def get_all_tasks(self, search_term="", status_filter="Все", category_filter="Все"):
        cursor = self.conn.cursor()
        query = "SELECT id, title, description, due_date, status, category FROM tasks WHERE 1=1"
        params = []
        
        if search_term:
            query += " AND (title LIKE ? OR description LIKE ?)"
            params.extend([f"%{search_term}%", f"%{search_term}%"])
        
        if status_filter != "Все":
            query += " AND status = ?"
            params.append(status_filter)
        
        if category_filter != "Все":
            query += " AND category = ?"
            params.append(category_filter)
        
        query += " ORDER BY due_date"
        cursor.execute(query, params)
        return cursor.fetchall()
    
    def get_tasks_by_date(self, date):
        """Получить задачи на конкретную дату"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, title, description, status, category FROM tasks WHERE due_date = ?", (date,))
        return cursor.fetchall()
    
    def get_tasks_by_month(self, year, month):
        """Получить задачи за конкретный месяц"""
        start_date = f"{year}-{month:02d}-01"
        if month == 12:
            end_date = f"{year+1}-01-01"
        else:
            end_date = f"{year}-{month+1:02d}-01"
        
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, title, due_date, status, category FROM tasks WHERE due_date >= ? AND due_date < ?", 
                      (start_date, end_date))
        return cursor.fetchall()
    
    def update_task(self, task_id, title, description, due_date, status, category):
        cursor = self.conn.cursor()
        cursor.execute('''
        UPDATE tasks 
        SET title = ?, description = ?, due_date = ?, status = ?, category = ?
        WHERE id = ?
        ''', (title, description, due_date, status, category, task_id))
        self.conn.commit()
    
    def delete_task(self, task_id):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        self.conn.commit()
    
    def mark_done(self, task_id):
        cursor = self.conn.cursor()
        cursor.execute("UPDATE tasks SET status = 'Выполнено' WHERE id = ?", (task_id,))
        self.conn.commit()
    
    def get_task_stats(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status")
        status_stats = dict(cursor.fetchall())
        
        cursor.execute("SELECT category, COUNT(*) FROM tasks GROUP BY category")
        category_stats = dict(cursor.fetchall())
        
        return status_stats, category_stats
    
    def close(self):
        self.conn.close()

class CalendarTab:
    def __init__(self, parent, db, on_date_select=None):
        self.parent = parent
        self.db = db
        self.on_date_select = on_date_select
        self.current_date = datetime.now()
        self.create_widgets()
        self.update_calendar()
    
    def create_widgets(self):
        # Панель управления календарем
        control_frame = ttk.Frame(self.parent, style="Card.TFrame")
        control_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Кнопки навигации
        ttk.Button(control_frame, text="◀", width=3, 
                  command=lambda: self.change_month(-1), style="Accent.TButton").pack(side=tk.LEFT, padx=5)
        
        # Отображение текущего месяца и года
        self.month_year_var = tk.StringVar()
        self.month_year_label = ttk.Label(control_frame, textvariable=self.month_year_var, 
                                        font=('Segoe UI', 12, 'bold'), foreground="#2c3e50")
        self.month_year_label.pack(side=tk.LEFT, padx=10)
        
        ttk.Button(control_frame, text="▶", width=3, 
                  command=lambda: self.change_month(1), style="Accent.TButton").pack(side=tk.LEFT, padx=5)
        
        ttk.Button(control_frame, text="Сегодня", 
                  command=self.go_to_today, style="Accent.TButton").pack(side=tk.RIGHT)
        
        # Дни недели
        days_frame = ttk.Frame(self.parent, style="Card.TFrame")
        days_frame.pack(fill=tk.X, padx=10, pady=(0, 5))
        
        days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        colors = ['#3498db', '#2ecc71', '#9b59b6', '#e67e22', '#e74c3c', '#1abc9c', '#f1c40f']
        
        for i, day in enumerate(days):
            label = ttk.Label(days_frame, text=day, width=10, anchor=tk.CENTER, 
                            font=('Segoe UI', 10, 'bold'),
                            foreground='white', background=colors[i])
            label.grid(row=0, column=i, sticky="nsew", padx=1, pady=1)
            days_frame.columnconfigure(i, weight=1)
        
        # Календарная сетка
        self.calendar_frame = ttk.Frame(self.parent)
        self.calendar_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Панель задач для выбранного дня
        self.selected_day_frame = ttk.LabelFrame(self.parent, text="Задачи на выбранный день", 
                                              style="Card.TLabelframe")
        self.selected_day_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Создаем Treeview для задач выбранного дня
        self.day_tasks_tree = ttk.Treeview(self.selected_day_frame, columns=("ID", "Название", "Статус", "Категория"), 
                                          show="headings", height=6)
        
        # Настройка скроллбара
        scrollbar = ttk.Scrollbar(self.selected_day_frame, orient="vertical", command=self.day_tasks_tree.yview)
        self.day_tasks_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.day_tasks_tree.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Заголовки столбцов
        columns = {
            "ID": {"width": 40, "anchor": tk.CENTER},
            "Название": {"width": 150, "anchor": tk.W},
            "Статус": {"width": 100, "anchor": tk.CENTER},
            "Категория": {"width": 100, "anchor": tk.CENTER}
        }
        
        for col, settings in columns.items():
            self.day_tasks_tree.heading(col, text=col)
            self.day_tasks_tree.column(col, **settings)
            
        # Теги для цветовой индикации
        self.day_tasks_tree.tag_configure('completed', background='#e6f7ea')
        self.day_tasks_tree.tag_configure('overdue', background='#fde8e8')
        self.day_tasks_tree.tag_configure('in_progress', background='#e6f0ff')
    
    def change_month(self, delta):
        """Переключить месяц вперед или назад"""
        month = self.current_date.month + delta
        year = self.current_date.year
        
        if month > 12:
            month = 1
            year += 1
        elif month < 1:
            month = 12
            year -= 1
            
        self.current_date = datetime(year, month, 1)
        self.update_calendar()
    
    def go_to_today(self):
        """Перейти к текущему месяцу"""
        self.current_date = datetime.now()
        self.update_calendar()
    
    def update_calendar(self):
        """Обновить отображение календаря"""
        # Очищаем предыдущий календарь
        for widget in self.calendar_frame.winfo_children():
            widget.destroy()
        
        # Устанавливаем заголовок
        month_name = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", 
                     "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"][self.current_date.month - 1]
        self.month_year_var.set(f"{month_name} {self.current_date.year}")
        
        # Получаем задачи на месяц
        month_tasks = self.db.get_tasks_by_month(self.current_date.year, self.current_date.month)
        tasks_by_day = {}
        for task in month_tasks:
            day = int(task[2].split('-')[2])
            if day not in tasks_by_day:
                tasks_by_day[day] = []
            tasks_by_day[day].append(task)
        
        # Создаем календарь на месяц
        cal = calendar.Calendar(firstweekday=0)  # Понедельник первый день недели
        month_days = cal.monthdayscalendar(self.current_date.year, self.current_date.month)
        
        # Отображаем календарь
        today = datetime.now().date()
        
        for week_idx, week in enumerate(month_days):
            for day_idx, day in enumerate(week):
                if day == 0:  # День не в текущем месяце
                    frame = ttk.Frame(self.calendar_frame, width=100, height=80, relief=tk.FLAT)
                    frame.grid(row=week_idx, column=day_idx, sticky="nsew", padx=1, pady=1)
                    continue
                
                # Создаем фрейм для дня
                is_today = (self.current_date.year == today.year and 
                           self.current_date.month == today.month and 
                           day == today.day)
                
                frame = ttk.Frame(self.calendar_frame, relief=tk.RAISED, borderwidth=1, 
                                 style='Today.TFrame' if is_today else 'Card.TFrame')
                frame.grid(row=week_idx, column=day_idx, sticky="nsew", padx=1, pady=1)
                frame.grid_propagate(False)
                frame.config(width=100, height=80)
                
                # Число месяца
                day_label = ttk.Label(frame, text=str(day), 
                                    font=('Segoe UI', 10, 'bold'),
                                    foreground='#e74c3c' if is_today else '#2c3e50')
                day_label.pack(anchor=tk.NW, padx=5, pady=5)
                
                # Отображаем задачи для этого дня
                if day in tasks_by_day:
                    num_tasks = len(tasks_by_day[day])
                    
                    # Определяем цвет в зависимости от количества задач
                    if num_tasks > 5:
                        color = '#e74c3c'  # Красный для большого количества задач
                    elif num_tasks > 2:
                        color = '#f39c12'  # Оранжевый для среднего количества
                    else:
                        color = '#2ecc71'  # Зеленый для малого количества
                    
                    tasks_label = ttk.Label(frame, text=f"Задач: {num_tasks}", 
                                          foreground=color, font=('Segoe UI', 8, 'bold'))
                    tasks_label.pack(anchor=tk.SW, padx=5, pady=5)
                
                # Привязываем обработчик клика
                frame.bind("<Button-1>", lambda e, d=day: self.select_day(d))
                day_label.bind("<Button-1>", lambda e, d=day: self.select_day(d))
        
        # Настраиваем пропорции колонок и строк
        for i in range(7):
            self.calendar_frame.columnconfigure(i, weight=1)
        for i in range(6):
            self.calendar_frame.rowconfigure(i, weight=1)
    
    def select_day(self, day):
        """Обработка выбора дня в календаре"""
        selected_date = f"{self.current_date.year}-{self.current_date.month:02d}-{day:02d}"
        
        # Получаем задачи на выбранный день
        tasks = self.db.get_tasks_by_date(selected_date)
        
        # Очищаем предыдущие задачи
        for item in self.day_tasks_tree.get_children():
            self.day_tasks_tree.delete(item)
        
        # Добавляем новые задачи
        for task in tasks:
            tags = []
            if task[3] == "Выполнено":
                tags.append('completed')
            elif task[3] == "Просрочено":
                tags.append('overdue')
            elif task[3] == "В процессе":
                tags.append('in_progress')
                
            self.day_tasks_tree.insert("", tk.END, values=(
                task[0], 
                task[1], 
                task[3], 
                task[4]
            ), tags=tags)
        
        # Обновляем заголовок
        self.selected_day_frame.configure(text=f"Задачи на {day:02d}.{self.current_date.month:02d}.{self.current_date.year}")
        
        # Если есть обработчик выбора даты
        if self.on_date_select:
            self.on_date_select(selected_date)

class TaskManagerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Менеджер задач")
        self.root.geometry("1100x800")
        self.root.configure(bg="#f5f7fa")
        
        self.check_database()
        
        self.db = Database()
        self.create_styles()
        self.create_widgets()
        self.load_tasks()
    
    def create_styles(self):
        self.style = ttk.Style()
        self.style.theme_use('default')
        
        # Общие настройки
        self.style.configure(".", background="#f5f7fa", foreground="#2c3e50", font=('Segoe UI', 10))
        
        # Стили для фреймов
        self.style.configure("Card.TFrame", background="white", borderwidth=1, relief="solid", 
                            bordercolor="#e0e0e0", padding=5)
        self.style.configure("Card.TLabelframe", background="white", borderwidth=1, relief="solid", 
                           bordercolor="#e0e0e0", padding=5)
        self.style.configure("Card.TLabelframe.Label", background="white", foreground="#3498db", 
                           font=('Segoe UI', 10, 'bold'))
        
        # Стили для кнопок
        self.style.configure("TButton", background="#3498db", foreground="white", 
                           borderwidth=0, padding=6)
        self.style.map("TButton", 
                      background=[('active', '#2980b9'), ('pressed', '#1c638e')],
                      foreground=[('active', 'white'), ('pressed', 'white')])
        
        self.style.configure("Accent.TButton", background="#e74c3c", foreground="white", 
                           borderwidth=0, padding=6)
        self.style.map("Accent.TButton", 
                      background=[('active', '#c0392b'), ('pressed', '#962d22')],
                      foreground=[('active', 'white'), ('pressed', 'white')])
        
        # Стили для Treeview
        self.style.configure("Treeview", background="white", foreground="#2c3e50", 
                           fieldbackground="white", rowheight=28, font=('Segoe UI', 9))
        self.style.configure("Treeview.Heading", background="#3498db", foreground="white", 
                          font=('Segoe UI', 10, 'bold'))
        self.style.map("Treeview", background=[('selected', '#4a6984')])
        
        # Стили для вкладок
        self.style.configure("TNotebook", background="#f5f7fa")
        self.style.configure("TNotebook.Tab", background="#e0e0e0", padding=[10, 5])
        self.style.map("TNotebook.Tab", 
                      background=[('selected', 'white'), ('active', '#d5e8f7')],
                      foreground=[('selected', '#3498db'), ('active', '#2c3e50')])
        
        # Стили для меток
        self.style.configure("TLabel", background="#f5f7fa", foreground="#2c3e50")
        
        # Специальные стили
        self.style.configure("Today.TFrame", background="#e6f7ff", borderwidth=1, relief="solid")
        
        # Стили для полей ввода
        self.style.configure("TEntry", fieldbackground="white", bordercolor="#bdc3c7", 
                           lightcolor="#bdc3c7", darkcolor="#bdc3c7")
        self.style.configure("TCombobox", fieldbackground="white", bordercolor="#bdc3c7", 
                           lightcolor="#bdc3c7", darkcolor="#bdc3c7")
    
    def create_widgets(self):
        # Заголовок приложения
        header_frame = ttk.Frame(self.root, style="Card.TFrame")
        header_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Label(header_frame, text="📋 Менеджер задач", 
                 font=('Segoe UI', 16, 'bold'), 
                 foreground="#3498db").pack(pady=10)
        
        # Создаем вкладки
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=5)
        
        # Вкладка задач
        self.tasks_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.tasks_tab, text="📋 Задачи")
        
        # Вкладка календаря
        self.calendar_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.calendar_tab, text="📅 Календарь")
        
        # Вкладка статистики
        self.stats_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.stats_tab, text="📊 Статистика")
        
        # Создаем содержимое вкладок
        self.create_tasks_tab()
        self.create_calendar_tab()
        self.create_stats_tab()
        
        # Панель инструментов
        toolbar = ttk.Frame(self.root, style="Card.TFrame")
        toolbar.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        ttk.Button(toolbar, text="📤 Экспорт в CSV", command=self.export_to_csv).pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Button(toolbar, text="🔄 Обновить", command=self.load_tasks).pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Button(toolbar, text="❌ Выход", command=self.root.destroy, style="Accent.TButton").pack(side=tk.RIGHT, padx=5, pady=5)
    
    def create_tasks_tab(self):
        # Панель ввода данных
        input_frame = ttk.LabelFrame(self.tasks_tab, text="➕ Добавить новую задачу", style="Card.TLabelframe")
        input_frame.pack(pady=10, padx=10, fill=tk.X)
        
        # Название задачи
        ttk.Label(input_frame, text="Название:").grid(row=0, column=0, sticky=tk.W, padx=10, pady=5)
        self.title_entry = ttk.Entry(input_frame, width=40)
        self.title_entry.grid(row=0, column=1, padx=10, pady=5, sticky=tk.W)
        
        # Описание
        ttk.Label(input_frame, text="Описание:").grid(row=1, column=0, sticky=tk.W, padx=10, pady=5)
        self.desc_entry = ttk.Entry(input_frame, width=40)
        self.desc_entry.grid(row=1, column=1, padx=10, pady=5, sticky=tk.W)
        
        # Дата выполнения
        ttk.Label(input_frame, text="Дата (ДД.ММ.ГГГГ):").grid(row=2, column=0, sticky=tk.W, padx=10, pady=5)
        self.due_entry = ttk.Entry(input_frame, width=40)
        self.due_entry.grid(row=2, column=1, padx=10, pady=5, sticky=tk.W)
        
        # Категория
        ttk.Label(input_frame, text="Категория:").grid(row=3, column=0, sticky=tk.W, padx=10, pady=5)
        self.category_var = tk.StringVar()
        categories = ["Работа", "Учеба", "Личное", "Семья", "Общие"]
        self.category_combo = ttk.Combobox(input_frame, textvariable=self.category_var, 
                                         values=categories, state="readonly", width=37)
        self.category_combo.set("Общие")
        self.category_combo.grid(row=3, column=1, padx=10, pady=5, sticky=tk.W)
        
        # Кнопки
        btn_frame = ttk.Frame(self.tasks_tab, style="Card.TFrame")
        btn_frame.pack(pady=10)
        
        ttk.Button(btn_frame, text="➕ Добавить задачу", command=self.add_task, 
                  style="Accent.TButton").pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Button(btn_frame, text="✅ Выполнено", command=self.mark_done).pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Button(btn_frame, text="❌ Удалить", command=self.delete_task, style="Accent.TButton").pack(side=tk.LEFT, padx=5, pady=5)
        
        # Панель фильтров
        filter_frame = ttk.LabelFrame(self.tasks_tab, text="🔍 Фильтры", style="Card.TLabelframe")
        filter_frame.pack(pady=5, padx=10, fill=tk.X)
        
        # Поиск
        ttk.Label(filter_frame, text="Поиск:").grid(row=0, column=0, sticky=tk.W, padx=10, pady=5)
        self.search_entry = ttk.Entry(filter_frame, width=30)
        self.search_entry.grid(row=0, column=1, padx=10, pady=5, sticky=tk.W)
        self.search_entry.bind("<KeyRelease>", lambda e: self.load_tasks())
        
        # Фильтр по статусу
        ttk.Label(filter_frame, text="Статус:").grid(row=0, column=2, sticky=tk.W, padx=10, pady=5)
        self.status_var = tk.StringVar(value="Все")
        statuses = ["Все", "Новая", "В процессе", "Выполнено"]
        ttk.Combobox(filter_frame, textvariable=self.status_var, 
                    values=statuses, state="readonly", width=12).grid(row=0, column=3, padx=10, pady=5)
        self.status_var.trace_add("write", lambda *args: self.load_tasks())
        
        # Фильтр по категории
        ttk.Label(filter_frame, text="Категория:").grid(row=0, column=4, sticky=tk.W, padx=10, pady=5)
        self.category_filter_var = tk.StringVar(value="Все")
        categories_filter = ["Все"] + categories
        ttk.Combobox(filter_frame, textvariable=self.category_filter_var, 
                    values=categories_filter, state="readonly", width=12).grid(row=0, column=5, padx=10, pady=5)
        self.category_filter_var.trace_add("write", lambda *args: self.load_tasks())
        
        # Таблица задач
        tree_frame = ttk.Frame(self.tasks_tab, style="Card.TFrame")
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.tree = ttk.Treeview(tree_frame, columns=("ID", "Название", "Описание", "Дата", "Статус", "Категория"), 
                                show="headings", selectmode="browse")
        
        # Настройка скроллбара
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)
        
        # Заголовки столбцов
        columns = {
            "ID": {"width": 50, "anchor": tk.CENTER},
            "Название": {"width": 150, "anchor": tk.W},
            "Описание": {"width": 200, "anchor": tk.W},
            "Дата": {"width": 100, "anchor": tk.CENTER},
            "Статус": {"width": 100, "anchor": tk.CENTER},
            "Категория": {"width": 100, "anchor": tk.CENTER}
        }
        
        for col, settings in columns.items():
            self.tree.heading(col, text=col)
            self.tree.column(col, **settings)
        
        # Теги для цветовой индикации
        self.tree.tag_configure('completed', background='#e6f7ea')
        self.tree.tag_configure('overdue', background='#fde8e8')
        self.tree.tag_configure('in_progress', background='#e6f0ff')
        
        # Привязка двойного клика для редактирования
        self.tree.bind("<Double-1>", self.edit_task)
    
    def create_calendar_tab(self):
        """Создаем вкладку календаря"""
        self.calendar = CalendarTab(self.calendar_tab, self.db, self.on_date_select)
    
    def on_date_select(self, date):
        """Обработчик выбора даты в календаре"""
        # Переключаемся на вкладку задач
        self.notebook.select(0)
        
        # Устанавливаем выбранную дату
        try:
            year, month, day = date.split('-')
            formatted_date = f"{int(day):02d}.{int(month):02d}.{year}"
            self.due_entry.delete(0, tk.END)
            self.due_entry.insert(0, formatted_date)
        except:
            pass
    
    def create_stats_tab(self):
        # Фрейм для статистики
        stats_frame = ttk.Frame(self.stats_tab)
        stats_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Контейнер для графиков
        container = ttk.Frame(stats_frame)
        container.pack(fill=tk.BOTH, expand=True)
        
        # График статусов
        status_frame = ttk.LabelFrame(container, text="📊 Распределение по статусам", 
                                   style="Card.TLabelframe")
        status_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # График категорий
        category_frame = ttk.LabelFrame(container, text="📊 Распределение по категориям", 
                                     style="Card.TLabelframe")
        category_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Обновление статистики
        self.update_stats(status_frame, category_frame)
    
    def update_stats(self, status_frame, category_frame):
        # Очищаем предыдущие графики
        for widget in status_frame.winfo_children():
            widget.destroy()
        
        for widget in category_frame.winfo_children():
            widget.destroy()
        
        # Получаем данные
        status_stats, category_stats = self.db.get_task_stats()
        
        # Создаем график для статусов
        fig1 = plt.Figure(figsize=(6, 4), dpi=80, facecolor='#f5f7fa')
        ax1 = fig1.add_subplot(111, facecolor='#f5f7fa')
        
        if status_stats:
            colors = ['#3498db', '#2ecc71', '#e74c3c', '#f39c12', '#9b59b6']
            explode = [0.05] * len(status_stats)
            
            wedges, texts, autotexts = ax1.pie(
                status_stats.values(), 
                labels=status_stats.keys(), 
                autopct=lambda p: f'{p:.1f}%\n({int(p*sum(status_stats.values())/100)})',
                explode=explode,
                colors=colors[:len(status_stats)],
                shadow=True,
                startangle=90,
                textprops={'fontsize': 10}
            )
            
            # Делаем подписи жирными
            for text in texts:
                text.set_fontweight('bold')
                
            for autotext in autotexts:
                autotext.set_fontweight('bold')
                autotext.set_fontsize(10)
                
            ax1.set_title('Статусы задач', fontsize=14, fontweight='bold', color='#2c3e50', pad=10)
            ax1.axis('equal')
            
        else:
            ax1.text(0.5, 0.5, 'Нет данных', ha='center', va='center', 
                    fontsize=12, fontweight='bold', color='#7f8c8d')
            ax1.set_axis_off()
        
        canvas1 = FigureCanvasTkAgg(fig1, master=status_frame)
        canvas1.draw()
        canvas1.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Создаем график для категорий
        fig2 = plt.Figure(figsize=(6, 4), dpi=100, facecolor='#f5f7fa')
        ax2 = fig2.add_subplot(111, facecolor='#f5f7fa')
        
        if category_stats:
            # Генерируем цвета на основе количества категорий
            colors = list(mcolors.TABLEAU_COLORS.values())
            if len(category_stats) > len(colors):
                colors = list(plt.cm.tab20.colors)
            
            wedges, texts, autotexts = ax2.pie(
                category_stats.values(), 
                labels=category_stats.keys(), 
                autopct=lambda p: f'{p:.1f}%\n({int(p*sum(category_stats.values())/100)})',
                colors=colors[:len(category_stats)],
                shadow=True,
                startangle=90,
                textprops={'fontsize': 10}
            )
            
            # Делаем подписи жирными
            for text in texts:
                text.set_fontweight('bold')
                
            for autotext in autotexts:
                autotext.set_fontweight('bold')
                autotext.set_fontsize(10)
                
            ax2.set_title('Категории задач', fontsize=12, fontweight='bold', color='#2c3e50', pad=10)
            ax2.axis('equal')
            
            
        else:
            ax2.text(0.5, 0.5, 'Нет данных', ha='center', va='center', 
                    fontsize=12, fontweight='bold', color='#7f8c8d')
            ax2.set_axis_off()
        
        canvas2 = FigureCanvasTkAgg(fig2, master=category_frame)
        canvas2.draw()
        canvas2.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    
    def add_task(self):
        title = self.title_entry.get().strip()
        description = self.desc_entry.get().strip()
        due_date = self.due_entry.get().strip()
        category = self.category_var.get()
        
        if not title or not due_date:
            messagebox.showerror("Ошибка", "Укажите название и дату!")
            return
        
        try:
            day, month, year = map(int, due_date.split('.'))
            date_obj = datetime(year, month, day)
            db_date = date_obj.strftime("%Y-%m-%d")
        except ValueError:
            messagebox.showerror("Ошибка", "Неверный формат даты! Используйте ДД.ММ.ГГГГ")
            return
        
        self.db.add_task(title, description, db_date, category)
        self.clear_entries()
        self.load_tasks()
        self.update_stats_tab()
        self.calendar.update_calendar()  # Обновляем календарь
    
    def load_tasks(self):
        search_term = self.search_entry.get()
        status_filter = self.status_var.get()
        category_filter = self.category_filter_var.get()
        
        tasks = self.db.get_all_tasks(search_term, status_filter, category_filter)
        
        # Очистка таблицы
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        # Заполнение данными
        today = datetime.now().date()
        
        for task in tasks:
            task_id, title, description, due_date, status, category = task
            
            try:
                # Преобразование даты из БД в формат ДД.ММ.ГГГГ
                if due_date:
                    task_date = datetime.strptime(due_date, "%Y-%m-%d").date()
                    display_date = task_date.strftime("%d.%m.%Y")
                    
                    # Проверка на просроченность
                    if status != "Выполнено" and task_date < today:
                        status = "Просрочено"
            except ValueError:
                display_date = "Некорректная дата"
            
            tags = []
            if status == "Выполнено":
                tags.append('completed')
            elif status == "Просрочено":
                tags.append('overdue')
            elif status == "В процессе":
                tags.append('in_progress')
            
            self.tree.insert("", tk.END, values=(
                task_id, 
                title, 
                description[:50] + "..." if len(description) > 50 else description,
                display_date,
                status,
                category
            ), tags=tags)
    
    def mark_done(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите задачу!")
            return
        
        task_id = self.tree.item(selected[0])['values'][0]
        self.db.mark_done(task_id)
        self.load_tasks()
        self.update_stats_tab()
        self.calendar.update_calendar()  # Обновляем календарь
    
    def delete_task(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите задачу!")
            return
        
        task_id = self.tree.item(selected[0])['values'][0]
        if messagebox.askyesno("Подтверждение", "Удалить выбранную задачу?"):
            self.db.delete_task(task_id)
            self.load_tasks()
            self.update_stats_tab()
            self.calendar.update_calendar()  # Обновляем календарь
    
    def edit_task(self, event):
        selected = self.tree.selection()
        if not selected:
            return
        
        item = selected[0]
        task_data = self.tree.item(item, 'values')
        task_id = task_data[0]
        
        # Получаем полные данные о задаче из БД
        conn = sqlite3.connect('tasks.db')
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        task = cursor.fetchone()
        conn.close()
        
        if not task:
            return
        
        # Создаем окно редактирования
        edit_win = tk.Toplevel(self.root)
        edit_win.title("Редактирование задачи")
        edit_win.geometry("500x400")
        edit_win.configure(bg="#f5f7fa")
        edit_win.grab_set()
        
        # Основной фрейм
        main_frame = ttk.Frame(edit_win, style="Card.TFrame")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Поля для редактирования
        ttk.Label(main_frame, text="Название:").pack(pady=(10, 2), padx=10, anchor=tk.W)
        title_entry = ttk.Entry(main_frame, width=50)
        title_entry.pack(padx=10, fill=tk.X)
        title_entry.insert(0, task[1])
        
        ttk.Label(main_frame, text="Описание:").pack(pady=(10, 2), padx=10, anchor=tk.W)
        desc_entry = tk.Text(main_frame, height=5, width=50)
        desc_entry.pack(padx=10, fill=tk.X)
        desc_entry.insert("1.0", task[2] if task[2] else "")
        
        ttk.Label(main_frame, text="Дата (ДД.ММ.ГГГГ):").pack(pady=(10, 2), padx=10, anchor=tk.W)
        due_entry = ttk.Entry(main_frame, width=50)
        due_entry.pack(padx=10, fill=tk.X)
        due_date = datetime.strptime(task[3], "%Y-%m-%d").strftime("%d.%m.%Y")
        due_entry.insert(0, due_date)
        
        ttk.Label(main_frame, text="Категория:").pack(pady=(10, 2), padx=10, anchor=tk.W)
        category_var = tk.StringVar()
        categories = ["Работа", "Учеба", "Личное", "Семья", "Общие"]
        category_combo = ttk.Combobox(main_frame, textvariable=category_var, 
                                     values=categories, state="readonly", width=47)
        category_combo.pack(padx=10, anchor=tk.W)
        category_combo.set(task[5] if task[5] else "Общие")
        
        ttk.Label(main_frame, text="Статус:").pack(pady=(10, 2), padx=10, anchor=tk.W)
        status_var = tk.StringVar()
        status_combo = ttk.Combobox(main_frame, textvariable=status_var, 
                                   values=["Новая", "В процессе", "Выполнено"], 
                                   state="readonly", width=47)
        status_combo.pack(padx=10, anchor=tk.W)
        status_combo.set(task[4] if task[4] else "Новая")
        
        # Кнопка сохранения
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(pady=20)
        
        ttk.Button(btn_frame, text="Сохранить", command=lambda: self.save_edited_task(
            task_id,
            title_entry.get(),
            desc_entry.get("1.0", tk.END).strip(),
            due_entry.get(),
            status_var.get(),
            category_var.get(),
            edit_win
        )).pack(side=tk.LEFT, padx=10)
        
        ttk.Button(btn_frame, text="Отмена", command=edit_win.destroy).pack(side=tk.LEFT, padx=10)
    
    def save_edited_task(self, task_id, title, description, due_date, status, category, window):
        if not title or not due_date:
            messagebox.showerror("Ошибка", "Укажите название и дату!")
            return
        
        try:
            day, month, year = map(int, due_date.split('.'))
            date_obj = datetime(year, month, day)
            db_date = date_obj.strftime("%Y-%m-%d")
        except ValueError:
            messagebox.showerror("Ошибка", "Неверный формат даты! Используйте ДД.ММ.ГГГГ")
            return
        
        self.db.update_task(task_id, title, description, db_date, status, category)
        window.destroy()
        self.load_tasks()
        self.update_stats_tab()
        self.calendar.update_calendar()  # Обновляем календарь
        messagebox.showinfo("Успех", "Задача успешно обновлена!")
    
    def export_to_csv(self):
        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV файлы", "*.csv"), ("Все файлы", "*.*")]
        )
        
        if not filename:
            return
        
        try:
            tasks = self.db.get_all_tasks()
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerow(['ID', 'Название', 'Описание', 'Дата', 'Статус', 'Категория'])
                
                for task in tasks:
                    # Преобразование даты в формат ДД.ММ.ГГГГ
                    try:
                        task_date = datetime.strptime(task[3], "%Y-%m-%d")
                        formatted_date = task_date.strftime("%d.%m.%Y")
                    except:
                        formatted_date = task[3]
                    
                    writer.writerow([
                        task[0],
                        task[1],
                        task[2],
                        formatted_date,
                        task[4],
                        task[5]
                    ])
            
            messagebox.showinfo("Успех", f"Данные экспортированы в:\n{filename}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось экспортировать данные:\n{str(e)}")
    
    def update_stats_tab(self):
        """Обновляет вкладку статистики"""
        status_frame = None
        category_frame = None
        
        for widget in self.stats_tab.winfo_children():
            if isinstance(widget, ttk.Frame):
                for child in widget.winfo_children():
                    if "статусам" in child.cget("text"):
                        status_frame = child
                    elif "категориям" in child.cget("text"):
                        category_frame = child
        
        if status_frame and category_frame:
            self.update_stats(status_frame, category_frame)
    
    def clear_entries(self):
        self.title_entry.delete(0, tk.END)
        self.desc_entry.delete(0, tk.END)
        self.due_entry.delete(0, tk.END)
        self.category_combo.set("Общие")

    def check_database(self):
        """Проверяет существование БД и создает при необходимости"""
        try:
            conn = sqlite3.connect('tasks.db')
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'")
            table_exists = cursor.fetchone()
            conn.close()
            
            if not table_exists:
                self.initialize_database()
        except:
            self.initialize_database()
    
    def initialize_database(self):
        """Иницфиализирует базу данных"""
        # Используем тот же код, что и в скрипте инициализации
        conn = sqlite3.connect('tasks.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                due_date TEXT NOT NULL,
                status TEXT DEFAULT 'Новая',
                category TEXT DEFAULT 'Общие',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()

if __name__ == "__main__":
    root = tk.Tk()
    app = TaskManagerApp(root)
    root.mainloop()
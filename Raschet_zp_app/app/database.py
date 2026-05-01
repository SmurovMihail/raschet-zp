# (работа с базой данных)

import sqlite3
import os
import sys
from contextlib import contextmanager
from datetime import datetime

class Database:
    def __init__(self):
        """инициализация подключения к базе данных"""
        
        if getattr(sys, 'frozen', False):
            base_path = os.path.dirname(sys.executable)
        else:
            base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        self.db_path = os.path.join(base_path, 'database', 'payroll.db')
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.init_db()
    
    @contextmanager
    def get_connection(self):
        """контекстный менеджер для работы с бд"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def init_db(self):
        """создание таблиц если они не существуют"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # таблица Организация (сотрудники) - все колонки сразу
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS Организация (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ФИО TEXT NOT NULL,
                    ИНН TEXT UNIQUE,
                    СНИЛС TEXT UNIQUE,
                    должность TEXT NOT NULL,
                    тип_оплаты TEXT CHECK(тип_оплаты IN ('оклад', 'почасовая')) NOT NULL,
                    оклад REAL DEFAULT 0,
                    ставка_час REAL DEFAULT 0,
                    стандартный_вычет REAL DEFAULT 0,
                    дата_приёма DATE NOT NULL,
                    дата_увольнения DATE,
                    is_active INTEGER DEFAULT 1
                )
            ''')
            
            # таблица РасчетныеПериоды
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS РасчетныеПериоды (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    месяц INTEGER NOT NULL CHECK(месяц BETWEEN 1 AND 12),
                    год INTEGER NOT NULL,
                    дата_расчёта DATE DEFAULT CURRENT_DATE,
                    UNIQUE(месяц, год)
                )
            ''')
            
            # таблица Начисления
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS Начисления (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    employee_id INTEGER NOT NULL,
                    period_id INTEGER NOT NULL,
                    отработано_часов REAL DEFAULT 0,
                    премия REAL DEFAULT 0,
                    доп_начисления REAL DEFAULT 0,
                    удержек REAL DEFAULT 0,
                    начислено_всего REAL DEFAULT 0,
                    НДФЛ REAL DEFAULT 0,
                    страховые_взносы REAL DEFAULT 0,
                    FOREIGN KEY (employee_id) REFERENCES Организация(id) ON DELETE CASCADE,
                    FOREIGN KEY (period_id) REFERENCES РасчетныеПериоды(id) ON DELETE CASCADE,
                    UNIQUE(employee_id, period_id)
                )
            ''')
            
            # индексы
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_начисления_employee ON Начисления(employee_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_начисления_period ON Начисления(period_id)')
            
            self.init_default_data()
    
    def init_default_data(self):
        """добавление тестовых данных если таблицы пустые"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # проверяем есть ли сотрудники
            cursor.execute('SELECT COUNT(*) FROM Организация')
            if cursor.fetchone()[0] == 0:
                test_employees = [
                    ('Иванов Иван Иванович', '770112345678', '12345678901', 'Генеральный директор', 'оклад', 150000, 0, 0, '2020-01-15'),
                    ('Петрова Елена Сергеевна', '770176543210', '10987654321', 'Главный бухгалтер', 'оклад', 90000, 0, 1400, '2020-02-01'),
                    ('Сидоров Петр Николаевич', '770155555555', '11223344556', 'Менеджер', 'оклад', 60000, 0, 2800, '2021-03-10'),
                    ('Козлова Анна Викторовна', '770166666666', '12312312312', 'Программист', 'почасовая', 0, 800, 1400, '2021-05-20'),
                    ('Смирнов Дмитрий Алексеевич', '770177777777', '13131313131', 'Системный администратор', 'почасовая', 0, 650, 0, '2022-06-15'),
                ]
                for emp in test_employees:
                    cursor.execute('''
                        INSERT INTO Организация (ФИО, ИНН, СНИЛС, должность, тип_оплаты, оклад, ставка_час, стандартный_вычет, дата_приёма)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', emp)
            
            # проверяем есть ли расчетные периоды
            cursor.execute('SELECT COUNT(*) FROM РасчетныеПериоды')
            if cursor.fetchone()[0] == 0:
                for year in range(2023, 2027):
                    for month in range(1, 13):
                        cursor.execute('''
                            INSERT INTO РасчетныеПериоды (месяц, год, дата_расчёта)
                            VALUES (?, ?, ?)
                        ''', (month, year, f'{year}-{month:02d}-01'))
    
    # --- методы для работы с сотрудниками ---
    
    def get_all_employees(self, active_only=True):
        """получить всех сотрудников (только активных по умолчанию)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if active_only:
                cursor.execute('SELECT * FROM Организация WHERE is_active = 1 ORDER BY ФИО')
            else:
                cursor.execute('SELECT * FROM Организация ORDER BY ФИО')
            return [dict(row) for row in cursor.fetchall()]
    
    def get_employee(self, employee_id):
        """получить сотрудника по id"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM Организация WHERE id = ?', (employee_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def add_employee(self, data):
        """добавить сотрудника с проверкой длины инн и снилс"""
        inn = data.get('ИНН', '').strip()
        snils = data.get('СНИЛС', '').strip()
        
        if inn and inn not in ['', '-']:
            if len(inn) not in [10, 12] or not inn.isdigit():
                raise ValueError("ИНН должен содержать 10 или 12 цифр")
        
        if snils and snils not in ['', '-']:
            if len(snils) != 11 or not snils.isdigit():
                raise ValueError("СНИЛС должен содержать 11 цифр")
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO Организация (ФИО, ИНН, СНИЛС, должность, тип_оплаты, оклад, ставка_час, стандартный_вычет, дата_приёма)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                data['ФИО'], inn if inn else '', snils if snils else '',
                data['должность'], data['тип_оплаты'],
                data.get('оклад', 0), data.get('ставка_час', 0),
                data.get('стандартный_вычет', 0), data['дата_приёма']
            ))
            return cursor.lastrowid
    
    def update_employee(self, employee_id, data):
        """обновить данные сотрудника"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE Организация 
                SET ФИО=?, ИНН=?, СНИЛС=?, должность=?, тип_оплаты=?, 
                    оклад=?, ставка_час=?, стандартный_вычет=?
                WHERE id=?
            ''', (
                data['ФИО'], data.get('ИНН', ''), data.get('СНИЛС', ''),
                data['должность'], data['тип_оплаты'],
                data.get('оклад', 0), data.get('ставка_час', 0),
                data.get('стандартный_вычет', 0), employee_id
            ))
    
    def fire_employee(self, employee_id):
        """уволить сотрудника (помечает как неактивного)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE Организация 
                SET is_active = 0, дата_увольнения = DATE('now')
                WHERE id = ?
            ''', (employee_id,))

    def reinstate_employee(self, employee_id):
        """восстановить уволенного сотрудника"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE Организация 
                SET is_active = 1, дата_увольнения = NULL
                WHERE id = ?
            ''', (employee_id,))
    
    # --- методы для работы с периодами ---
    
    def get_all_periods(self):
        """получить все расчетные периоды"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM РасчетныеПериоды ORDER BY год DESC, месяц DESC')
            return [dict(row) for row in cursor.fetchall()]
    
    def get_available_years(self):
        """получить доступные годы для выбора"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT DISTINCT год FROM РасчетныеПериоды ORDER BY год DESC')
            return [row['год'] for row in cursor.fetchall()]
    
    def get_periods_by_year(self, year):
        """получить периоды за определенный год"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM РасчетныеПериоды WHERE год = ? ORDER BY месяц', (year,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_period(self, month, year):
        """получить период по месяцу и году"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM РасчетныеПериоды WHERE месяц = ? AND год = ?', (month, year))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_or_create_period(self, month, year):
        """получить или создать период"""
        period = self.get_period(month, year)
        if not period:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO РасчетныеПериоды (месяц, год, дата_расчёта)
                    VALUES (?, ?, DATE('now'))
                ''', (month, year))
                return self.get_period(month, year)
        return period
    
    # --- методы для работы с начислениями ---
    
    def save_payroll(self, data):
        """сохранить или обновить начисление"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id FROM Начисления 
                WHERE employee_id = ? AND period_id = ?
            ''', (data['employee_id'], data['period_id']))
            existing = cursor.fetchone()
            
            if existing:
                cursor.execute('''
                    UPDATE Начисления 
                    SET отработано_часов=?, премия=?, доп_начисления=?, 
                        удержек=?, начислено_всего=?, НДФЛ=?, страховые_взносы=?
                    WHERE employee_id = ? AND period_id = ?
                ''', (
                    data.get('отработано_часов', 0), data.get('премия', 0),
                    data.get('доп_начисления', 0), data.get('удержек', 0),
                    data['начислено_всего'], data['НДФЛ'], data['страховые_взносы'],
                    data['employee_id'], data['period_id']
                ))
            else:
                cursor.execute('''
                    INSERT INTO Начисления 
                    (employee_id, period_id, отработано_часов, премия, доп_начисления, 
                     удержек, начислено_всего, НДФЛ, страховые_взносы)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    data['employee_id'], data['period_id'],
                    data.get('отработано_часов', 0), data.get('премия', 0),
                    data.get('доп_начисления', 0), data.get('удержек', 0),
                    data['начислено_всего'], data['НДФЛ'], data['страховые_взносы']
                ))
            return True
    
    def get_payroll_by_period(self, period_id):
        """получить все начисления за период"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT n.*, o.ФИО, o.должность, o.тип_оплаты, o.оклад, o.ставка_час
                FROM Начисления n
                JOIN Организация o ON n.employee_id = o.id
                WHERE n.period_id = ?
                ORDER BY o.ФИО
            ''', (period_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_payroll_by_employee(self, employee_id):
        """получить все начисления сотрудника"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT n.*, p.месяц, p.год
                FROM Начисления n
                JOIN РасчетныеПериоды p ON n.period_id = p.id
                WHERE n.employee_id = ?
                ORDER BY p.год DESC, p.месяц DESC
            ''', (employee_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    # --- методы для статистики ---
    
    def get_summary_by_period(self, period_id):
        """получить сводку по периоду"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    COUNT(*) as count_employees,
                    COALESCE(SUM(начислено_всего), 0) as total_accrued,
                    COALESCE(SUM(НДФЛ), 0) as total_ndfl,
                    COALESCE(SUM(страховые_взносы), 0) as total_insurance,
                    COALESCE(SUM(начислено_всего - НДФЛ), 0) as total_to_pay
                FROM Начисления
                WHERE period_id = ?
            ''', (period_id,))
            row = cursor.fetchone()
            return {
                'count_employees': row[0] if row[0] else 0,
                'total_accrued': row[1] if row[1] else 0,
                'total_ndfl': row[2] if row[2] else 0,
                'total_insurance': row[3] if row[3] else 0,
                'total_to_pay': row[4] if row[4] else 0
            }
    
    def get_summary_by_year(self, year):
        """получить сводку по году"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    SUM(начислено_всего) as total_accrued,
                    SUM(НДФЛ) as total_ndfl,
                    SUM(страховые_взносы) as total_insurance,
                    SUM(начислено_всего - НДФЛ) as total_to_pay
                FROM Начисления n
                JOIN РасчетныеПериоды p ON n.period_id = p.id
                WHERE p.год = ?
            ''', (year,))
            row = cursor.fetchone()
            return {
                'total_accrued': row[0] if row[0] else 0,
                'total_ndfl': row[1] if row[1] else 0,
                'total_insurance': row[2] if row[2] else 0,
                'total_to_pay': row[3] if row[3] else 0
            }
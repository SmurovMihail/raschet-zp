# (логика расчета заработной платы)

from datetime import datetime

class PayrollCalculator:
    """Класс для расчета заработной платы"""
    
    # ставки налогов и взносов
    NDFL_RATE = 0.13        # 13% НДФЛ
    INSURANCE_RATE = 0.30   # 30% страховые взносы
    
    def __init__(self, db):
        """инициализация с подключением к бд"""
        self.db = db
    
    def calculate_employee_salary(self, employee, worked_hours=None, worked_days=None,
                                   bonus=0, additional=0, deduction=0):
        """расчет зарплаты для одного сотрудника"""
        
        # расчет базовой суммы
        if employee['тип_оплаты'] == 'почасовая':        
            hours = worked_hours or 0
            base_salary = hours * employee['ставка_час']
        else:
            salary = employee['оклад']
            if worked_days is not None:
                days_in_month = self._get_days_in_month()
                base_salary = salary * (worked_days / days_in_month)
            else:
                base_salary = salary
        
        # учет премий и доп. начислений
        total_accrued = base_salary + bonus + additional
        
        # учет удержаний
        total_after_deductions = total_accrued - deduction
        
        # расчет НДФЛ с учетом вычетов
        taxable_amount = max(0, total_after_deductions - employee.get('стандартный_вычет', 0))
        ndfl = taxable_amount * self.NDFL_RATE
        
        # расчет страховых взносов
        insurance = total_after_deductions * self.INSURANCE_RATE
        
        # сумма к выдаче
        to_pay = total_after_deductions - ndfl
        
        # округление
        total_accrued = round(total_accrued, 2)
        ndfl = round(ndfl, 2)
        insurance = round(insurance, 2)
        to_pay = round(to_pay, 2)
        
        return {
            'employee_id': employee['id'],
            'начислено_всего': total_accrued,
            'НДФЛ': ndfl,
            'страховые_взносы': insurance,
            'к_выдаче': to_pay,
            'базовая_сумма': base_salary,
            'премия': bonus,
            'доп_начисления': additional,
            'удержек': deduction
        }
    
    def calculate_period_payroll(self, period_id, employees_data):
        """расчет зарплаты для всех сотрудников за период"""
        results = []
        total_summary = {
            'total_accrued': 0,
            'total_ndfl': 0,
            'total_insurance': 0,
            'total_to_pay': 0,
            'employee_count': 0
        }
        
        for emp_data in employees_data:
            employee = self.db.get_employee(emp_data['employee_id'])
            if not employee:
                continue
            
            result = self.calculate_employee_salary(
                employee,
                worked_hours=emp_data.get('отработано_часов'),
                worked_days=emp_data.get('отработано_дней'),
                bonus=emp_data.get('премия', 0),
                additional=emp_data.get('доп_начисления', 0),
                deduction=emp_data.get('удержек', 0)
            )
            
            result['period_id'] = period_id
            
            payroll_data = {
                'employee_id': result['employee_id'],
                'period_id': period_id,
                'отработано_часов': emp_data.get('отработано_часов', 0),
                'отработано_дней': emp_data.get('отработано_дней', 0),
                'премия': result['премия'],
                'доп_начисления': result['доп_начисления'],
                'удержек': result['удержек'],
                'начислено_всего': result['начислено_всего'],
                'НДФЛ': result['НДФЛ'],
                'страховые_взносы': result['страховые_взносы']
            }
            
            self.db.save_payroll(payroll_data)
            results.append(result)
            
            total_summary['total_accrued'] += result['начислено_всего']
            total_summary['total_ndfl'] += result['НДФЛ']
            total_summary['total_insurance'] += result['страховые_взносы']
            total_summary['total_to_pay'] += result['к_выдаче']
            total_summary['employee_count'] += 1
        
        for key in total_summary:
            if key != 'employee_count':
                total_summary[key] = round(total_summary[key], 2)
        
        return results, total_summary
    
    def _get_days_in_month(self):
        """количество дней в текущем месяце"""
        now = datetime.now()
        if now.month == 2:
            year = now.year
            if (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0):
                return 29
            return 28
        elif now.month in [4, 6, 9, 11]:
            return 30
        else:
            return 31
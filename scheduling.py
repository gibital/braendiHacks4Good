# scheduling.py
import random
from ortools.sat.python import cp_model
import pandas as pd
from itertools import combinations

# Constants and allowed values
allowed_multipliers = [0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 1.0]
BASE_HOURS = 420

def generate_sample_data(employees):
    """
    Generates sample multipliers and availability data for a list of employees.
    Uses up to 50 attempts to get aggregate target hours between 1850 and 2000.
    Returns:
      employee_target_hours: dict {employee: target_hours}
      individual_unavailable: dict {employee: set(individual unavailable day numbers)}
      never_available: dict {employee: set(never available day-of-week indices)}
    """
    lower_bound = 1850 / BASE_HOURS  # ~4.4048
    upper_bound = 2000 / BASE_HOURS  # ~4.7619
    sample_attempt = 0
    while sample_attempt < 50:
        multipliers = [random.choice(allowed_multipliers) for _ in employees]
        total_target = BASE_HOURS * sum(multipliers)
        if lower_bound * BASE_HOURS <= total_target <= upper_bound * BASE_HOURS:
            break
        sample_attempt += 1
    if sample_attempt == 50:
        print("No sample data found meeting the target hours criteria after 50 attempts, proceeding anyways.")
    employee_target_hours = {e: BASE_HOURS * m for e, m in zip(employees, multipliers)}
    
    # For individual unavailable days, select 5 random days (0 to 69) for each employee.
    individual_unavailable = {e: set(random.sample(range(70), 5)) for e in employees}
    
    # Map day names to indices.
    day_name_to_index = {
        'monday': 0, 'tuesday': 1, 'wednesday': 2,
        'thursday': 3, 'friday': 4, 'saturday': 5, 'sunday': 6
    }
    # For never available days-of-week, assign one random day with 50% chance.
    never_available = {}
    for e in employees:
        if random.random() < 0.5:
            never_available[e] = {random.choice(list(day_name_to_index.values()))}
        else:
            never_available[e] = set()
    return employee_target_hours, individual_unavailable, never_available

def run_scheduling(employees, employee_target_hours, individual_unavailable, never_available, output_filename):
    """
    Builds the scheduling model, solves it (trying up to 10 times while extending margins),
    then creates 10 weekly schedule tables plus an Analytics sheet.
    Writes the output to an Excel file and returns its filename.
    """
    num_days = 70
    days = range(num_days)
    
    def day_type(d):
        return 'weekday' if d % 7 < 5 else 'weekend'
    
    # Define shifts and their durations.
    shifts_by_day = {
        'weekday': ['FA', 'FB', 'AA', 'AB'],  # Two morning (FA, FB) and two evening (AA, AB) shifts.
        'weekend': ['SA', 'SB']               # Two all-day shifts.
    }
    shift_duration = {
        'FA': 2.5, 'FB': 2.5,
        'AA': 6,   'AB': 6,
        'SA': 12.5, 'SB': 12.5
    }
    
    # Build employee availability dictionary.
    availability = {}
    for e in employees:
        availability[e] = {}
        for d in days:
            dow = d % 7
            if dow in never_available.get(e, set()):
                availability[e][d] = False
            elif d in individual_unavailable.get(e, set()):
                availability[e][d] = False
            else:
                availability[e][d] = True

    # Iteratively build and solve the scheduling model.
    scale = 10  # Used to convert fractional hours to integers.
    margin_lower = 0.67
    margin_upper = 0.73
    attempt = 1
    while attempt <= 10:
        print(f"Scheduling attempt {attempt}: Trying with target hour margins {margin_lower*100:.0f}% to {margin_upper*100:.0f}%")
        model = cp_model.CpModel()
        shift_vars = {}
        for e in employees:
            for d in days:
                for s in shifts_by_day[day_type(d)]:
                    shift_vars[(e, d, s)] = model.NewBoolVar(f'{e}_{d}_{s}')
                    
        # Constraint 1: Each employee can work at most one shift per day.
        for e in employees:
            for d in days:
                model.Add(sum(shift_vars[(e, d, s)] for s in shifts_by_day[day_type(d)]) <= 1)
                
        # Constraint 2: Only assign a shift if the employee is available on that day.
        for e in employees:
            for d in days:
                if not availability[e][d]:
                    for s in shifts_by_day[day_type(d)]:
                        model.Add(shift_vars[(e, d, s)] == 0)
                        
        # Constraint 3: Employee's scheduled hours must be between margin_lower and margin_upper of their target hours.
        for e in employees:
            total_hours = sum(shift_vars[(e, d, s)] * int(shift_duration[s] * scale)
                              for d in days for s in shifts_by_day[day_type(d)])
            model.Add(total_hours >= int(employee_target_hours[e] * margin_lower * scale))
            model.Add(total_hours <= int(employee_target_hours[e] * margin_upper * scale))
            
        # Constraint 4: Every shift must be filled.
        for d in days:
            for s in shifts_by_day[day_type(d)]:
                model.Add(sum(shift_vars[(e, d, s)] for e in employees) == 1)
                
        model.Maximize(sum(shift_vars.values()))
        solver = cp_model.CpSolver()
        status = solver.Solve(model)
        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            print(f"Solution found on attempt {attempt} with margins {margin_lower*100:.0f}% to {margin_upper*100:.0f}%.")
            break
        else:
            margin_lower -= 0.01
            margin_upper += 0.01
            attempt += 1

    if attempt > 10:
        print("No feasible solution found after 10 attempts. Exiting the scheduling loop.")
        print("Team and Availability Constraints:")
        for e in employees:
            print(f"Employee: {e}")
            print(f"  Target Hours: {employee_target_hours[e]}")
            print(f"  Individually Unavailable Days: {sorted(list(individual_unavailable.get(e, set())))}")
            print(f"  Regularly Unavailable (day-of-week indices): {sorted(list(never_available.get(e, set())))}")
        return None

    # Process the solution: Build schedule records.
    schedule_records = []
    for d in days:
        for e in employees:
            for s in shifts_by_day[day_type(d)]:
                if solver.Value(shift_vars[(e, d, s)]) == 1:
                    schedule_records.append({'Employee': e, 'Day': d, 'Shift': s, 'Hours': shift_duration[s]})
    schedule_df = pd.DataFrame(schedule_records)
    schedule_df = schedule_df.sort_values(by=['Employee', 'Day'])
    
    # Create 10 weekly tables (each week = 7 days).
    weekly_tables = {}
    for week in range(10):
        week_start = week * 7
        week_end = week_start + 7
        week_df = pd.DataFrame(index=employees, columns=[f'Day {d+1}' for d in range(week_start, week_end)])
        for e in employees:
            for d in range(week_start, week_end):
                if not availability[e][d]:
                    week_df.loc[e, f'Day {d+1}'] = 'Unavailable'
                else:
                    assign = schedule_df[(schedule_df['Employee'] == e) & (schedule_df['Day'] == d)]
                    if not assign.empty:
                        week_df.loc[e, f'Day {d+1}'] = assign.iloc[0]['Shift']
                    else:
                        week_df.loc[e, f'Day {d+1}'] = 'Off'
        weekly_tables[f'Week {week+1}'] = week_df

    # Compute analytics.
    schedule_df['Day_Type'] = schedule_df['Day'].apply(day_type)
    # Mapping for analytics.
    day_mapping = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday", 5: "Saturday", 6: "Sunday"}
    analytics = []
    for e in employees:
        emp_df = schedule_df[schedule_df['Employee'] == e]
        scheduled_hours = emp_df['Hours'].sum()
        target_hours = employee_target_hours[e]
        hours_percent = round((scheduled_hours / target_hours) * 100, 1) if target_hours > 0 else 0

        weekday_df = emp_df[emp_df['Day_Type'] == 'weekday']
        morning_shifts = weekday_df[weekday_df['Shift'].isin(['FA', 'FB'])].shape[0]
        evening_shifts = weekday_df[weekday_df['Shift'].isin(['AA', 'AB'])].shape[0]
        total_weekday = morning_shifts + evening_shifts
        pct_morning = round((morning_shifts / total_weekday * 100), 1) if total_weekday > 0 else 0
        pct_evening = round((evening_shifts / total_weekday * 100), 1) if total_weekday > 0 else 0

        shift_A_count = emp_df['Shift'].apply(lambda s: 1 if s[1]=='A' else 0).sum()
        shift_B_count = emp_df['Shift'].apply(lambda s: 1 if s[1]=='B' else 0).sum()
        total_shifts = emp_df.shape[0]
        pct_shift_A = round((shift_A_count / total_shifts * 100), 1) if total_shifts > 0 else 0
        pct_shift_B = round((shift_B_count / total_shifts * 100), 1) if total_shifts > 0 else 0

        weekday_count = emp_df[emp_df['Day_Type'] == 'weekday'].shape[0]
        weekend_count = emp_df[emp_df['Day_Type'] == 'weekend'].shape[0]
        pct_weekday = round((weekday_count / total_shifts * 100), 1) if total_shifts > 0 else 0
        pct_weekend = round((weekend_count / total_shifts * 100), 1) if total_shifts > 0 else 0

        multiplier = round(employee_target_hours[e] / BASE_HOURS, 2)
        regular_unavailable = sorted([day_mapping[d] for d in never_available.get(e, set())])
        individual_unavail = sorted(list(individual_unavailable.get(e, set())))
        analytics.append({
            'Employee': e,
            'Multiplier': multiplier,
            'Regularly Unavailable Days': ", ".join(regular_unavailable) if regular_unavailable else "",
            'Individually Unavailable Days': ", ".join(map(str, individual_unavail)) if individual_unavail else "",
            'Target Hours': target_hours,
            'Scheduled Hours': scheduled_hours,
            'Hours %': hours_percent,
            'Weekday Shifts': weekday_count,
            'Weekend Shifts': weekend_count,
            '% Weekday Shifts': pct_weekday,
            '% Weekend Shifts': pct_weekend,
            'Morning Shifts (Weekday)': morning_shifts,
            'Evening Shifts (Weekday)': evening_shifts,
            '% Morning Shifts (Weekday)': pct_morning,
            '% Evening Shifts (Weekday)': pct_evening,
            'Shift A Count': shift_A_count,
            'Shift B Count': shift_B_count,
            '% Shift A': pct_shift_A,
            '% Shift B': pct_shift_B
        })
    analytics_df = pd.DataFrame(analytics)
    
    # Write weekly tables and analytics to the Excel file.
    with pd.ExcelWriter(output_filename) as writer:
        for week_name, df in weekly_tables.items():
            df.to_excel(writer, sheet_name=week_name)
        analytics_df.to_excel(writer, sheet_name="Analytics")
    
    # Optionally, print summaries to console.
    for week_name, df in weekly_tables.items():
        print(f"\n{week_name}:")
        print(df)
    print("\nAnalytics Summary:")
    print(analytics_df)
    
    return output_filename

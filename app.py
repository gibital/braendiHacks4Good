import random
from ortools.sat.python import cp_model
import pandas as pd

# ---------------------------
# Prompt user for input data
# ---------------------------

# Updated allowed multipliers including additional values.
allowed_multipliers = [0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 1.0]

# First prompt: choose sample data or manual input.
choice = input("Type 'sample' to use a sample set of employees with randomized settings, or 'manual' to manually enter them: ").strip().lower()

if choice == 'sample':
    print("Using sample data with eight employees and target hours based on 420.")
    # Sample employee list of 8 employees.
    employees = ["Alice", "Bob", "Charlie", "David", "Eva", "Frank", "Grace", "Henry"]
    # Generate multipliers until the total target hours fall between 1850 and 2000.
    lower_bound = 1850 / 420  # ≈ 4.4048
    upper_bound = 2000 / 420  # ≈ 4.7619
    while True:
        multipliers = [random.choice(allowed_multipliers) for _ in employees]
        total_target = 420 * sum(multipliers)
        if lower_bound * 420 <= total_target <= upper_bound * 420:
            break
    employee_target_hours = {e: 420 * m for e, m in zip(employees, multipliers)}
    
    # For individual unavailable days, randomly select 5 days (from 0 to 69) for each employee.
    individual_unavailable = {e: set(random.sample(range(70), 5)) for e in employees}
    
    # Map day names to indices.
    day_name_to_index = {
        'monday': 0,
        'tuesday': 1,
        'wednesday': 2,
        'thursday': 3,
        'friday': 4,
        'saturday': 5,
        'sunday': 6
    }
    # For never available days-of-week, assign one random day with 50% chance or leave empty.
    never_available = {}
    for e in employees:
        if random.random() < 0.5:
            never_available[e] = {random.choice(list(day_name_to_index.values()))}
        else:
            never_available[e] = set()
else:
    # Manual input mode.
    # 1. Employee Names (comma-separated)
    employee_input = input("Enter employee names separated by commas: ")
    employees = [e.strip() for e in employee_input.split(",") if e.strip()]

    # 2. Multipliers: For each employee, prompt for a multiplier.
    employee_target_hours = {}
    for e in employees:
        multiplier_input = input(f"Enter multiplier for {e} (allowed values {allowed_multipliers}, or press Enter for a random value): ")
        if multiplier_input.strip():
            try:
                multiplier = float(multiplier_input.strip())
                if multiplier not in allowed_multipliers:
                    print(f"Multiplier not in allowed set; using random value for {e}.")
                    multiplier = random.choice(allowed_multipliers)
            except Exception as ex:
                print(f"Error reading multiplier for {e}; using random value.")
                multiplier = random.choice(allowed_multipliers)
        else:
            multiplier = random.choice(allowed_multipliers)
        employee_target_hours[e] = 840 * multiplier  # target hours for the 70-day period

    # 3. Unavailable Days: For each employee, prompt for individual unavailable days (0-69)
    individual_unavailable = {}
    for e in employees:
        unavailable_input = input(f"Enter individual unavailable days for {e} (comma-separated day numbers between 0 and 69), or press Enter if none: ")
        if unavailable_input.strip():
            try:
                days_list = [int(x.strip()) for x in unavailable_input.split(",") if x.strip().isdigit()]
            except Exception as ex:
                print(f"Error processing unavailable days for {e}; assuming none.")
                days_list = []
        else:
            days_list = []
        individual_unavailable[e] = set(days_list)

    # 4. Never Available Days-of-Week: For each employee, prompt for days of the week when they are never available.
    day_name_to_index = {
        'monday': 0,
        'tuesday': 1,
        'wednesday': 2,
        'thursday': 3,
        'friday': 4,
        'saturday': 5,
        'sunday': 6
    }
    never_available = {}
    for e in employees:
        never_input = input(f"Enter days of the week when {e} is NEVER available (e.g., Monday, Tuesday), or press Enter if none: ")
        if never_input.strip():
            days_names = [x.strip().lower() for x in never_input.split(",") if x.strip()]
            indices = set()
            for name in days_names:
                if name in day_name_to_index:
                    indices.add(day_name_to_index[name])
                else:
                    print(f"Unrecognized day name '{name}' for {e}; ignoring.")
            never_available[e] = indices
        else:
            never_available[e] = set()

# Prompt for the output filename prefix.
filename_prefix = input("Enter the output filename prefix (this will precede '_weekly_schedule.xlsx'): ").strip()
if not filename_prefix:
    filename_prefix = "weekly_schedule"
output_filename = f"outputs/{filename_prefix}_weekly_schedule.xlsx"

# ---------------------------
# Define problem parameters
# ---------------------------
num_days = 70
days = range(num_days)

def day_type(d):
    # Monday=0, Tuesday=1, ... Sunday=6
    dow = d % 7
    return 'weekday' if dow < 5 else 'weekend'

# Define shifts by day type.
shifts_by_day = {
    'weekday': ['FA', 'FB', 'AA', 'AB'],  # Two morning, two evening shifts.
    'weekend': ['SA', 'SB']               # Two all-day shifts.
}

# Define shift durations in hours.
shift_duration = {
    'FA': 2.5, 'FB': 2.5,
    'AA': 6,   'AB': 6,
    'SA': 12.5, 'SB': 12.5
}

# -----------------------------------------------
# Build employee availability dictionary.
# -----------------------------------------------
availability = {}
for e in employees:
    availability[e] = {}
    for d in days:
        dow = d % 7
        if dow in never_available[e]:
            availability[e][d] = False
        elif d in individual_unavailable[e]:
            availability[e][d] = False
        else:
            availability[e][d] = True

# ---------------------------
# Iteratively build and solve the model with target hours constraint.
# ---------------------------
scale = 10  # To convert fractional hours to integer constraints.
margin_lower = 0.67
margin_upper = 0.73
attempt = 1
solution_found = False

while True:
    print(f"Attempt {attempt}: Trying with target hour margins {margin_lower*100:.0f}% to {margin_upper*100:.0f}%")
    
    # Build a new model for this attempt.
    model = cp_model.CpModel()
    
    # Decision variables: shift_vars[(e, d, s)] indicates if employee e is assigned shift s on day d.
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
    
    # Constraint 3: Employee target hours constraint with lower and upper bounds.
    for e in employees:
        total_hours = sum(shift_vars[(e, d, s)] * int(shift_duration[s] * scale)
                          for d in days for s in shifts_by_day[day_type(d)])
        model.Add(total_hours >= int(employee_target_hours[e] * margin_lower * scale))
        model.Add(total_hours <= int(employee_target_hours[e] * margin_upper * scale))
    
    # Constraint 4: Every shift must be filled.
    for d in days:
        for s in shifts_by_day[day_type(d)]:
            model.Add(sum(shift_vars[(e, d, s)] for e in employees) == 1)
    
    # (Optional) Objective: Maximize total number of assigned shifts.
    model.Maximize(sum(shift_vars.values()))
    
    # Solve the model.
    solver = cp_model.CpSolver()
    status = solver.Solve(model)
    
    if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        print(f"Solution found on attempt {attempt} with margins {margin_lower*100:.0f}% to {margin_upper*100:.0f}%.")
        solution_found = True
        break
    else:
        print("No solution found with these margins. Extending margins by 1% on both sides and trying again.\n")
        margin_lower -= 0.01
        margin_upper += 0.01
        attempt += 1

# ---------------------------
# Process the solution.
# ---------------------------
# Build schedule records with shift duration.
schedule_records = []
for d in days:
    for e in employees:
        for s in shifts_by_day[day_type(d)]:
            if solver.Value(shift_vars[(e, d, s)]) == 1:
                schedule_records.append({'Employee': e, 'Day': d, 'Shift': s, 'Hours': shift_duration[s]})
                
schedule_df = pd.DataFrame(schedule_records)
schedule_df = schedule_df.sort_values(by=['Employee', 'Day'])

# Create 10 weekly tables (each week has 7 days).
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

# ---------------------------
# Analytics Computation
# ---------------------------
# Add a column to schedule_df to indicate the day type.
schedule_df['Day_Type'] = schedule_df['Day'].apply(day_type)

analytics = []
for e in employees:
    emp_df = schedule_df[schedule_df['Employee'] == e]
    scheduled_hours = emp_df['Hours'].sum()
    target_hours = employee_target_hours[e]
    hours_percent = (scheduled_hours / target_hours) * 100 if target_hours > 0 else 0

    # Weekday shifts: morning (FA/FB) vs. evening (AA/AB).
    weekday_df = emp_df[emp_df['Day_Type'] == 'weekday']
    morning_shifts = weekday_df[weekday_df['Shift'].isin(['FA', 'FB'])].shape[0]
    evening_shifts = weekday_df[weekday_df['Shift'].isin(['AA', 'AB'])].shape[0]
    total_weekday = morning_shifts + evening_shifts
    pct_morning = (morning_shifts / total_weekday * 100) if total_weekday > 0 else 0
    pct_evening = (evening_shifts / total_weekday * 100) if total_weekday > 0 else 0

    # Breakdown based on the second letter (A vs. B) for all shifts.
    shift_A_count = emp_df['Shift'].apply(lambda s: 1 if s[1] == 'A' else 0).sum()
    shift_B_count = emp_df['Shift'].apply(lambda s: 1 if s[1] == 'B' else 0).sum()
    total_shifts = emp_df.shape[0]
    pct_shift_A = (shift_A_count / total_shifts * 100) if total_shifts > 0 else 0
    pct_shift_B = (shift_B_count / total_shifts * 100) if total_shifts > 0 else 0

    # Weekend vs. Weekday shift counts.
    weekday_count = emp_df[emp_df['Day_Type'] == 'weekday'].shape[0]
    weekend_count = emp_df[emp_df['Day_Type'] == 'weekend'].shape[0]
    pct_weekday = (weekday_count / total_shifts * 100) if total_shifts > 0 else 0
    pct_weekend = (weekend_count / total_shifts * 100) if total_shifts > 0 else 0

    analytics.append({
        'Employee': e,
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

# ---------------------------
# Write all sheets to the Excel file.
# ---------------------------
with pd.ExcelWriter(output_filename) as writer:
    for week_name, df in weekly_tables.items():
        df.to_excel(writer, sheet_name=week_name)
    analytics_df.to_excel(writer, sheet_name="Analytics")

# Print results to console.
for week_name, df in weekly_tables.items():
    print(f"\n{week_name}:")
    print(df)
print("\nAnalytics Summary:")
print(analytics_df)
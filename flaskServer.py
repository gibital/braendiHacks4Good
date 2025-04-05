# app.py
import os
import tempfile
from flask import Flask, render_template, request, send_file, flash, redirect, url_for
from scheduling import run_scheduling, BASE_HOURS
app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        filename_prefix = request.form.get('filename_prefix') or "weekly_schedule"
        output_filename = os.path.join(tempfile.gettempdir(), f"{filename_prefix}_weekly_schedule.xlsx")
        
        # Always use manual (real) data.
        employees = request.form.getlist('employee_names[]')
        multipliers = request.form.getlist('multipliers[]')
        employee_target_hours = {}
        individual_unavailable = {}
        never_available = {}
        for i, (name, mult) in enumerate(zip(employees, multipliers), start=1):
            try:
                multiplier = float(mult)
            except:
                multiplier = 0
            employee_target_hours[name] = BASE_HOURS * multiplier
            # Retrieve regularly unavailable days from multi-select.
            reg = request.form.getlist(f'regular_unavailable_{i}[]')
            never_available[name] = set(int(x) for x in reg) if reg else set()
            # Retrieve individual unavailable days from text field.
            indiv = request.form.get(f'individual_unavailable_{i}')
            if indiv:
                individual_unavailable[name] = set(int(x.strip()) for x in indiv.split(',') if x.strip().isdigit())
            else:
                individual_unavailable[name] = set()
        
        result_file = run_scheduling(employees, employee_target_hours, individual_unavailable, never_available, output_filename)
        if result_file:
            return send_file(result_file, as_attachment=True)
        else:
            flash("No feasible solution found after 10 attempts. Please adjust your team configuration.", "danger")
            return redirect(url_for('index'))
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)
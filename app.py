import os
from flask import Flask, render_template, request, redirect, url_for, flash, get_flashed_messages
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Enum
from datetime import datetime
import sqlite3
from sqlalchemy import func, and_, or_
from datetime import datetime, date
from flask import send_file
import pandas as pd
from io import BytesIO

app = Flask(__name__)
app.secret_key = 'fleet_management_secret_key'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'fleet.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Enums for option fields
VEHICLE_TYPES = ('Pickup', 'V8', 'Hardtop', 'Other')
FUEL_TYPES = ('Diesel', 'Benzin', 'Hybrid', 'Electric')
ASSIGNMENT_TYPES = ('Project', 'Region', 'Center Office', 'Other')
INSURANCE_TYPES = ('Fully Insured', 'Partial')
SAFETY_TYPES = ('Safe', 'Fair', 'Not Safe')
MAINTENANCE_CENTERS = ('EEP', 'Moenco', 'Other')
YES_NO = ('Yes', 'No')

class Vehicle(db.Model):
    plate_number = db.Column(db.String(20), primary_key=True)
    chasis = db.Column(db.String(50), unique=True, nullable=False)
    vehicle_type = db.Column(Enum(*VEHICLE_TYPES, name='vehicle_types'))
    make = db.Column(db.String(50))
    model = db.Column(db.String(50))
    year = db.Column(db.String(4))
    fuel_type = db.Column(Enum(*FUEL_TYPES, name='fuel_types'))
    fuel_capacity = db.Column(db.Float)
    fuel_consumption = db.Column(db.Float)
    loading_capacity = db.Column(db.String(100))
    assigned_for = db.Column(Enum(*ASSIGNMENT_TYPES, name='assignment_types'))
    
    # Relationships
    compliance = db.relationship('Compliance', backref='vehicle', uselist=False)
    maintenance = db.relationship('Maintenance', backref='vehicle')
    assignments = db.relationship('Assignment', backref='vehicle')

class Driver(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    id_number = db.Column(db.String(50), unique=True)
    phone = db.Column(db.String(15))
    reporting_to = db.Column(db.String(100))
    
    assignments = db.relationship('Assignment', backref='driver')

class Compliance(db.Model):
    plate_number = db.Column(db.String(20), db.ForeignKey('vehicle.plate_number'), primary_key=True)
    insurance_type = db.Column(Enum(*INSURANCE_TYPES, name='insurance_types'))
    insurance_date = db.Column(db.Date)
    yearly_inspection = db.Column(Enum(*YES_NO, name='yes_no_types'))
    inspection_date = db.Column(db.Date)
    safety_audit = db.Column(Enum(*SAFETY_TYPES, name='safety_types'))
    utilization_history = db.Column(db.Text)
    accident_history = db.Column(db.Text)

class Maintenance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    plate_number = db.Column(db.String(20), db.ForeignKey('vehicle.plate_number'))
    last_service_km = db.Column(db.Integer)
    last_service_date = db.Column(db.Date)
    next_service_km = db.Column(db.Integer)
    next_service_date = db.Column(db.Date)
    maintenance_center = db.Column(Enum(*MAINTENANCE_CENTERS, name='maintenance_centers'))

class Assignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    plate_number = db.Column(db.String(20), db.ForeignKey('vehicle.plate_number'))
    driver_id = db.Column(db.Integer, db.ForeignKey('driver.id'))
    work_place = db.Column(db.String(100))
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    gps_position = db.Column(db.String(50))
    geofence_violations = db.Column(db.Integer)

def get_dashboard_counts():
    conn = sqlite3.connect('fleet.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM vehicle")
    vehicle_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM driver")
    driver_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM assignment WHERE end_date IS NULL")
    assignment_count = cursor.fetchone()[0]
    
    cursor.execute('''
        SELECT v.plate_number, v.make, v.model, m.next_service_date, m.maintenance_center 
        FROM maintenance m
        JOIN vehicle v ON m.plate_number = v.plate_number
        WHERE m.next_service_date <= date('now', '+7 days')
        ORDER BY m.next_service_date
        LIMIT 5
    ''')
    maintenance_due = cursor.fetchall()
    
    cursor.execute('''
        SELECT v.plate_number, v.make, v.model, 
               CASE 
                   WHEN c.yearly_inspection = 'No' THEN 'Inspection Missing'
                   WHEN c.inspection_date < date('now', '-1 year') THEN 'Inspection Expired'
                   WHEN c.insurance_date < date('now', '-1 year') THEN 'Insurance Expired'
                   ELSE 'Unknown Issue'
               END AS issue_type
        FROM compliance c
        JOIN vehicle v ON c.plate_number = v.plate_number
        WHERE c.yearly_inspection = 'No' 
            OR c.inspection_date < date('now', '-1 year')
            OR c.insurance_date < date('now', '-1 year')
        LIMIT 5
    ''')
    compliance_issues = cursor.fetchall()
    
    conn.close()
    
    return vehicle_count, driver_count, assignment_count, maintenance_due, compliance_issues

@app.before_request
def create_tables():
    db.create_all()

@app.route('/')
def index():
    counts = get_dashboard_counts()
    return render_template('index.html', 
                           vehicle_count=counts[0],
                           driver_count=counts[1],
                           assignment_count=counts[2],
                           maintenance_due=counts[3],
                           compliance_issues=counts[4])

# VEHICLE MANAGEMENT
@app.route('/vehicles', methods=['GET', 'POST'])
def manage_vehicles():
    if request.method == 'POST':
        plate_number = request.form['plate_number'].upper().strip()
        
        # Check if plate number already exists
        if Vehicle.query.get(plate_number):
            flash('Plate number already exists!', 'danger')
            return redirect(url_for('manage_vehicles'))
        
        new_vehicle = Vehicle(
            plate_number=plate_number,
            chasis=request.form['chasis'],
            vehicle_type=request.form['vehicle_type'],
            make=request.form['make'],
            model=request.form['model'],
            year=request.form['year'],
            fuel_type=request.form['fuel_type'],
            fuel_capacity=float(request.form['fuel_capacity'] or 0),
            fuel_consumption=float(request.form['fuel_consumption'] or 0),
            loading_capacity=request.form['loading_capacity'],
            assigned_for=request.form['assigned_for']
        )
        db.session.add(new_vehicle)
        db.session.commit()
        flash('Vehicle added successfully!', 'success')
        return redirect(url_for('manage_vehicles'))
    
    vehicles = Vehicle.query.all()
    return render_template('vehicles.html', vehicles=vehicles)

@app.route('/vehicles/<plate_number>', methods=['GET', 'POST'])
def edit_vehicle(plate_number):
    vehicle = Vehicle.query.get_or_404(plate_number)
    
    if request.method == 'POST':
        vehicle.chasis = request.form['chasis']
        vehicle.vehicle_type = request.form['vehicle_type']
        vehicle.make = request.form['make']
        vehicle.model = request.form['model']
        vehicle.year = request.form['year']
        vehicle.fuel_type = request.form['fuel_type']
        vehicle.fuel_capacity = float(request.form['fuel_capacity'] or 0)
        vehicle.fuel_consumption = float(request.form['fuel_consumption'] or 0)
        vehicle.loading_capacity = request.form['loading_capacity']
        vehicle.assigned_for = request.form['assigned_for']
        db.session.commit()
        flash('Vehicle updated successfully!', 'success')
        return redirect(url_for('manage_vehicles'))
    
    return render_template('edit_vehicle.html', vehicle=vehicle)

@app.route('/vehicles/delete/<plate_number>')
def delete_vehicle(plate_number):
    vehicle = Vehicle.query.get_or_404(plate_number)
    db.session.delete(vehicle)
    db.session.commit()
    flash('Vehicle deleted successfully!', 'success')
    return redirect(url_for('manage_vehicles'))

# DRIVER MANAGEMENT
@app.route('/drivers', methods=['GET', 'POST'])
def manage_drivers():
    if request.method == 'POST':
        phone = request.form['phone'].strip()
        # Validate Ethiopian phone number
        #if not phone.startswith('+251'):
            #flash('Phone must start with +251', 'danger')
        #return redirect(url_for('manage_drivers'))
        
        new_driver = Driver(
            name=request.form['name'],
            id_number=request.form['id_number'],
            phone=phone,
            reporting_to=request.form['reporting_to']
        )
        db.session.add(new_driver)
        db.session.commit()
        flash('Driver added successfully!', 'success')
        return redirect(url_for('manage_drivers'))
    
    drivers = Driver.query.all()
    return render_template('drivers.html', drivers=drivers)

@app.route('/drivers/<int:driver_id>', methods=['GET', 'POST'])
def edit_driver(driver_id):
    driver = Driver.query.get_or_404(driver_id)
    
    if request.method == 'POST':
        phone = request.form['phone'].strip()
        #if not phone.startswith('+251'):
            #flash('Phone must start with +251', 'danger')
        #return redirect(url_for('edit_driver', driver_id=driver_id))
            
        driver.name = request.form['name']
        driver.id_number = request.form['id_number']
        driver.phone = phone
        driver.reporting_to = request.form['reporting_to']
        db.session.commit()
        flash('Driver updated successfully!', 'success')
        return redirect(url_for('manage_drivers'))
    
    return render_template('edit_driver.html', driver=driver)

@app.route('/drivers/delete/<int:driver_id>')
def delete_driver(driver_id):
    driver = Driver.query.get_or_404(driver_id)
    db.session.delete(driver)
    db.session.commit()
    flash('Driver deleted successfully!', 'success')
    return redirect(url_for('manage_drivers'))

# ASSIGNMENT MANAGEMENT
@app.route('/assignments', methods=['GET', 'POST'])
def manage_assignments():
    if request.method == 'POST':
        plate_number = request.form['plate_number'].upper().strip()
        driver_id = request.form['driver_id']
        
        # Check if vehicle exists
        if not Vehicle.query.get(plate_number):
            flash('Vehicle with this plate number does not exist!', 'danger')
            return redirect(url_for('manage_assignments'))
        
        new_assignment = Assignment(
            plate_number=plate_number,
            driver_id=driver_id,
            work_place=request.form['work_place'],
            start_date=datetime.strptime(request.form['start_date'], '%Y-%m-%d').date(),
            end_date=datetime.strptime(request.form['end_date'], '%Y-%m-%d').date() if request.form['end_date'] else None,
            gps_position=request.form['gps_position'],
            geofence_violations=int(request.form['geofence_violations'] or 0)
        )
        db.session.add(new_assignment)
        db.session.commit()
        flash('Assignment created successfully!', 'success')
        return redirect(url_for('manage_assignments'))
    
    assignments = Assignment.query.all()
    vehicles = Vehicle.query.all()
    drivers = Driver.query.all()
    return render_template('assignments.html', assignments=assignments, vehicles=vehicles, drivers=drivers)

@app.route('/assignments/<int:assignment_id>', methods=['GET', 'POST'])
def edit_assignment(assignment_id):
    assignment = Assignment.query.get_or_404(assignment_id)
    
    if request.method == 'POST':
        plate_number = request.form['plate_number'].upper().strip()
        
        # Check if vehicle exists
        if not Vehicle.query.get(plate_number):
            flash('Vehicle with this plate number does not exist!', 'danger')
            return redirect(url_for('edit_assignment', assignment_id=assignment_id))
            
        assignment.plate_number = plate_number
        assignment.driver_id = request.form['driver_id']
        assignment.work_place = request.form['work_place']
        assignment.start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d').date()
        assignment.end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d').date() if request.form['end_date'] else None
        assignment.gps_position = request.form['gps_position']
        assignment.geofence_violations = int(request.form['geofence_violations'] or 0)
        db.session.commit()
        flash('Assignment updated successfully!', 'success')
        return redirect(url_for('manage_assignments'))
    
    vehicles = Vehicle.query.all()
    drivers = Driver.query.all()
    return render_template('edit_assignment.html', assignment=assignment, vehicles=vehicles, drivers=drivers)

@app.route('/assignments/delete/<int:assignment_id>')
def delete_assignment(assignment_id):
    assignment = Assignment.query.get_or_404(assignment_id)
    db.session.delete(assignment)
    db.session.commit()
    flash('Assignment deleted successfully!', 'success')
    return redirect(url_for('manage_assignments'))

# COMPLIANCE MANAGEMENT
@app.route('/compliance/<plate_number>', methods=['GET', 'POST'])
def manage_compliance(plate_number):
    vehicle = Vehicle.query.get_or_404(plate_number)
    compliance = Compliance.query.get(plate_number)
    
    if not compliance:
        compliance = Compliance(plate_number=plate_number)
    
    if request.method == 'POST':
        compliance.insurance_type = request.form['insurance_type']
        compliance.insurance_date = datetime.strptime(request.form['insurance_date'], '%Y-%m-%d').date() if request.form['insurance_date'] else None
        compliance.yearly_inspection = request.form['yearly_inspection']
        compliance.inspection_date = datetime.strptime(request.form['inspection_date'], '%Y-%m-%d').date() if request.form['inspection_date'] else None
        compliance.safety_audit = request.form['safety_audit']
        compliance.utilization_history = request.form['utilization_history']
        compliance.accident_history = request.form['accident_history']
        
        if not vehicle.compliance:
            db.session.add(compliance)
        db.session.commit()
        flash('Compliance data saved!', 'success')
        return redirect(url_for('manage_compliance', plate_number=plate_number))
    
    return render_template('compliance.html', vehicle=vehicle, compliance=compliance)

# MAINTENANCE MANAGEMENT
@app.route('/maintenance/<plate_number>', methods=['GET', 'POST'])
def manage_maintenance(plate_number):
    vehicle = Vehicle.query.get_or_404(plate_number)
    
    if request.method == 'POST':
        new_maintenance = Maintenance(
            plate_number=plate_number,
            last_service_km=int(request.form['last_service_km'] or 0),
            last_service_date=datetime.strptime(request.form['last_service_date'], '%Y-%m-%d').date(),
            next_service_km=int(request.form['next_service_km'] or 0),
            next_service_date=datetime.strptime(request.form['next_service_date'], '%Y-%m-%d').date(),
            maintenance_center=request.form['maintenance_center']
        )
        db.session.add(new_maintenance)
        db.session.commit()
        flash('Maintenance record added!', 'success')
        return redirect(url_for('manage_maintenance', plate_number=plate_number))
    
    maintenance_records = Maintenance.query.filter_by(plate_number=plate_number).all()
    return render_template('maintenance.html', vehicle=vehicle, maintenance_records=maintenance_records)

@app.route('/maintenance/delete/<int:record_id>')
def delete_maintenance(record_id):
    record = Maintenance.query.get_or_404(record_id)
    plate_number = record.plate_number
    db.session.delete(record)
    db.session.commit()
    flash('Maintenance record deleted!', 'success')
    return redirect(url_for('manage_maintenance', plate_number=plate_number))

# Reporting Routes with proper imports and error handling

@app.route('/reports/assignment-summary')
def assignment_summary_report():
    try:
        assignment_counts = db.session.query(
            Vehicle.assigned_for,
            func.count(Vehicle.plate_number)
        ).group_by(Vehicle.assigned_for).all()
        
        ongoing_assignments = Assignment.query.filter(
            or_(
                Assignment.end_date.is_(None),
                Assignment.end_date >= date.today()
            )
        ).count()
        
        active_assignments = db.session.query(Assignment.plate_number).filter(
            or_(
                Assignment.end_date.is_(None),
                Assignment.end_date >= date.today()
            )
        )
        unassigned_vehicles = db.session.query(Vehicle).filter(
            ~Vehicle.plate_number.in_(active_assignments)
        ).count()
        
        return render_template(
            'reports/assignment_summary.html',
            assignment_counts=assignment_counts,
            ongoing_assignments=ongoing_assignments,
            unassigned_vehicles=unassigned_vehicles,
            now=datetime.now()
        )
    except Exception as e:
        flash(f'Error generating assignment summary: {str(e)}', 'danger')
        return redirect(url_for('generate_report'))

@app.route('/reports/unassigned-vehicles')
def unassigned_vehicles_report():
    try:
        active_assignments = db.session.query(Assignment.plate_number).filter(
            or_(
                Assignment.end_date.is_(None),
                Assignment.end_date >= date.today()
            )
        )
        vehicles = db.session.query(Vehicle).filter(
            ~Vehicle.plate_number.in_(active_assignments)
        ).all()
        
        return render_template(
            'reports/unassigned_vehicles.html',
            vehicles=vehicles,
            now=datetime.now()
        )
    except Exception as e:
        flash(f'Error generating unassigned vehicles report: {str(e)}', 'danger')
        return redirect(url_for('generate_report'))

@app.route('/reports/driver-assignments')
def driver_assignments_report():
    try:
        drivers = db.session.query(Driver, Assignment).outerjoin(
            Assignment,
            and_(
                Assignment.driver_id == Driver.id,
                or_(
                    Assignment.end_date.is_(None),
                    Assignment.end_date >= date.today()
                )
            )
        ).all()
        
        return render_template(
            'reports/driver_assignments.html',
            drivers=drivers,
            now=datetime.now()
        )
    except Exception as e:
        flash(f'Error generating driver assignments report: {str(e)}', 'danger')
        return redirect(url_for('generate_report'))

# Update the existing generate_report route to handle both basic and advanced
@app.route('/report', methods=['GET', 'POST'])
def generate_report():
    if request.method == 'POST' and request.form.get('report_type') == 'basic':
        report_type = request.form['search_type']
        identifier = request.form['identifier'].strip()
        
        if report_type == 'plate':
            vehicle = Vehicle.query.get(identifier.upper())
            if vehicle:
                return render_template('vehicle_report.html', vehicle=vehicle)
            flash(f'No vehicle found with plate number: {identifier}', 'danger')
        
        elif report_type == 'driver_name':
            driver = Driver.query.filter(Driver.name.ilike(f'%{identifier}%')).first()
            if driver:
                return render_template('driver_report.html', driver=driver)
            flash(f'No driver found with name: {identifier}', 'danger')
        
        elif report_type == 'driver_id':
            driver = Driver.query.filter_by(id_number=identifier).first()
            if driver:
                return render_template('driver_report.html', driver=driver)
            flash(f'No driver found with ID: {identifier}', 'danger')
    
    return render_template('report.html')

@app.route('/reports/export/assignment-summary')
def export_assignment_summary():
    try:
        # Get the same data as the HTML report
        assignment_counts = db.session.query(
            Vehicle.assigned_for,
            func.count(Vehicle.plate_number)
        ).group_by(Vehicle.assigned_for).all()
        
        # Create a DataFrame
        df = pd.DataFrame(assignment_counts, columns=['Assignment Type', 'Vehicle Count'])
        
        # Create Excel file in memory
        output = BytesIO()
        writer = pd.ExcelWriter(output, engine='xlsxwriter')
        df.to_excel(writer, sheet_name='Assignment Summary', index=False)
        
        # Add summary stats
        stats = pd.DataFrame({
            'Metric': ['Ongoing Assignments', 'Unassigned Vehicles'],
            'Count': [
                Assignment.query.filter(or_(Assignment.end_date.is_(None), Assignment.end_date >= date.today())).count(),
                db.session.query(Vehicle).filter(~Vehicle.plate_number.in_(
                    db.session.query(Assignment.plate_number).filter(
                        or_(Assignment.end_date.is_(None), Assignment.end_date >= date.today()))
                )).count()
            ]
        })
        stats.to_excel(writer, sheet_name='Summary Stats', index=False)
        
        writer.close()
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            download_name=f'assignment_summary_{datetime.now().strftime("%Y%m%d")}.xlsx',
            as_attachment=True
        )
    except Exception as e:
        flash(f'Error exporting report: {str(e)}', 'danger')
        return redirect(url_for('generate_report'))
        
@app.route('/reports/export/unassigned-vehicles')
def export_unassigned_vehicles():
    try:
        vehicles = db.session.query(Vehicle).filter(
            ~Vehicle.plate_number.in_(
                db.session.query(Assignment.plate_number).filter(
                    or_(Assignment.end_date.is_(None), Assignment.end_date >= date.today())
            ))
        ).all()
        
        # Convert to list of dicts
        data = [{
            'Plate Number': v.plate_number,
            'Make': v.make,
            'Model': v.model,
            'Type': v.vehicle_type,
            'Assigned For': v.assigned_for
        } for v in vehicles]
        
        df = pd.DataFrame(data)
        
        output = BytesIO()
        df.to_excel(output, sheet_name='Unassigned Vehicles', index=False)
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            download_name=f'unassigned_vehicles_{datetime.now().strftime("%Y%m%d")}.xlsx',
            as_attachment=True
        )
    except Exception as e:
        flash(f'Error exporting report: {str(e)}', 'danger')
        return redirect(url_for('generate_report'))

@app.route('/reports/export/driver-assignments')
def export_driver_assignments():
    try:
        drivers = db.session.query(Driver, Assignment).outerjoin(
            Assignment,
            and_(
                Assignment.driver_id == Driver.id,
                or_(
                    Assignment.end_date.is_(None),
                    Assignment.end_date >= date.today()
                )
            )
        ).all()
        
        data = [{
            'Driver Name': d.name,
            'ID Number': d.id_number,
            'Phone': d.phone,
            'Assigned Vehicle': f"{a.vehicle.plate_number} ({a.vehicle.make})" if a else 'Not assigned',
            'Work Place': a.work_place if a else '-',
            'Start Date': a.start_date.strftime('%Y-%m-%d') if a and a.start_date else '-',
            'End Date': a.end_date.strftime('%Y-%m-%d') if a and a.end_date else '-'
        } for d, a in drivers]
        
        df = pd.DataFrame(data)
        
        output = BytesIO()
        df.to_excel(output, sheet_name='Driver Assignments', index=False)
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            download_name=f'driver_assignments_{datetime.now().strftime("%Y%m%d")}.xlsx',
            as_attachment=True
        )
    except Exception as e:
        flash(f'Error exporting report: {str(e)}', 'danger')
        return redirect(url_for('generate_report'))        

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=1000, debug=True)

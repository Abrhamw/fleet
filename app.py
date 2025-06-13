import os
import streamlit as st
#from streamlit_option_menu import option_menu
import sqlite3
from sqlalchemy import create_engine, Enum, func, and_, or_, Column, String, Integer, Float, Date, Text, ForeignKey
from sqlalchemy.orm import sessionmaker, scoped_session, relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime, date
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from passlib.hash import pbkdf2_sha256
import uuid
from io import BytesIO

# Ensure database directory exists
basedir = os.path.abspath(os.path.dirname(__file__))
db_dir = os.path.join(basedir, 'fleetgk')
os.makedirs(db_dir, exist_ok=True)  # Create directory if it doesn't exist
db_path = os.path.join(db_dir, 'fleet.db')

# Use environment variable for PythonAnywhere or default to local path
if os.getenv('PYTHONANYWHERE') == 'true':
    db_path = '/home/abrahamw/desktop/ims/fleetgk/fleet.db'
    db_uri = f'sqlite:///{db_path}'
else:
    db_uri = f'sqlite:///{db_path}'

# Initialize SQLAlchemy
try:
    engine = create_engine(db_uri, echo=False)
    Session = scoped_session(sessionmaker(bind=engine))
    Base = declarative_base()
except Exception as e:
    st.error(f"Failed to initialize database: {str(e)}")
    st.stop()

# Enums for database fields
VEHICLE_TYPES = ('Pickup', 'Land Cruiser', 'Prado', 'V8', 'Hardtop', 'Minibus', 'Bus', 'Crane', 'ISUZU FSR', 'Other')
FUEL_TYPES = ('Diesel', 'Benzin', 'Hybrid', 'Electric')
ASSIGNMENT_TYPES = ('Program Office I', 'Program Office II', 'Program Office III', 'Program Office IV', 'Central I Region', 'Central II Region', 'Central III Region', 'North Region', 'North East I Region', 'North East II Region', 'North West Region', 'West Region', 'South West Region', 'South I Region', 'South II Region', 'East I Region', 'East II Region', 'Region Coordination Office', 'Load Dispatch Center', 'Other')
INSURANCE_TYPES = ('Fully Insured', 'Partial')
SAFETY_TYPES = ('Safe', 'Fair', 'Not Safe')
MAINTENANCE_CENTERS = ('EEP', 'Moenco', 'Other')
YES_NO = ('Yes', 'No')

# Database Models
class Vehicle(Base):
    __tablename__ = 'vehicle'
    plate_number = Column(String(20), primary_key=True)
    chasis = Column(String(50), unique=True, nullable=False)
    vehicle_type = Column(Enum(*VEHICLE_TYPES, name='vehicle_types'))
    make = Column(String(50))
    model = Column(String(50))
    year = Column(String(4))
    fuel_type = Column(Enum(*FUEL_TYPES, name='fuel_types'))
    fuel_capacity = Column(Float)
    fuel_consumption = Column(Float)
    loading_capacity = Column(String(100))
    assigned_for = Column(Enum(*ASSIGNMENT_TYPES, name='assignment_types'))
    compliance = relationship('Compliance', backref='vehicle', uselist=False)
    maintenance = relationship('Maintenance', backref='vehicle')
    assignments = relationship('Assignment', backref='vehicle')

class Driver(Base):
    __tablename__ = 'driver'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    id_number = Column(String(50), unique=True)
    phone = Column(String(15))
    reporting_to = Column(String(100))
    assignments = relationship('Assignment', backref='driver')

class Compliance(Base):
    __tablename__ = 'compliance'
    plate_number = Column(String(20), ForeignKey('vehicle.plate_number'), primary_key=True)
    insurance_type = Column(Enum(*INSURANCE_TYPES, name='insurance_types'))
    insurance_date = Column(Date)
    yearly_inspection = Column(Enum(*YES_NO, name='yes_no_types'))
    inspection_date = Column(Date)
    safety_audit = Column(Enum(*SAFETY_TYPES, name='safety_types'))
    utilization_history = Column(Text)
    accident_history = Column(Text)

class Maintenance(Base):
    __tablename__ = 'maintenance'
    id = Column(Integer, primary_key=True)
    plate_number = Column(String(20), ForeignKey('vehicle.plate_number'))
    last_service_km = Column(Integer)
    last_service_date = Column(Date)
    next_service_km = Column(Integer)
    next_service_date = Column(Date)
    maintenance_center = Column(Enum(*MAINTENANCE_CENTERS, name='maintenance_centers'))

class Assignment(Base):
    __tablename__ = 'assignment'
    id = Column(Integer, primary_key=True)
    plate_number = Column(String(20), ForeignKey('vehicle.plate_number'))
    driver_id = Column(Integer, ForeignKey('driver.id'))
    work_place = Column(String(100))
    start_date = Column(Date)
    end_date = Column(Date)
    gps_position = Column(String(50))
    geofence_violations = Column(Integer)

class User(Base):
    __tablename__ = 'user'
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(100), nullable=False)
    role = Column(String(20), default='user')

# Create tables
try:
    Base.metadata.create_all(engine)
except Exception as e:
    st.error(f"Failed to create database tables: {str(e)}")
    st.stop()

# Helper Functions
def get_dashboard_counts():
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM vehicle")
        vehicle_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM driver")
        driver_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM assignment WHERE end_date IS NULL")
        assignment_count = cursor.fetchone()[0]
        cursor.execute('''
            SELECT v.plate_number, v.make, v.model, m.next_service_date, m.maintenance_center
            FROM maintenance m JOIN vehicle v ON m.plate_number = v.plate_number
            WHERE m.next_service_date <= date('now', '+7 days')
            ORDER BY m.next_service_date LIMIT 5
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
            FROM compliance c JOIN vehicle v ON c.plate_number = v.plate_number
            WHERE c.yearly_inspection = 'No'
                OR c.inspection_date < date('now', '-1 year')
                OR c.insurance_date < date('now', '-1 year')
            LIMIT 5
        ''')
        compliance_issues = cursor.fetchall()
        conn.close()
        return vehicle_count, driver_count, assignment_count, maintenance_due, compliance_issues
    except Exception as e:
        st.error(f"Error fetching dashboard counts: {str(e)}")
        return 0, 0, 0, [], []

# Authentication
def verify_user(username, password):
    session = Session()
    try:
        user = session.query(User).filter_by(username=username).first()
        if user and pbkdf2_sha256.verify(password, user.password_hash):
            return user
        return None
    except Exception as e:
        st.error(f"Authentication error: {str(e)}")
        return None
    finally:
        session.close()

def create_default_user():
    session = Session()
    try:
        if not session.query(User).filter_by(username='admin').first():
            hashed_password = pbkdf2_sha256.hash('admin123')
            admin_user = User(username='admin', password_hash=hashed_password, role='admin')
            session.add(admin_user)
            session.commit()
    except Exception as e:
        st.error(f"Failed to create default user: {str(e)}")
    finally:
        session.close()

# Streamlit App
st.set_page_config(page_title="Fleet Management System", layout="wide")

def main():
    create_default_user()
    
    if 'user' not in st.session_state:
        st.session_state.user = None

    with st.sidebar:
        st.title("Fleet Management System")
        if st.session_state.user is None:
            st.subheader("Login")
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            if st.button("Login"):
                user = verify_user(username, password)
                if user:
                    st.session_state.user = user
                    st.success("Logged in successfully!")
                    st.rerun()
                else:
                    st.error("Invalid credentials")
        else:
            st.write(f"Welcome, {st.session_state.user.username}")
            if st.button("Logout"):
                st.session_state.user = None
                st.rerun()

        if st.session_state.user:
            selected = option_menu(
                menu_title="Menu",
                options=["Dashboard", "Vehicles", "Drivers", "Assignments", "Compliance", "Maintenance", "Reports"],
                icons=["house", "truck", "person", "link", "shield-check", "tools", "bar-chart"],
                default_index=0,
            )
        else:
            selected = None

    if st.session_state.user is None:
        st.warning("Please log in to access the system.")
        return

    session = Session()

    try:
        if selected == "Dashboard":
            vehicle_count, driver_count, assignment_count, maintenance_due, compliance_issues = get_dashboard_counts()
            st.header("Dashboard")
            col1, col2, col3 = st.columns(3)
            col1.metric("Total Vehicles", vehicle_count)
            col2.metric("Total Drivers", driver_count)
            col3.metric("Active Assignments", assignment_count)
            st.subheader("Upcoming Maintenance (Next 7 Days)")
            maintenance_df = pd.DataFrame(maintenance_due, columns=['Plate Number', 'Make', 'Model', 'Next Service Date', 'Maintenance Center'])
            st.dataframe(maintenance_df)
            st.subheader("Compliance Issues")
            compliance_df = pd.DataFrame(compliance_issues, columns=['Plate Number', 'Make', 'Model', 'Issue Type'])
            st.dataframe(compliance_df)

            # Seaborn Visualization
            st.subheader("Vehicle Distribution by Type")
            vehicles = session.query(Vehicle.vehicle_type, func.count(Vehicle.plate_number)).group_by(Vehicle.vehicle_type).all()
            vehicle_df = pd.DataFrame(vehicles, columns=['Vehicle Type', 'Count'])
            fig, ax = plt.subplots(figsize=(10, 6))
            sns.barplot(x='Count', y='Vehicle Type', data=vehicle_df, ax=ax, palette='viridis')
            st.pyplot(fig)

        elif selected == "Vehicles":
            st.header("Manage Vehicles")
            with st.form("vehicle_form"):
                plate_number = st.text_input("Plate Number").upper().strip()
                chasis = st.text_input("Chasis")
                vehicle_type = st.selectbox("Vehicle Type", VEHICLE_TYPES)
                make = st.text_input("Make")
                model = st.text_input("Model")
                year = st.text_input("Year")
                fuel_type = st.selectbox("Fuel Type", FUEL_TYPES)
                fuel_capacity = st.number_input("Fuel Capacity", min_value=0.0)
                fuel_consumption = st.number_input("Fuel Consumption", min_value=0.0)
                loading_capacity = st.text_input("Loading Capacity")
                assigned_for = st.selectbox("Assigned For", ASSIGNMENT_TYPES)
                submit = st.form_submit_button("Add Vehicle")
                if submit:
                    if session.query(Vehicle).get(plate_number):
                        st.error("Plate number already exists!")
                    else:
                        new_vehicle = Vehicle(
                            plate_number=plate_number, chasis=chasis, vehicle_type=vehicle_type,
                            make=make, model=model, year=year, fuel_type=fuel_type,
                            fuel_capacity=fuel_capacity, fuel_consumption=fuel_consumption,
                            loading_capacity=loading_capacity, assigned_for=assigned_for
                        )
                        session.add(new_vehicle)
                        session.commit()
                        st.success("Vehicle added successfully!")
                        st.rerun()

            vehicles = session.query(Vehicle).all()
            st.subheader("Vehicle List")
            vehicle_df = pd.DataFrame([(v.plate_number, v.make, v.model, v.vehicle_type, v.assigned_for) for v in vehicles],
                                    columns=['Plate Number', 'Make', 'Model', 'Type', 'Assigned For'])
            st.dataframe(vehicle_df)

            # Edit/Delete Vehicle
            st.subheader("Edit/Delete Vehicle")
            plate_to_edit = st.text_input("Enter Plate Number to Edit/Delete")
            if plate_to_edit:
                vehicle = session.query(Vehicle).get(plate_to_edit.upper())
                if vehicle:
                    with st.form("edit_vehicle_form"):
                        chasis = st.text_input("Chasis", value=vehicle.chasis)
                        vehicle_type = st.selectbox("Vehicle Type", VEHICLE_TYPES, index=VEHICLE_TYPES.index(vehicle.vehicle_type) if vehicle.vehicle_type else 0)
                        make = st.text_input("Make", value=vehicle.make)
                        model = st.text_input("Model", value=vehicle.model)
                        year = st.text_input("Year", value=vehicle.year)
                        fuel_type = st.selectbox("Fuel Type", FUEL_TYPES, index=FUEL_TYPES.index(vehicle.fuel_type) if vehicle.fuel_type else 0)
                        fuel_capacity = st.number_input("Fuel Capacity", min_value=0.0, value=vehicle.fuel_capacity or 0.0)
                        fuel_consumption = st.number_input("Fuel Consumption", min_value=0.0, value=vehicle.fuel_consumption or 0.0)
                        loading_capacity = st.text_input("Loading Capacity", value=vehicle.loading_capacity)
                        assigned_for = st.selectbox("Assigned For", ASSIGNMENT_TYPES, index=ASSIGNMENT_TYPES.index(vehicle.assigned_for) if vehicle.assigned_for else 0)
                        col1, col2 = st.columns(2)
                        update = col1.form_submit_button("Update Vehicle")
                        delete = col2.form_submit_button("Delete Vehicle")
                        if update:
                            vehicle.chasis = chasis
                            vehicle.vehicle_type = vehicle_type
                            vehicle.make = make
                            vehicle.model = model
                            vehicle.year = year
                            vehicle.fuel_type = fuel_type
                            vehicle.fuel_capacity = fuel_capacity
                            vehicle.fuel_consumption = fuel_consumption
                            vehicle.loading_capacity = loading_capacity
                            vehicle.assigned_for = assigned_for
                            session.commit()
                            st.success("Vehicle updated successfully!")
                            st.rerun()
                        if delete:
                            session.delete(vehicle)
                            session.commit()
                            st.success("Vehicle deleted successfully!")
                            st.rerun()
                else:
                    st.error("Vehicle not found!")

        elif selected == "Drivers":
            st.header("Manage Drivers")
            with st.form("driver_form"):
                name = st.text_input("Name")
                id_number = st.text_input("ID Number")
                phone = st.text_input("Phone")
                reporting_to = st.text_input("Reporting To")
                submit = st.form_submit_button("Add Driver")
                if submit:
                    new_driver = Driver(name=name, id_number=id_number, phone=phone.strip(), reporting_to=reporting_to)
                    session.add(new_driver)
                    session.commit()
                    st.success("Driver added successfully!")
                    st.rerun()

            drivers = session.query(Driver).all()
            st.subheader("Driver List")
            driver_df = pd.DataFrame([(d.name, d.id_number, d.phone, d.reporting_to) for d in drivers],
                                    columns=['Name', 'ID Number', 'Phone', 'Reporting To'])
            st.dataframe(driver_df)

            # Edit/Delete Driver
            st.subheader("Edit/Delete Driver")
            driver_id_to_edit = st.number_input("Enter Driver ID to Edit/Delete", min_value=1, step=1)
            if driver_id_to_edit:
                driver = session.query(Driver).get(driver_id_to_edit)
                if driver:
                    with st.form("edit_driver_form"):
                        name = st.text_input("Name", value=driver.name)
                        id_number = st.text_input("ID Number", value=driver.id_number)
                        phone = st.text_input("Phone", value=driver.phone)
                        reporting_to = st.text_input("Reporting To", value=driver.reporting_to)
                        col1, col2 = st.columns(2)
                        update = col1.form_submit_button("Update Driver")
                        delete = col2.form_submit_button("Delete Driver")
                        if update:
                            driver.name = name
                            driver.id_number = id_number
                            driver.phone = phone.strip()
                            driver.reporting_to = reporting_to
                            session.commit()
                            st.success("Driver updated successfully!")
                            st.rerun()
                        if delete:
                            session.delete(driver)
                            session.commit()
                            st.success("Driver deleted successfully!")
                            st.rerun()
                else:
                    st.error("Driver not found!")

        elif selected == "Assignments":
            st.header("Manage Assignments")
            with st.form("assignment_form"):
                plate_number = st.text_input("Plate Number").upper().strip()
                drivers = session.query(Driver).all()
                driver_id = st.selectbox("Driver", [(d.id, d.name) for d in drivers], format_func=lambda x: x[1])
                work_place = st.text_input("Work Place")
                start_date = st.date_input("Start Date")
                end_date = st.date_input("End Date", value=None, min_value=start_date)
                gps_position = st.text_input("GPS Position")
                geofence_violations = st.number_input("Geofence Violations", min_value=0, value=0)
                submit = st.form_submit_button("Add Assignment")
                if submit:
                    if not session.query(Vehicle).get(plate_number):
                        st.error("Vehicle does not exist!")
                    else:
                        new_assignment = Assignment(
                            plate_number=plate_number, driver_id=driver_id[0], work_place=work_place,
                            start_date=start_date, end_date=end_date, gps_position=gps_position,
                            geofence_violations=geofence_violations
                        )
                        session.add(new_assignment)
                        session.commit()
                        st.success("Assignment created successfully!")
                        st.rerun()

            assignments = session.query(Assignment).all()
            st.subheader("Assignment List")
            assignment_df = pd.DataFrame([(a.plate_number, a.driver.name if a.driver else 'None', a.work_place, a.start_date, a.end_date) for a in assignments],
                                        columns=['Plate Number', 'Driver', 'Work Place', 'Start Date', 'End Date'])
            st.dataframe(assignment_df)

            # Edit/Delete Assignment
            st.subheader("Edit/Delete Assignment")
            assignment_id_to_edit = st.number_input("Enter Assignment ID to Edit/Delete", min_value=1, step=1)
            if assignment_id_to_edit:
                assignment = session.query(Assignment).get(assignment_id_to_edit)
                if assignment:
                    with st.form("edit_assignment_form"):
                        plate_number = st.text_input("Plate Number", value=assignment.plate_number).upper().strip()
                        driver_id = st.selectbox("Driver", [(d.id, d.name) for d in session.query(Driver).all()], 
                                                index=[d.id for d in drivers].index(assignment.driver_id) if assignment.driver_id else 0, 
                                                format_func=lambda x: x[1])
                        work_place = st.text_input("Work Place", value=assignment.work_place)
                        start_date = st.date_input("Start Date", value=assignment.start_date)
                        end_date = st.date_input("End Date", value=assignment.end_date, min_value=start_date)
                        gps_position = st.text_input("GPS Position", value=assignment.gps_position)
                        geofence_violations = st.number_input("Geofence Violations", min_value=0, value=assignment.geofence_violations or 0)
                        col1, col2 = st.columns(2)
                        update = col1.form_submit_button("Update Assignment")
                        delete = col2.form_submit_button("Delete Assignment")
                        if update:
                            if not session.query(Vehicle).get(plate_number):
                                st.error("Vehicle does not exist!")
                            else:
                                assignment.plate_number = plate_number
                                assignment.driver_id = driver_id[0]
                                assignment.work_place = work_place
                                assignment.start_date = start_date
                                assignment.end_date = end_date
                                assignment.gps_position = gps_position
                                assignment.geofence_violations = geofence_violations
                                session.commit()
                                st.success("Assignment updated successfully!")
                                st.rerun()
                        if delete:
                            session.delete(assignment)
                            session.commit()
                            st.success("Assignment deleted successfully!")
                            st.rerun()
                else:
                    st.error("Assignment not found!")

        elif selected == "Compliance":
            st.header("Manage Compliance")
            plate_number = st.text_input("Enter Vehicle Plate Number").upper().strip()
            if plate_number:
                vehicle = session.query(Vehicle).get(plate_number)
                if not vehicle:
                    st.error("Vehicle not found!")
                else:
                    compliance = session.query(Compliance).get(plate_number) or Compliance(plate_number=plate_number)
                    with st.form("compliance_form"):
                        insurance_type = st.selectbox("Insurance Type", INSURANCE_TYPES, 
                                                    index=INSURANCE_TYPES.index(compliance.insurance_type) if compliance.insurance_type else 0)
                        insurance_date = st.date_input("Insurance Date", value=compliance.insurance_date)
                        yearly_inspection = st.selectbox("Yearly Inspection", YES_NO, 
                                                        index=YES_NO.index(compliance.yearly_inspection) if compliance.yearly_inspection else 0)
                        inspection_date = st.date_input("Inspection Date", value=compliance.inspection_date)
                        safety_audit = st.selectbox("Safety Audit", SAFETY_TYPES, 
                                                    index=SAFETY_TYPES.index(compliance.safety_audit) if compliance.safety_audit else 0)
                        utilization_history = st.text_area("Utilization History", value=compliance.utilization_history or "")
                        accident_history = st.text_area("Accident History", value=compliance.accident_history or "")
                        submit = st.form_submit_button("Save Compliance")
                        if submit:
                            compliance.insurance_type = insurance_type
                            compliance.insurance_date = insurance_date
                            compliance.yearly_inspection = yearly_inspection
                            compliance.inspection_date = inspection_date
                            compliance.safety_audit = safety_audit
                            compliance.utilization_history = utilization_history
                            compliance.accident_history = accident_history
                            if not vehicle.compliance:
                                session.add(compliance)
                            session.commit()
                            st.success("Compliance data saved!")
                            st.rerun()

        elif selected == "Maintenance":
            st.header("Manage Maintenance")
            plate_number = st.text_input("Enter Vehicle Plate Number").upper().strip()
            if plate_number:
                vehicle = session.query(Vehicle).get(plate_number)
                if not vehicle:
                    st.error("Vehicle not found!")
                else:
                    with st.form("maintenance_form"):
                        last_service_km = st.number_input("Last Service KM", min_value=0, value=0)
                        last_service_date = st.date_input("Last Service Date")
                        next_service_km = st.number_input("Next Service KM", min_value=0, value=0)
                        next_service_date = st.date_input("Next Service Date")
                        maintenance_center = st.selectbox("Maintenance Center", MAINTENANCE_CENTERS)
                        submit = st.form_submit_button("Add Maintenance Record")
                        if submit:
                            new_maintenance = Maintenance(
                                plate_number=plate_number, last_service_km=last_service_km,
                                last_service_date=last_service_date, next_service_km=next_service_km,
                                next_service_date=next_service_date, maintenance_center=maintenance_center
                            )
                            session.add(new_maintenance)
                            session.commit()
                            st.success("Maintenance record added!")
                            st.rerun()
                    maintenance_records = session.query(Maintenance).filter_by(plate_number=plate_number).all()
                    st.subheader("Maintenance Records")
                    maintenance_df = pd.DataFrame([(m.last_service_date, m.last_service_km, m.next_service_date, m.next_service_km, m.maintenance_center) for m in maintenance_records],
                                                columns=['Last Service Date', 'Last Service KM', 'Next Service Date', 'Next Service KM', 'Maintenance Center'])
                    st.dataframe(maintenance_df)

                    # Delete Maintenance Record
                    st.subheader("Delete Maintenance Record")
                    record_id = st.number_input("Enter Maintenance Record ID to Delete", min_value=1, step=1)
                    if record_id:
                        record = session.query(Maintenance).get(record_id)
                        if record and record.plate_number == plate_number:
                            if st.button("Delete Record"):
                                session.delete(record)
                                session.commit()
                                st.success("Maintenance record deleted!")
                                st.rerun()
                        else:
                            st.error("Record not found or does not belong to this vehicle!")

        elif selected == "Reports":
            st.header("Reports")
            report_type = st.selectbox("Select Report", ["Assignment Summary", "Unassigned Vehicles", "Driver Assignments"])
            if report_type == "Assignment Summary":
                assignment_counts = session.query(Vehicle.assigned_for, func.count(Vehicle.plate_number)).group_by(Vehicle.assigned_for).all()
                df = pd.DataFrame(assignment_counts, columns=['Assignment Type', 'Vehicle Count'])
                st.dataframe(df)
                fig, ax = plt.subplots(figsize=(10, 6))
                sns.barplot(x='Vehicle Count', y='Assignment Type', data=df, ax=ax, palette='viridis')
                st.pyplot(fig)
                if st.button("Export to Excel"):
                    output = BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        df.to_excel(writer, sheet_name='Assignment Summary', index=False)
                        stats = pd.DataFrame({
                            'Metric': ['Ongoing Assignments', 'Unassigned Vehicles'],
                            'Count': [
                                session.query(Assignment).filter(or_(Assignment.end_date.is_(None), Assignment.end_date >= date.today())).count(),
                                session.query(Vehicle).filter(~Vehicle.plate_number.in_(
                                    session.query(Assignment.plate_number).filter(or_(Assignment.end_date.is_(None), Assignment.end_date >= date.today()))
                                )).count()
                            ]
                        })
                        stats.to_excel(writer, sheet_name='Summary Stats', index=False)
                    output.seek(0)
                    st.download_button("Download Excel", output, f'assignment_summary_{datetime.now().strftime("%Y%m%d")}.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

            elif report_type == "Unassigned Vehicles":
                active_assignments = session.query(Assignment.plate_number).filter(or_(Assignment.end_date.is_(None), Assignment.end_date >= date.today()))
                vehicles = session.query(Vehicle).filter(~Vehicle.plate_number.in_(active_assignments)).all()
                df = pd.DataFrame([(v.plate_number, v.make, v.model, v.vehicle_type, v.assigned_for) for v in vehicles],
                                columns=['Plate Number', 'Make', 'Model', 'Type', 'Assigned For'])
                st.dataframe(df)
                if st.button("Export to Excel"):
                    output = BytesIO()
                    df.to_excel(output, sheet_name='Unassigned Vehicles', index=False)
                    output.seek(0)
                    st.download_button("Download Excel", output, f'unassigned_vehicles_{datetime.now().strftime("%Y%m%d")}.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

            elif report_type == "Driver Assignments":
                drivers = session.query(Driver, Assignment).outerjoin(Assignment, and_(Assignment.driver_id == Driver.id, or_(Assignment.end_date.is_(None), Assignment.end_date >= date.today()))).all()
                df = pd.DataFrame([{
                    'Driver Name': d.name, 'ID Number': d.id_number, 'Phone': d.phone,
                    'Assigned Vehicle': f"{a.vehicle.plate_number} ({a.vehicle.make})" if a else 'Not assigned',
                    'Work Place': a.work_place if a else '-', 'Start Date': a.start_date.strftime('%Y-%m-%d') if a and a.start_date else '-',
                    'End Date': a.end_date.strftime('%Y-%m-%d') if a and a.end_date else '-'
                } for d, a in drivers], columns=['Driver Name', 'ID Number', 'Phone', 'Assigned Vehicle', 'Work Place', 'Start Date', 'End Date'])
                st.dataframe(df)
                if st.button("Export to Excel"):
                    output = BytesIO()
                    df.to_excel(output, sheet_name='Driver Assignments', index=False)
                    output.seek(0)
                    st.download_button("Download Excel", output, f'driver_assignments_{datetime.now().strftime("%Y%m%d")}.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    main()
'''

### Key Changes to Fix the Error:
1. **Flexible Database Path**:
   - Added logic to detect if running on PythonAnywhere via an environment variable (`PYTHONANYWHERE`).
   - Default to a local path (`fleetgk/fleet.db` relative to the script) for local testing.
   - Used `os.makedirs(db_dir, exist_ok=True)` to ensure the `fleet_management` directory exists.

2. **Improved Error Handling**:
   - Wrapped database initialization and table creation in try-except blocks to catch and display specific errors.
   - Added error handling in `get_dashboard_counts`, `verify_user`, and `create_default_user` to prevent crashes if the database is inaccessible.

3. **SQLite URI Format**:
   - Used a standard SQLite URI (`sqlite:///path/to/db`) for both local and PythonAnywhere environments.
   - Ensured the path is absolute to avoid relative path issues.

4. **Permissions Check**:
   - While the code can't directly modify file permissions, the directory creation ensures the app has write access to the local directory.
   - For PythonAnywhere, the path `/home/abrhamw/fleet_management/fleet.db` assumes the user `abrhamw` has write permissions.

### Steps to Resolve the Issue:
1. **Verify the Database Path**:
   - **Local Environment**: The database will be created in `<script_directory>/fleet_management/fleet.db`. Ensure you have write permissions in the script's directory.
   - **PythonAnywhere**: Confirm the path `/home/abrhamw/fleet_management/fleet.db` is correct for your PythonAnywhere account. Replace `abrhamw` with your actual PythonAnywhere username if different.
   - Check if the `fleet_management` directory exists. If not, create it manually:
     ```bash
     mkdir -p /home/abrhamw/fleet_management
     ```
   - Ensure the directory has appropriate permissions:
     ```bash
     chmod -R u+rw /home/abrhamw/fleet_management
     ```

2. **Set Environment Variable (if on PythonAnywhere)**:
   - In your PythonAnywhere environment, set the environment variable to indicate you're running on PythonAnywhere. You can do this in the PythonAnywhere dashboard or via a `.bashrc` file:
     ```bash
     export PYTHONANYWHERE=true
     ```
   - Alternatively, modify the code to always use the PythonAnywhere path if you're sure you're deploying there.

3. **Install Dependencies**:
   Ensure all required libraries are installed:
   ```bash
   pip install streamlit streamlit-option-menu sqlalchemy pandas seaborn matplotlib passlib xlsxwriter
   ```

4. **Run the App**:
   ```bash
   streamlit run app.py
   ```
   - If running locally, the database will be created automatically in the `fleet_management` directory.
   - If on PythonAnywhere, ensure the web app is configured to run Streamlit (update the WSGI file or use a Bash console to run the app).

5. **Test Login**:
   - Use the default credentials (`admin`/`admin123`) to log in.
   - If the database is created successfully, the app should load without the `OperationalError`.

### Troubleshooting Tips:
- **Check File Permissions**:
  If the error persists, verify permissions on the database file and directory:
  ```bash
  ls -ld /home/abrhamw/fleet_management
  ls -l /home/abrhamw/fleet_management/fleet.db
  ```
  Ensure the user running the app has read/write access.

- **Test Database Connection**:
  To isolate the issue, test the SQLite connection manually:
  ```python
  import sqlite3
  conn = sqlite3.connect('/home/abrhamw/fleet_management/fleet.db')
  conn.close()
  ```
  If this fails, the issue is with the path or permissions.

- **Alternative Path**:
  If you're testing locally and the PythonAnywhere path is irrelevant, comment out the PythonAnywhere path logic and use a simpler path:
  ```python
  db_path = os.path.join(basedir, 'fleet.db')
  db_uri = f'sqlite:///{db_path}'
  ```

- **Log Debugging**:
  If the error persists, enable SQLAlchemy logging by setting `echo=True` in `create_engine` temporarily:
  ```python
  engine = create_engine(db_uri, echo=True)
  ```
  This will print SQLAlchemy operations to the console, helping identify the issue.

### Notes:
- The updated code maintains all functionality (dashboard, vehicles, drivers, assignments, compliance, maintenance, reports, authentication, Seaborn visualizations).
- If you're migrating from the Flask app, the database schema remains compatible, so existing data should work if the file is accessible.
- If you encounter a different error after applying these changes, please share the full error message, and I'll provide a targeted fix.
- For production on PythonAnywhere, consider using a more robust database (e.g., MySQL) and secure the database file's permissions.

Let me know if you need help with PythonAnywhere setup, further debugging, or additional features!'''

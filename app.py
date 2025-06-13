import os
import streamlit as st
from streamlit_option_menu import option_menu
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

# Streamlit-specific configuration
st.set_page_config(page_title="Fleet Management System", layout="wide")

# Database setup optimized for Streamlit Cloud
db_dir = 'data'
os.makedirs(db_dir, exist_ok=True)
db_path = os.path.join(db_dir, 'fleet.db')
db_uri = f'sqlite:///{db_path}'

# Initialize SQLAlchemy
try:
    engine = create_engine(db_uri, echo=False)
    Session = scoped_session(sessionmaker(bind=engine))
    Base = declarative_base()
except Exception as e:
    st.error(f"Failed to initialize database: {str(e)}")
    st.stop()

# Enums for database fields (unchanged)
VEHICLE_TYPES = ('Pickup', 'Land Cruiser', 'Prado', 'V8', 'Hardtop', 'Minibus', 'Bus', 'Crane', 'ISUZU FSR', 'Other')
FUEL_TYPES = ('Diesel', 'Benzin', 'Hybrid', 'Electric')
ASSIGNMENT_TYPES = ('Program Office I', 'Program Office II', 'Program Office III', 'Program Office IV', 'Central I Region', 'Central II Region', 'Central III Region', 'North Region', 'North East I Region', 'North East II Region', 'North West Region', 'West Region', 'South West Region', 'South I Region', 'South II Region', 'East I Region', 'East II Region', 'Region Coordination Office', 'Load Dispatch Center', 'Other')
INSURANCE_TYPES = ('Fully Insured', 'Partial')
SAFETY_TYPES = ('Safe', 'Fair', 'Not Safe')
MAINTENANCE_CENTERS = ('EEP', 'Moenco', 'Other')
YES_NO = ('Yes', 'No')

# Database Models (unchanged)
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

# Helper Functions (unchanged)
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

# Authentication (unchanged)
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
        # Rest of the application code remains unchanged
        # [Dashboard, Vehicles, Drivers, Assignments, Compliance, Maintenance, Reports]
        # ... (same as original file content) ...
        if selected == "Dashboard":
            st.header("Dashboard")
            vehicle_count, driver_count, assignment_count, maintenance_due, compliance_issues, max_counts = get_dashboard_counts()
            
            # Animated Buckets
            col1, col2, col3 = st.columns(3)
            with col1:
                fill_height = (vehicle_count / max_counts['vehicles']) * 100
                st.markdown(f"""
                <div class="bucket-container">
                    <div class="bucket-label">Vehicles</div>
                    <div class="bucket-fill vehicle-bucket" style="--fill-height: {fill_height}%"></div>
                    <div class="bucket-value">{vehicle_count}</div>
                </div>
                """, unsafe_allow_html=True)
            with col2:
                fill_height = (driver_count / max_counts['drivers']) * 100
                st.markdown(f"""
                <div class="bucket-container">
                    <div class="bucket-label">Drivers</div>
                    <div class="bucket-fill driver-bucket" style="--fill-height: {fill_height}%"></div>
                    <div class="bucket-value">{driver_count}</div>
                </div>
                """, unsafe_allow_html=True)
            with col3:
                fill_height = (assignment_count / max_counts['assignments']) * 100
                st.markdown(f"""
                <div class="bucket-container">
                    <div class="bucket-label">Assignments</div>
                    <div class="bucket-fill assignment-bucket" style="--fill-height: {fill_height}%"></div>
                    <div class="bucket-value">{assignment_count}</div>
                </div>
                """, unsafe_allow_html=True)

            # Data Analysis
            st.subheader("Data Analysis")
            st.write(f"**Total Vehicles**: {vehicle_count} (Max capacity: {max_counts['vehicles']})")
            st.write(f"**Total Drivers**: {driver_count} (Max capacity: {max_counts['drivers']})")
            st.write(f"**Active Assignments**: {assignment_count} (Max capacity: {max_counts['assignments']})")
            st.write(f"**Maintenance Due (Next 7 Days)**: {len(maintenance_due)} vehicles")
            st.write(f"**Compliance Issues**: {len(compliance_issues)} vehicles")

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

        elif selected in ["Vehicles", "Drivers", "Assignments", "Compliance", "Maintenance", "Reports", "Summary"]:
            if st.session_state.user is None:
                st.warning("Please log in to access this section.")
                return

        if selected == "Vehicles":
            st.header("Manage Vehicles")
            with st.expander("Add New Vehicle"):
                with st.form("vehicle_form"):
                    plate_number = st.text_input("Plate Number", placeholder="e.g., ABC123", help="Unique vehicle plate number").upper().strip()
                    chasis = st.text_input("Chasis", placeholder="e.g., XYZ789", help="Vehicle chassis number")
                    vehicle_type = st.selectbox("Vehicle Type", VEHICLE_TYPES, help="Select the type of vehicle")
                    make = st.text_input("Make", placeholder="e.g., Toyota", help="Vehicle manufacturer")
                    model = st.text_input("Model", placeholder="e.g., Hilux", help="Vehicle model")
                    year = st.text_input("Year", placeholder="e.g., 2020", help="Manufacturing year")
                    fuel_type = st.selectbox("Fuel Type", FUEL_TYPES, help="Select fuel type")
                    fuel_capacity = st.number_input("Fuel Capacity (liters)", min_value=0.0, value=0.0, help="Fuel tank capacity")
                    fuel_consumption = st.number_input("Fuel Consumption (km/l)", min_value=0.0, value=0.0, help="Fuel efficiency")
                    loading_capacity = st.text_input("Loading Capacity", placeholder="e.g., 1000 kg", help="Maximum load capacity")
                    assigned_for = st.selectbox("Assigned For", ASSIGNMENT_TYPES, help="Select assignment region/office")
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
            st.write(f"**Total Vehicles**: {len(vehicles)}")
            st.write(f"**Unique Vehicle Types**: {len(set(v.vehicle_type for v in vehicles))}")
            st.write(f"**Most Common Assignment**: {max((v.assigned_for for v in vehicles), key=lambda x: sum(1 for v in vehicles if v.assigned_for == x), default='None')}")

            # Edit/Delete Vehicle
            with st.expander("Edit/Delete Vehicle"):
                plate_to_edit = st.text_input("Enter Plate Number to Edit/Delete", placeholder="e.g., ABC123").upper().strip()
                if plate_to_edit:
                    vehicle = session.query(Vehicle).get(plate_to_edit)
                    if vehicle:
                        with st.form("edit_vehicle_form"):
                            chasis = st.text_input("Chasis", value=vehicle.chasis, placeholder="e.g., XYZ789")
                            vehicle_type = st.selectbox("Vehicle Type", VEHICLE_TYPES, index=VEHICLE_TYPES.index(vehicle.vehicle_type) if vehicle.vehicle_type else 0)
                            make = st.text_input("Make", value=vehicle.make, placeholder="e.g., Toyota")
                            model = st.text_input("Model", value=vehicle.model, placeholder="e.g., Hilux")
                            year = st.text_input("Year", value=vehicle.year, placeholder="e.g., 2020")
                            fuel_type = st.selectbox("Fuel Type", FUEL_TYPES, index=FUEL_TYPES.index(vehicle.fuel_type) if vehicle.fuel_type else 0)
                            fuel_capacity = st.number_input("Fuel Capacity (liters)", min_value=0.0, value=vehicle.fuel_capacity or 0.0)
                            fuel_consumption = st.number_input("Fuel Consumption (km/l)", min_value=0.0, value=vehicle.fuel_consumption or 0.0)
                            loading_capacity = st.text_input("Loading Capacity", value=vehicle.loading_capacity, placeholder="e.g., 1000 kg")
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
            with st.expander("Add New Driver"):
                with st.form("driver_form"):
                    name = st.text_input("Name", placeholder="e.g., John Doe", help="Driver's full name")
                    id_number = st.text_input("ID Number", placeholder="e.g., D123456", help="Unique ID number")
                    phone = st.text_input("Phone", placeholder="e.g., +251912345678", help="Contact number")
                    reporting_to = st.text_input("Reporting To", placeholder="e.g., Jane Smith", help="Supervisor's name")
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
            st.write(f"**Total Drivers**: {len(drivers)}")
            st.write(f"**Unique Reporting Managers**: {len(set(d.reporting_to for d in drivers if d.reporting_to))}")
            active_assignments = session.query(Assignment).filter(or_(Assignment.end_date.is_(None), Assignment.end_date >= date.today())).count()
            st.write(f"**Drivers with Active Assignments**: {len(set(a.driver_id for a in session.query(Assignment).filter(or_(Assignment.end_date.is_(None), Assignment.end_date >= date.today()))))}")

            # Edit/Delete Driver
            with st.expander("Edit/Delete Driver"):
                driver_id_to_edit = st.number_input("Enter Driver ID to Edit/Delete", min_value=1, step=1, help="Find ID in Driver List")
                if driver_id_to_edit:
                    driver = session.query(Driver).get(driver_id_to_edit)
                    if driver:
                        with st.form("edit_driver_form"):
                            name = st.text_input("Name", value=driver.name, placeholder="e.g., John Doe")
                            id_number = st.text_input("ID Number", value=driver.id_number, placeholder="e.g., D123456")
                            phone = st.text_input("Phone", value=driver.phone, placeholder="e.g., +251912345678")
                            reporting_to = st.text_input("Reporting To", value=driver.reporting_to, placeholder="e.g., Jane Smith")
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
            with st.expander("Add New Assignment"):
                with st.form("assignment_form"):
                    plate_number = st.text_input("Plate Number", placeholder="e.g., ABC123", help="Vehicle plate number").upper().strip()
                    drivers = session.query(Driver).all()
                    driver_id = st.selectbox("Driver", [(d.id, d.name) for d in drivers], format_func=lambda x: x[1], help="Select driver")
                    work_place = st.text_input("Work Place", placeholder="e.g., Addis Ababa", help="Assignment location")
                    start_date = st.date_input("Start Date", help="Assignment start date")
                    end_date = st.date_input("End Date", value=None, min_value=start_date, help="Optional end date")
                    gps_position = st.text_input("GPS Position", placeholder="e.g., 9.03, 38.74", help="GPS coordinates")
                    geofence_violations = st.number_input("Geofence Violations", min_value=0, value=0, help="Number of violations")
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
            assignment_df = pd.DataFrame([(a.plate_number, a.driver.name if a.driver else 'None', a.work_place, parse_date(a.start_date), parse_date(a.end_date)) for a in assignments],
                                        columns=['Plate Number', 'Driver', 'Work Place', 'Start Date', 'End Date'])
            st.dataframe(assignment_df)
            st.write(f"**Total Assignments**: {len(assignments)}")
            st.write(f"**Active Assignments**: {len([a for a in assignments if a.end_date is None or a.end_date >= date.today()])}")
            st.write(f"**Most Common Work Place**: {max((a.work_place for a in assignments), key=lambda x: sum(1 for a in assignments if a.work_place == x), default='None')}")

            # Edit/Delete Assignment
            with st.expander("Edit/Delete Assignment"):
                assignment_id_to_edit = st.number_input("Enter Assignment ID to Edit/Delete", min_value=1, step=1, help="Find ID in Assignment List")
                if assignment_id_to_edit:
                    assignment = session.query(Assignment).get(assignment_id_to_edit)
                    if assignment:
                        with st.form("edit_assignment_form"):
                            plate_number = st.text_input("Plate Number", value=assignment.plate_number, placeholder="e.g., ABC123").upper().strip()
                            driver_id = st.selectbox("Driver", [(d.id, d.name) for d in session.query(Driver).all()], 
                                                    index=[d.id for d in drivers].index(assignment.driver_id) if assignment.driver_id else 0, 
                                                    format_func=lambda x: x[1])
                            work_place = st.text_input("Work Place", value=assignment.work_place, placeholder="e.g., Addis Ababa")
                            start_date = st.date_input("Start Date", value=assignment.start_date)
                            end_date = st.date_input("End Date", value=assignment.end_date, min_value=start_date)
                            gps_position = st.text_input("GPS Position", value=assignment.gps_position, placeholder="e.g., 9.03, 38.74")
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
            with st.expander("Update Compliance"):
                plate_number = st.text_input("Enter Vehicle Plate Number", placeholder="e.g., ABC123").upper().strip()
                if plate_number:
                    vehicle = session.query(Vehicle).get(plate_number)
                    if not vehicle:
                        st.error("Vehicle not found!")
                    else:
                        compliance = session.query(Compliance).get(plate_number) or Compliance(plate_number=plate_number)
                        with st.form("compliance_form"):
                            insurance_type = st.selectbox("Insurance Type", INSURANCE_TYPES, 
                                                        index=INSURANCE_TYPES.index(compliance.insurance_type) if compliance.insurance_type else 0,
                                                        help="Select insurance coverage")
                            insurance_date = st.date_input("Insurance Date", value=compliance.insurance_date, help="Insurance expiry date")
                            yearly_inspection = st.selectbox("Yearly Inspection", YES_NO, 
                                                            index=YES_NO.index(compliance.yearly_inspection) if compliance.yearly_inspection else 0,
                                                            help="Has yearly inspection been done?")
                            inspection_date = st.date_input("Inspection Date", value=compliance.inspection_date, help="Date of last inspection")
                            safety_audit = st.selectbox("Safety Audit", SAFETY_TYPES, 
                                                        index=SAFETY_TYPES.index(compliance.safety_audit) if compliance.safety_audit else 0,
                                                        help="Safety audit status")
                            utilization_history = st.text_area("Utilization History", value=compliance.utilization_history or "", placeholder="Enter vehicle usage details")
                            accident_history = st.text_area("Accident History", value=compliance.accident_history or "", placeholder="Enter accident details")
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
            compliances = session.query(Compliance).all()
            st.write(f"**Total Compliance Records**: {len(compliances)}")
            st.write(f"**Vehicles with Safety Issues**: {len([c for c in compliances if c.safety_audit == 'Not Safe'])}")
            st.write(f"**Vehicles with Expired Insurance**: {len([c for c in compliances if c.insurance_date and c.insurance_date < date.today()])}")

        elif selected == "Maintenance":
            st.header("Manage Maintenance")
            with st.expander("Add Maintenance Record"):
                plate_number = st.text_input("Enter Vehicle Plate Number", placeholder="e.g., ABC123").upper().strip()
                if plate_number:
                    vehicle = session.query(Vehicle).get(plate_number)
                    if not vehicle:
                        st.error("Vehicle not found!")
                    else:
                        with st.form("maintenance_form"):
                            last_service_km = st.number_input("Last Service KM", min_value=0, value=0, help="Kilometers at last service")
                            last_service_date = st.date_input("Last Service Date", help="Date of last service")
                            next_service_km = st.number_input("Next Service KM", min_value=0, value=0, help="Kilometers for next service")
                            next_service_date = st.date_input("Next Service Date", help="Date of next service")
                            maintenance_center = st.selectbox("Maintenance Center", MAINTENANCE_CENTERS, help="Select service center")
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
            if plate_number:
                maintenance_records = session.query(Maintenance).filter_by(plate_number=plate_number).all()
                st.subheader("Maintenance Records")
                maintenance_df = pd.DataFrame([(parse_date(m.last_service_date), m.last_service_km, 
                                               parse_date(m.next_service_date), m.next_service_km, 
                                               m.maintenance_center) for m in maintenance_records],
                                              columns=['Last Service Date', 'Last Service KM', 'Next Service Date', 'Next Service KM', 'Maintenance Center'])
                st.dataframe(maintenance_df)
                st.write(f"**Total Maintenance Records for {plate_number}**: {len(maintenance_records)}")
                st.write(f"**Average Service Interval (KM)**: {sum((m.next_service_km - m.last_service_km) for m in maintenance_records) / len(maintenance_records) if maintenance_records else 0:.2f}")

                # Delete Maintenance Record
                with st.expander("Delete Maintenance Record"):
                    record_id = st.number_input("Enter Maintenance Record ID to Delete", min_value=1, step=1, help="Find ID in Maintenance Records")
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
            report_type = st.selectbox("Select Report", ["Assignment Summary", "Unassigned Vehicles", "Driver Assignments"], 
                                      help="Choose a report type")
            if report_type == "Assignment Summary":
                assignment_counts = session.query(Vehicle.assigned_for, func.count(Vehicle.plate_number)).group_by(Vehicle.assigned_for).all()
                df = pd.DataFrame(assignment_counts, columns=['Assignment Type', 'Vehicle Count'])
                st.dataframe(df)
                st.write(f"**Total Assignment Types**: {len(assignment_counts)}")
                st.write(f"**Most Common Assignment Type**: {max((a[0] for a in assignment_counts), key=lambda x: sum(c[1] for c in assignment_counts if c[0] == x), default='None')}")
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
                    st.download_button("Download Excel", data=output, file_name=f'assignment_summary_{datetime.now().strftime("%Y%m%d")}.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

            elif report_type == "Unassigned Vehicles":
                active_assignments = session.query(Assignment.plate_number).filter(or_(Assignment.end_date.is_(None), Assignment.end_date >= date.today()))
                vehicles = session.query(Vehicle).filter(~Vehicle.plate_number.in_(active_assignments)).all()
                df = pd.DataFrame([(v.plate_number, v.make, v.model, v.vehicle_type, v.assigned_for) for v in vehicles],
                                columns=['Plate Number', 'Make', 'Model', 'Type', 'Assigned For'])
                st.dataframe(df)
                st.write(f"**Total Unassigned Vehicles**: {len(vehicles)}")
                st.write(f"**Most Common Vehicle Type (Unassigned)**: {max((v.vehicle_type for v in vehicles), key=lambda x: sum(1 for v in vehicles if v.vehicle_type == x), default='None')}")
                if st.button("Export to Excel"):
                    output = BytesIO()
                    df.to_excel(output, sheet_name='Unassigned Vehicles', index=False)
                    output.seek(0)
                    st.download_button("Download Excel", data=output, file_name=f'unassigned_vehicles_{datetime.now().strftime("%Y%m%d")}.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

            elif report_type == "Driver Assignments":
                drivers = session.query(Driver, Assignment).outerjoin(Assignment, and_(Assignment.driver_id == Driver.id, or_(Assignment.end_date.is_(None), Assignment.end_date >= date.today()))).all()
                df = pd.DataFrame([{
                    'Driver Name': d.name, 'ID Number': d.id_number, 'Phone': d.phone,
                    'Assigned Vehicle': f"{a.vehicle.plate_number} ({a.vehicle.make})" if a else 'Not assigned',
                    'Work Place': a.work_place if a else '-',
                    'Start Date': parse_date(a.start_date) if a else '-',
                    'End Date': parse_date(a.end_date) if a else '-'
                } for d, a in drivers], columns=['Driver Name', 'ID Number', 'Phone', 'Assigned Vehicle', 'Work Place', 'Start Date', 'End Date'])
                st.dataframe(df)
                st.write(f"**Total Drivers in Report**: {len(df)}")
                st.write(f"**Drivers without Assignments**: {len([row for row in df.itertuples() if row.Assigned_Vehicle == 'Not assigned'])}")
                if st.button("Export to Excel"):
                    output = BytesIO()
                    df.to_excel(output, sheet_name='Driver Assignments', index=False)
                    output.seek(0)
                    st.download_button("Download Excel", data=output, file_name=f'driver_assignments_{datetime.now().strftime("%Y%m%d")}.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

        elif selected == "Summary":
            st.header("Single Page Summary")
            plate_filter = st.text_input("Filter by Plate Number", placeholder="e.g., ABC123", help="Enter vehicle plate number").upper().strip()
            driver_id_filter = st.number_input("Filter by Driver ID", min_value=0, value=0, step=1, help="Enter driver ID (0 for no filter)")
            driver_name_filter = st.text_input("Filter by Driver Name", placeholder="e.g., John Doe", help="Enter driver name").strip()
            
            # Fetch filtered data
            query = session.query(Vehicle, Assignment, Driver, Compliance, Maintenance).outerjoin(Assignment, Vehicle.plate_number == Assignment.plate_number).outerjoin(Driver, Assignment.driver_id == Driver.id).outerjoin(Compliance, Vehicle.plate_number == Compliance.plate_number).outerjoin(Maintenance, Vehicle.plate_number == Maintenance.plate_number)
            if plate_filter:
                query = query.filter(Vehicle.plate_number == plate_filter)
            if driver_id_filter:
                query = query.filter(Driver.id == driver_id_filter)
            if driver_name_filter:
                query = query.filter(Driver.name.ilike(f'%{driver_name_filter}%'))
            
            results = query.all()
            if not results:
                st.warning("No records found matching the filters.")
            else:
                summary_data = []
                for vehicle, assignment, driver, compliance, maintenance in results:
                    summary_data.append({
                        'Plate Number': vehicle.plate_number,
                        'Vehicle Type': vehicle.vehicle_type,
                        'Make': vehicle.make,
                        'Model': vehicle.model,
                        'Driver Name': driver.name if driver else 'None',
                        'Driver ID': driver.id if driver else '-',
                        'Work Place': assignment.work_place if assignment else '-',
                        'Assignment Start': parse_date(assignment.start_date) if assignment else '-',
                        'Assignment End': parse_date(assignment.end_date) if assignment else '-',
                        'Insurance Status': compliance.insurance_type if compliance else 'None',
                        'Safety Audit': compliance.safety_audit if compliance else 'None',
                        'Last Service Date': parse_date(maintenance.last_service_date) if maintenance else '-',
                        'Next Service Date': parse_date(maintenance.next_service_date) if maintenance else '-'
                    })
                summary_df = pd.DataFrame(summary_data)
                st.dataframe(summary_df)
                st.write(f"**Total Records Found**: {len(summary_data)}")
                st.write(f"**Vehicles with Active Assignments**: {sum(1 for d in summary_data if d['Assignment End'] == '-' or (d['Assignment End'] != '-' and datetime.strptime(d['Assignment End'], '%Y-%m-%d').date() >= date.today()))}")
                if st.button("Export Summary to Excel"):
                    output = BytesIO()
                    summary_df.to_excel(output, sheet_name='Summary', index=False)
                    output.seek(0)
                    st.download_button(
                        label="Download Excel",
                        data=output,
                        file_name=f'summary_{datetime.now().strftime("%Y%m%d")}.xlsx',
                        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                    )
        
    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    main()

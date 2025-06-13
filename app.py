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
        
    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    main()
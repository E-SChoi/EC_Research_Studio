
import sqlite3
from pathlib import Path
from datetime import datetime

DB_NAME = "research_studio.db"

def get_db_path(project_path):
    return Path(project_path) / DB_NAME

def connect(project_path):
    db_path = get_db_path(project_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(db_path)

def init_database(project_path):
    conn = connect(project_path)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS sensors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        electrode_type TEXT,
        material TEXT,
        manufacturer TEXT,
        note TEXT,
        created_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS samples (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        target_type TEXT,
        sequence TEXT,
        supplier TEXT,
        lot TEXT,
        note TEXT,
        created_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS recognition_elements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        element_type TEXT,
        sequence TEXT,
        modification TEXT,
        supplier TEXT,
        note TEXT,
        created_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS reagents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        reagent_type TEXT,
        composition TEXT,
        concentration TEXT,
        pH TEXT,
        note TEXT,
        created_at TEXT
    )
    """)

    conn.commit()
    conn.close()

def add_record(project_path, table, data):
    init_database(project_path)
    conn = connect(project_path)
    cur = conn.cursor()

    data = dict(data)
    data["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cols = list(data.keys())
    placeholders = ", ".join(["?"] * len(cols))
    sql = f"INSERT OR REPLACE INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
    cur.execute(sql, [data[c] for c in cols])

    conn.commit()
    conn.close()

def get_table(project_path, table):
    init_database(project_path)
    conn = connect(project_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM {table} ORDER BY id DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

def get_names(project_path, table):
    rows = get_table(project_path, table)
    return [r.get("name", "") for r in rows if r.get("name")]

def seed_default_database(project_path):
    init_database(project_path)

    defaults = [
        ("sensors", {
            "name": "Carbon SPE",
            "electrode_type": "Screen-printed electrode",
            "material": "Carbon",
            "manufacturer": "",
            "note": "Default carbon screen-printed electrode"
        }),
        ("sensors", {
            "name": "Gold SPE",
            "electrode_type": "Screen-printed electrode",
            "material": "Gold",
            "manufacturer": "",
            "note": "Default gold screen-printed electrode"
        }),
        ("samples", {
            "name": "RNA target",
            "target_type": "RNA",
            "sequence": "",
            "supplier": "",
            "lot": "",
            "note": ""
        }),
        ("samples", {
            "name": "Protein target",
            "target_type": "Protein",
            "sequence": "",
            "supplier": "",
            "lot": "",
            "note": ""
        }),
        ("recognition_elements", {
            "name": "Aptamer",
            "element_type": "Aptamer",
            "sequence": "",
            "modification": "",
            "supplier": "",
            "note": ""
        }),
        ("recognition_elements", {
            "name": "Antibody",
            "element_type": "Antibody",
            "sequence": "",
            "modification": "",
            "supplier": "",
            "note": ""
        }),
        ("reagents", {
            "name": "Fe(CN)6 / KCl",
            "reagent_type": "Redox probe",
            "composition": "5 mM Fe(CN)6 in 0.1 M KCl",
            "concentration": "5 mM / 0.1 M",
            "pH": "",
            "note": "Default electrochemical redox probe"
        }),
        ("reagents", {
            "name": "PBS",
            "reagent_type": "Buffer",
            "composition": "PBS",
            "concentration": "",
            "pH": "7.4",
            "note": ""
        }),
    ]

    for table, data in defaults:
        add_record(project_path, table, data)

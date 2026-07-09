from pathlib import Path
from datetime import datetime
from utils.json_io import load_json, save_json
from database.db import seed_default_database

BASE_DIR = Path("projects")

def safe_name(name: str) -> str:
    return name.strip().replace(" ", "_").replace("/", "_").replace("\\", "_")

def create_project(project_name: str) -> Path:
    BASE_DIR.mkdir(exist_ok=True)
    folder_name = safe_name(project_name)
    project_path = BASE_DIR / folder_name
    project_path.mkdir(exist_ok=True)

    for sub in ["Experiments", "RawData", "Results", "Figures", "Reports", "PublicationFigures", "Database"]:
        (project_path / sub).mkdir(exist_ok=True)

    info = {
        "project_name": project_name,
        "folder_name": folder_name,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "version": "0.6",
        "experiments": []
    }
    save_json(project_path / "project.json", info)
    seed_default_database(project_path)
    return project_path

def list_projects():
    BASE_DIR.mkdir(exist_ok=True)
    return [p.name for p in BASE_DIR.iterdir() if p.is_dir()]

def open_project(folder_name: str):
    project_path = BASE_DIR / folder_name
    return project_path, load_json(project_path / "project.json")

def create_experiment(project_path: Path, project_info: dict, exp_info: dict) -> Path:
    exp_folder = safe_name(exp_info["experiment_name"])
    exp_path = project_path / "Experiments" / exp_folder
    exp_path.mkdir(parents=True, exist_ok=True)

    for sub in ["RawData", "Results", "Figures", "Reports", "Notes", "PublicationFigures"]:
        (exp_path / sub).mkdir(exist_ok=True)

    exp_info["folder_name"] = exp_folder
    exp_info["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    exp_info.setdefault("raw_files", [])
    exp_info.setdefault("results", [])
    exp_info.setdefault("publication_figures", [])

    save_json(exp_path / "experiment.json", exp_info)

    if exp_folder not in project_info["experiments"]:
        project_info["experiments"].append(exp_folder)
        save_json(project_path / "project.json", project_info)

    return exp_path

from pathlib import Path
from datetime import datetime
import zipfile

def create_project_backup(project_path):
    project_path = Path(project_path)
    backup_dir = project_path / "Backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = backup_dir / f"{project_path.name}_backup_{timestamp}.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in project_path.rglob("*"):
            if p.is_file() and "Backups" not in p.parts:
                z.write(p, p.relative_to(project_path))

    return zip_path

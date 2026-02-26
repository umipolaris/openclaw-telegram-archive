import os
import shutil
from pathlib import Path


def put_file(root_dir: str, storage_key: str, content: bytes) -> str:
    target_path = Path(root_dir) / storage_key
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(content)
    return str(target_path)


def put_file_from_path(root_dir: str, storage_key: str, source_path: str) -> str:
    target_path = Path(root_dir) / storage_key
    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.with_suffix(f"{target_path.suffix}.uploading")
    with open(source_path, "rb") as src, open(tmp_path, "wb") as dst:
        shutil.copyfileobj(src, dst, length=1024 * 1024)
    os.replace(tmp_path, target_path)
    return str(target_path)


def delete_file(root_dir: str, storage_key: str) -> None:
    target_path = Path(root_dir) / storage_key
    target_path.unlink(missing_ok=True)

from pathlib import Path


def put_file(root_dir: str, storage_key: str, content: bytes) -> str:
    target_path = Path(root_dir) / storage_key
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(content)
    return str(target_path)


def delete_file(root_dir: str, storage_key: str) -> None:
    target_path = Path(root_dir) / storage_key
    target_path.unlink(missing_ok=True)

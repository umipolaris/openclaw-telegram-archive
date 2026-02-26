import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")
IntegrityError = sqlalchemy.exc.IntegrityError

from app.services.error_codes import IngestErrorCode, classify_exception_for_stage


def test_classify_storage_stage_errors():
    assert classify_exception_for_stage(FileNotFoundError("missing"), "STORED") == IngestErrorCode.STORAGE_TEMP_FILE_MISSING
    assert classify_exception_for_stage(PermissionError("denied"), "STORED") == IngestErrorCode.STORAGE_READ_FAIL
    assert classify_exception_for_stage(RuntimeError("boom"), "STORED") == IngestErrorCode.STORAGE_WRITE_FAIL


def test_classify_indexed_stage_errors():
    assert classify_exception_for_stage(IntegrityError("stmt", {}, Exception("db")), "INDEXED") == IngestErrorCode.DB_WRITE_FAIL


def test_classify_unknown_stage_defaults_pipeline_unexpected():
    assert classify_exception_for_stage(RuntimeError("x"), "UNKNOWN") == IngestErrorCode.PIPELINE_UNEXPECTED

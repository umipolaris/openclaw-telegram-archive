import pytest


@pytest.mark.skip(reason="requires postgres/redis/minio containers")
def test_ingest_e2e_placeholder():
    assert True

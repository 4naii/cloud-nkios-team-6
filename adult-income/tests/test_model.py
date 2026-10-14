"""모델 테스트 (FastAPI 없이도 실행 가능): pytest -q tests/test_model.py"""
from scripts.validate import main


def test_validation_passes():
    assert main() is True

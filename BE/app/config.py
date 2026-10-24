"""설정값을 한곳에서 읽습니다.

.env 파일(커밋 금지)에서 값을 읽고, 없으면 기본값을 씁니다.
AI API 키는 오직 여기서만 읽습니다 (CONVENTIONS §11).
"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # 테스트 환경 등 python-dotenv가 없을 때
    load_dotenv = None

BE_DIR = Path(__file__).resolve().parents[1]   # .../FashionERP/BE
REPO_DIR = BE_DIR.parent                        # .../FashionERP

if load_dotenv:
    # .env 는 저장소 루트에 둡니다 (.env.example 과 같은 위치, CONVENTIONS §12).
    # BE/.env 도 읽어 주되 루트가 우선입니다.
    load_dotenv(REPO_DIR / ".env")
    load_dotenv(BE_DIR / ".env", override=False)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./fashion_erp.db")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "")

# 다른 팀이 관리하는 파일 위치 (BE 코드는 읽기만 합니다)
ORDERS_CSV = REPO_DIR / "datasets" / "product_return_dataset_2000.csv"
SAMPLE_DIR = REPO_DIR / "DATA" / "sample"
ENUMS_JSON = REPO_DIR / "DATA" / "enums.json"
AI_FALLBACK_JSON = REPO_DIR / "AI" / "fallback" / "returns-analyze.json"


def db_path() -> str:
    """sqlite:///./fashion_erp.db → BE 폴더 기준의 실제 파일 경로"""
    raw = DATABASE_URL.replace("sqlite:///", "", 1)
    path = Path(raw)
    if not path.is_absolute():
        path = BE_DIR / path
    return str(path)

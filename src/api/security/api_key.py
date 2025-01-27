from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# FastAPI security scheme
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

async def get_api_key(api_key: str = Security(api_key_header)) -> str:
    """Dependency for validating API key"""
    master_key = os.environ.get("MASTER_API_KEY")
    if not master_key:
        raise HTTPException(
            status_code=500,
            detail="MASTER_API_KEY not configured"
        )
    if api_key != master_key:
        raise HTTPException(
            status_code=403,
            detail="Invalid API key"
        )
    return api_key

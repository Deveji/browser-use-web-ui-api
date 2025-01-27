from datetime import datetime, timedelta
from typing import Dict, Optional, Any
import secrets
import time
from fastapi import HTTPException, Security, Header
from fastapi.security import APIKeyHeader

class APIKeyManager:
    def __init__(self):
        self.api_keys: Dict[str, Dict] = {}
        self.key_prefix = "bua_"  # browser-use-api prefix
        
    def generate_key(self, expires_in_days: Optional[int] = 30) -> str:
        """Generate a new API key with expiration"""
        key = f"{self.key_prefix}{secrets.token_urlsafe(32)}"
        days = 30 if expires_in_days is None else expires_in_days
        expiration = datetime.utcnow() + timedelta(days=days)
        
        self.api_keys[key] = {
            "created_at": datetime.utcnow(),
            "expires_at": expiration,
            "is_active": True,
            "last_used": None,
            "usage_count": 0
        }
        return key
    
    def validate_key(self, api_key: str) -> bool:
        """Validate an API key"""
        if api_key not in self.api_keys:
            return False
            
        key_data = self.api_keys[api_key]
        
        # Check if key is active and not expired
        if not key_data["is_active"]:
            return False
            
        if datetime.utcnow() > key_data["expires_at"]:
            key_data["is_active"] = False
            return False
            
        # Update usage statistics
        key_data["last_used"] = datetime.utcnow()
        key_data["usage_count"] += 1
        
        return True
    
    def revoke_key(self, api_key: str) -> bool:
        """Revoke an API key"""
        if api_key in self.api_keys:
            self.api_keys[api_key]["is_active"] = False
            return True
        return False
    
    def rotate_key(self, old_key: str) -> Optional[str]:
        """Rotate an API key - generate new and revoke old"""
        if self.validate_key(old_key):
            new_key = self.generate_key()
            self.revoke_key(old_key)
            return new_key
        return None
    
    def get_key_info(self, api_key: str) -> Optional[Dict[str, Any]]:
        """Get information about an API key"""
        key_info = self.api_keys.get(api_key)
        if key_info is None:
            raise HTTPException(
                status_code=404,
                detail="API key not found"
            )
        return key_info
    
    def list_active_keys(self) -> Dict[str, Dict[str, Any]]:
        """Get all active API keys and their information"""
        return {
            key: info for key, info in self.api_keys.items()
            if info["is_active"] and datetime.utcnow() <= info["expires_at"]
        }

# Create global instance
api_key_manager = APIKeyManager()

# FastAPI security scheme
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

async def get_api_key(api_key: str = Security(api_key_header)) -> str:
    """Dependency for validating API key"""
    if not api_key_manager.validate_key(api_key):
        raise HTTPException(
            status_code=403,
            detail="Invalid or expired API key"
        )
    return api_key

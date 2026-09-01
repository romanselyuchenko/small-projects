from fastapi import FastAPI, Response, Cookie, Header, HTTPException
from pydantic import BaseModel, Field, field_validator
from packaging import version

import uuid
from itsdangerous import URLSafeSerializer
from datetime import datetime, timedelta
from typing import Annotated
from datetime import datetime

app = FastAPI()

MINIMUM_APP_VERSION = "0.0.2"


class CommonHeaders(BaseModel):
    model_config = {"populate_by_name": True}
    user_agent: str | None = None
    accept_language: str | None = None
    x_current_version: str = Field(..., description="Version format 0.0.n", )

    @field_validator("x_current_version")
    @classmethod
    def check_version(cls, v: str):
        try:
            parsed = version.parse(v)
        except Exception:
            raise ValueError("Invalid version format. Expected x.y.z")
        
        if parsed < version.parse(MINIMUM_APP_VERSION):
            raise ValueError(f"Minimum supported version is {MINIMUM_APP_VERSION}")
        
        return v

@app.get('/headers')
async def get_headers(headers: Annotated[CommonHeaders, Header()]):
    if not headers.user_agent:
        raise HTTPException(status_code=400, detail="<str>")
    
    return {"User-Agent": headers.user_agent, "Accept-Language": headers.accept_language}

@app.get("/info")
def info(response: Response, headers: Annotated[CommonHeaders, Header()]):
    
    if not headers.user_agent:
        raise HTTPException(status_code=400, detail="<str>")
    
    response.headers["X-Server-Time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return {
            "User-Agent": headers.user_agent, 
            "Accept-Language": headers.accept_language, 
            "message": "Добро пожаловать! Ваши заголовки успешно обработаны."
            }



"""人设管理 API"""
from fastapi import APIRouter
from pydantic import BaseModel
from personas import list_personas, get_persona, add_persona, remove_persona

router = APIRouter(prefix="/personas", tags=["personas"])


class PersonaCreate(BaseModel):
    id: str
    name: str
    prompt: str = ""
    emoji: str = ""


@router.get("")
async def api_list_personas():
    return {"personas": list_personas()}


@router.get("/{pid}")
async def api_get_persona(pid: str):
    p = get_persona(pid)
    if not p:
        return {"error": "人设不存在"}, 404
    return {"persona": p}


@router.post("")
async def api_add_persona(data: PersonaCreate):
    add_persona(data.model_dump())
    return {"status": "ok"}


@router.delete("/{pid}")
async def api_remove_persona(pid: str):
    remove_persona(pid)
    return {"status": "ok"}

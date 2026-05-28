"""Telegram bot management routes — send alerts, broadcast, check updates."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/telegram", tags=["telegram"])


class MessageRequest(BaseModel):
    chat_id: str
    text: str
    parse_mode: str = "Markdown"


class AlertRequest(BaseModel):
    title: str
    body: str
    level: str = "INFO"


@router.post("/send")
async def send_message(req: MessageRequest):
    from integrations import telegram_bot
    result = telegram_bot.send(req.chat_id, req.text, req.parse_mode)
    if not result:
        raise HTTPException(502, "Telegram send failed — check TELEGRAM_BOT_TOKEN")
    return result


@router.post("/broadcast")
async def broadcast(req: AlertRequest):
    from integrations import telegram_bot
    telegram_bot.alert(req.title, req.body, req.level)
    return {"status": "broadcast sent", "level": req.level}


@router.get("/updates")
async def get_updates(offset: int = 0):
    from integrations import telegram_bot
    updates = telegram_bot.get_updates(offset)
    return {"updates": updates, "count": len(updates)}


@router.post("/alert")
async def send_alert(req: AlertRequest):
    from integrations import telegram_bot
    telegram_bot.alert(req.title, req.body, req.level)
    return {"status": "ok", "title": req.title}

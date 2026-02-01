from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger
import httpx
from app.admin.auth import get_current_user
from config.settings import settings

router = APIRouter(prefix="/files", tags=["files"])

@router.get("/{file_id}")
async def get_telegram_file(
    file_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Telegram file proxy
    """
    try:
        # 1. Get file path from Telegram API
        async with httpx.AsyncClient() as client:
            token = settings.BOT_TOKEN
            
            # getFile
            info_res = await client.get(
                f"https://api.telegram.org/bot{token}/getFile?file_id={file_id}"
            )
            
            if info_res.status_code != 200:
                raise HTTPException(status_code=404, detail="File not found in Telegram")
                
            info = info_res.json()
            if not info.get("ok"):
                raise HTTPException(status_code=400, detail=info.get("description"))
                
            file_path = info["result"]["file_path"]
            file_url = f"https://api.telegram.org/file/bot{token}/{file_path}"
            
            # 2. Stream file content back to client
            # We create a new client for streaming to avoid closing it prematurely
            # or we can read it all if it's small. For images, reading all is safer/easier.
            
            file_res = await client.get(file_url)
            
            if file_res.status_code != 200:
                raise HTTPException(status_code=404, detail="Failed to download file")
                
            return StreamingResponse(
                content=file_res.iter_bytes(),
                media_type=file_res.headers.get("content-type", "image/jpeg")
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to proxy file {file_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

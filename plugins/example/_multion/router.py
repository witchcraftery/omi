import asyncio
import json
import os
from typing import List

import httpx
from dotenv import load_dotenv
from fastapi import APIRouter, Request, Form, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

import db
from models import RealtimePluginRequest, TranscriptSegment

load_dotenv()

router = APIRouter()

templates = Jinja2Templates(directory="templates")

GROQ_API_KEY = os.getenv('GROQ_API_KEY')
MULTION_API_KEY = os.getenv('MULTION_API_KEY', '123')


async def retrieve_books_to_buy(transcript: str) -> List[str]:
    print('retrieve_books_to_buy')
    groq_api_url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    prompt = f"""
    Analyze the following transcript and identify any book titles mentioned or suggested:
    {transcript}
    Return only a JSON array of book titles, without any additional text. If no books are mentioned or suggested, return an empty array.
    """

    payload = {
        "model": "llama3-8b-8192",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 150
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(groq_api_url, headers=headers, json=payload)
            response.raise_for_status()
            response_data = response.json()
            content = response_data['choices'][0]['message']['content']
            print(f"retrieve_books_to_buy, Raw GROQ API response: {content}")

            import re
            json_match = re.search(r'\[.*\]', content, re.DOTALL)
            if json_match:
                book_titles = json.loads(json_match.group())
            else:
                raise ValueError("retrieve_books_to_buy, No JSON array found in the response")

            print('retrieve_books_to_buy, Books to buy:', book_titles)
            return book_titles
    except Exception as e:
        print(f"retrieve_books_to_buy: error {e}")
        return []


async def call_multion(books: List[str], user_id: str):
    print('call_multion', f'Buying books with MultiOn for user_id: {user_id}')
    headers = {
        "X_MULTION_API_KEY": MULTION_API_KEY,
        "Content-Type": "application/json"
    }

    data = {
        "url": "https://amazon.com",
        "cmd": f"Add to my cart the following books (in paperback version, or any physical version): {books}. Only add the books, do not add anything else. and then say success.",
        "user_id": user_id,
        "local": False,
        "use_proxy": True,
        "include_screenshot": True
    }

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            print(f"Sending request to Multion API: {data}")
            response = await client.post(
                "https://api.multion.ai/v1/web/browse",
                headers=headers,
                json=data
            )
            response.raise_for_status()
            result = response.json()
            print(f"MultiOn API response: {result}")
            if result.get('status') != "DONE":
                return await retry_multion(result.get('session_id'))
            return result.get('message')
    except httpx.HTTPStatusError as e:
        print(f"HTTP error occurred: {e.response.status_code} {e.response.text}")
        raise
    except httpx.RequestError as e:
        print(f"An error occurred while requesting {e.request.url!r}.")
        raise
    except Exception as e:
        print(f"Unexpected error in call_multion: {str(e)}")
        raise


async def retry_multion(session_id: str):
    headers = {
        "X_MULTION_API_KEY": MULTION_API_KEY,
        "Content-Type": "application/json"
    }

    data = {
        "session_id": session_id,
        "cmd": "Try again",
        "url": "https://amazon.com",
        "local": False,
        "use_proxy": True,
        "include_screenshot": True
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.multion.ai/v1/web/browse",
                headers=headers,
                json=data
            )
            response.raise_for_status()
            return response.json().get('message')
    except httpx.HTTPStatusError as e:
        print(f"HTTP error occurred: {e.response.status_code} {e.response.text}")
        return f"HTTP error: {e.response.status_code}"
    except httpx.RequestError as e:
        print(f"An error occurred while requesting {e.request.url!r}.")
        return f"Request error: {str(e)}"
    except Exception as e:
        print(f"Unexpected error in retry_multion: {str(e)}")
        return f"Unexpected error: {str(e)}"


@router.get("/multion", response_class=HTMLResponse, tags=['multion'])
async def get_integration_page(request: Request):
    org_id = os.getenv('MULTION_ORG_ID')
    return templates.TemplateResponse("setup_multion_desktop.html", {"request": request, "org_id": org_id})


@router.get("/multion/callback", response_class=HTMLResponse, tags=['multion'])
async def oauth_callback(request: Request):
    user_id = request.query_params.get("user_id")
    if user_id:
        return templates.TemplateResponse("setup_multion_userid.html", {"request": request, "user_id": user_id})
    return "User ID not found in redirect."


@router.get("/multion/uid_input", response_class=HTMLResponse, tags=['multion'])
async def setup_uid_page(request: Request):
    uid = request.query_params.get("uid")
    if not uid:
        raise HTTPException(status_code=400, detail="UID not provided in the URL")
    return templates.TemplateResponse("setup_multion_phone.html", {"request": request, "uid": uid})


@router.post("/multion/submit_uid", tags=['multion'])
async def submit_uid(request: Request, user_id: str = Form(...), uid: str = Form(...)):
    db.store_multion_user_id(uid, user_id)
    is_setup_completed = db.get_multion_user_id(uid) is not None
    return templates.TemplateResponse("setup_multion_complete.html", {
        "request": request,
        "is_setup_completed": is_setup_completed,
        "user_id": user_id
    })


@router.get("/multion/check_setup_completion", tags=['multion'])
async def check_setup_completion(uid: str = Query(...)):
    user_id = db.get_multion_user_id(uid)
    is_setup_completed = user_id is not None
    return {"is_setup_completed": is_setup_completed}


@router.post("/multion/process_transcript", tags=['multion'])
async def initiate_process_transcript(data: RealtimePluginRequest, uid: str = Query(...)):
    user_id = db.get_multion_user_id(uid)
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid UID or USERID not found.")

    transcript = TranscriptSegment.segments_as_string(data.segments)

    try:
        books = await retrieve_books_to_buy(transcript)
        result = await asyncio.wait_for(call_multion(books, user_id), timeout=120)
    except asyncio.TimeoutError:
        print("Timeout error occurred")
        return
    except Exception as e:
        print(f"Error calling Multion API: {str(e)}")
        return

    if isinstance(result, bytes):
        result = result.decode('utf-8')
        return {"message": result}

    return {"message": ''}

# @router.post("/multion", response_model=EndpointResponse, tags=['multion'])
# async def multion_endpoint(memory: Memory, uid: str = Query(...)):
#     user_id = db.get_multion_user_id(uid)
#     if not user_id:
#         raise HTTPException(status_code=400, detail="Invalid UID or USERID not found.")
#
#     books = await retrieve_books_to_buy(memory)
#     if not books:
#         return EndpointResponse(message='No books were suggested or mentioned.')
#
#     result = await call_multion(books, user_id)
#     if isinstance(result, bytes):
#         result = result.decode('utf-8')
#
#     return EndpointResponse(message=result)

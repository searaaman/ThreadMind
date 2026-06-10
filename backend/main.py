from database import save_message, get_history
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv
from google import genai
import os

load_dotenv()

app = FastAPI()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

class ChatRequest(BaseModel):
    user_id: str
    message: str

@app.get("/")
def home():
    return {"message": "Chatbot backend is running!"}

@app.post("/chat")
def chat(request: ChatRequest):
    save_message(
        request.user_id,
        "User",
        request.message
    )
    history= get_history (request.user_id)
    print(history)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents="\n".join(history)
        
    )

    save_message(
        request.user_id,
        "AI",
        response.text
    )
    
    return {
        "reply": response.text
    }
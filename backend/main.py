from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv
from google import genai
import os

conversation_history = []
load_dotenv()

app = FastAPI()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

class ChatRequest(BaseModel):
    message: str

@app.get("/")
def home():
    return {"message": "Chatbot backend is running!"}

@app.post("/chat")
def chat(request: ChatRequest):
    conversation_history.append(f"User: {request.message}")
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents="\n".join(conversation_history),
    )
    
    conversation_history.append(f"AI: {response.text}")

    return {
        "reply": response.text
    }
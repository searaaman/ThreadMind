from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv
from google import genai
import os

conversation_histories = {}
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
    if request.user_id not in conversation_histories:
        conversation_histories[request.user_id] = []
    conversation_histories[request.user_id].append(f"User: {request.message}")
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents="\n".join(conversation_histories[request.user_id])
    )

    conversation_histories[request.user_id].append(f"AI: {response.text}")

    return {
        "reply": response.text
    }
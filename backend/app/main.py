from dotenv import load_dotenv
load_dotenv() # Load variables from .env file if it exists

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
import yfinance as yf
from app.database import engine, get_db
from app import models
from app.chat import generate_chat_response
import traceback

# Create database tables
models.Base.metadata.create_all(bind=engine)

# Pydantic schemas for Chat
class ChatSessionCreate(BaseModel):
    title: Optional[str] = "New Chat"

class ChatSessionResponse(BaseModel):
    id: str
    title: str
    created_at: str
    
class MessageCreate(BaseModel):
    content: str

class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    created_at: str

app = FastAPI(title="vittSarathi API")

# Allow connections from the frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {
        "status": "running",
        "message": "FastAPI backend container is active!"
    }

@app.get("/api/stock/{ticker}")
def get_stock_data(ticker: str):
    ticker = ticker.upper().strip()
    
    # Try the raw ticker first
    ticker_obj = yf.Ticker(ticker)
    info = {}
    try:
        info = ticker_obj.info
    except Exception:
        info = {}
        
    # If the ticker has no substantial information and doesn't contain a dot,
    # try automatically appending .NS (National Stock Exchange of India)
    if not info or not info.get("marketCap") or not info.get("longName"):
        if "." not in ticker:
            indian_ticker = f"{ticker}.NS"
            try:
                indian_ticker_obj = yf.Ticker(indian_ticker)
                indian_info = indian_ticker_obj.info
                if indian_info and (indian_info.get("marketCap") or indian_info.get("longName")):
                    info = indian_info
                    ticker = indian_ticker
            except Exception:
                pass

    # If still not found or insufficient information, try BSE (.BO)
    if not info or not info.get("marketCap") or not info.get("longName"):
        if "." not in ticker:
            indian_ticker_bse = f"{ticker}.BO"
            try:
                bse_ticker_obj = yf.Ticker(indian_ticker_bse)
                bse_info = bse_ticker_obj.info
                if bse_info and (bse_info.get("marketCap") or bse_info.get("longName")):
                    info = bse_info
                    ticker = indian_ticker_bse
            except Exception:
                pass
                
    # If still no substantial info is retrieved, raise 404
    if not info or (not info.get("marketCap") and not info.get("longName") and not info.get("currentPrice") and not info.get("regularMarketPrice")):
        raise HTTPException(
            status_code=404, 
            detail=f"Stock ticker '{ticker}' not found or no data available. Note: For Indian stocks, try appending .NS (e.g. RELIANCE.NS)."
        )
        
    # Helper functions to convert values safely
    def safe_float(val):
        if val is None:
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    def safe_int(val):
        if val is None:
            return None
        try:
            return int(val)
        except (ValueError, TypeError):
            return None

    # Construct clean structured response with all 12 categories
    payload = {
        "symbol": info.get("symbol", ticker),
        "longName": info.get("longName", info.get("shortName", ticker)),
        "currency": info.get("currency", "USD"),
        "currentPrice": safe_float(info.get("currentPrice", info.get("regularMarketPrice"))),
        "summary": info.get("longBusinessSummary", ""),
        "sector": info.get("sector", "N/A"),
        "industry": info.get("industry", "N/A"),
        
        # 1. Valuation
        "peRatio": safe_float(info.get("trailingPE", info.get("forwardPE"))),
        
        # 2. Growth
        "revenueGrowth": safe_float(info.get("revenueGrowth")),
        "earningsGrowth": safe_float(info.get("earningsGrowth")),
        
        # 3. Profitability
        "profitMargin": safe_float(info.get("profitMargins")),
        "roe": safe_float(info.get("returnOnEquity")),
        
        # 4. Financial Health
        "debtToEquity": safe_float(info.get("debtToEquity")),
        
        # 5. Market Sentiment
        "recommendation": info.get("recommendationKey", "N/A"),
        "targetPrice": safe_float(info.get("targetMeanPrice", info.get("targetMedianPrice"))),
        
        # 6. Share Data
        "marketCap": safe_int(info.get("marketCap")),
        "sharesOutstanding": safe_int(info.get("sharesOutstanding")),
        "floatShares": safe_int(info.get("floatShares")),
        
        # 7. Trading Activity
        "volume": safe_int(info.get("volume", info.get("regularMarketVolume"))),
        "averageVolume": safe_int(info.get("averageVolume", info.get("averageVolume10days"))),
        
        # 8. Risk
        "beta": safe_float(info.get("beta")),
        
        # 9. Income
        "dividendYield": safe_float(info.get("dividendYield")),
        "payoutRatio": safe_float(info.get("payoutRatio")),
        
        # 10. Momentum
        "fiftyTwoWeekHigh": safe_float(info.get("fiftyTwoWeekHigh")),
        "fiftyTwoWeekLow": safe_float(info.get("fiftyTwoWeekLow")),
        "fiftyDayAverage": safe_float(info.get("fiftyDayAverage")),
        "twoHundredDayAverage": safe_float(info.get("twoHundredDayAverage")),
        
        # 11. Ownership
        "heldPercentInstitutions": safe_float(info.get("heldPercentInstitutions")),
        "heldPercentInsiders": safe_float(info.get("heldPercentInsiders")),
        
    # 12. Cash Flow
        "freeCashFlow": safe_int(info.get("freeCashFlow"))
    }
    
    return payload

# --- Chat Endpoints ---

@app.post("/api/chat/sessions", response_model=ChatSessionResponse)
def create_chat_session(session_data: ChatSessionCreate, db: Session = Depends(get_db)):
    db_session = models.ChatSession(title=session_data.title)
    db.add(db_session)
    db.commit()
    db.refresh(db_session)
    return {
        "id": db_session.id, 
        "title": db_session.title, 
        "created_at": db_session.created_at.isoformat()
    }

@app.get("/api/chat/sessions", response_model=List[ChatSessionResponse])
def get_chat_sessions(db: Session = Depends(get_db)):
    sessions = db.query(models.ChatSession).order_by(models.ChatSession.created_at.desc()).all()
    return [
        {
            "id": session.id,
            "title": session.title,
            "created_at": session.created_at.isoformat()
        }
        for session in sessions
    ]

@app.delete("/api/chat/sessions/{session_id}")
def delete_chat_session(session_id: str, db: Session = Depends(get_db)):
    db_session = db.query(models.ChatSession).filter(models.ChatSession.id == session_id).first()
    if not db_session:
        raise HTTPException(status_code=404, detail="Chat session not found")
        
    db.delete(db_session)
    db.commit()
    return {"message": "Session deleted successfully"}

@app.get("/api/chat/sessions/{session_id}/messages", response_model=List[MessageResponse])
def get_chat_messages(session_id: str, db: Session = Depends(get_db)):
    db_session = db.query(models.ChatSession).filter(models.ChatSession.id == session_id).first()
    if not db_session:
        raise HTTPException(status_code=404, detail="Chat session not found")
        
    messages = []
    for msg in db_session.messages:
        messages.append({
            "id": msg.id,
            "role": msg.role,
            "content": msg.content,
            "created_at": msg.created_at.isoformat()
        })
    return messages

@app.post("/api/chat/sessions/{session_id}/message", response_model=MessageResponse)
def send_chat_message(session_id: str, message_data: MessageCreate, db: Session = Depends(get_db)):
    # 1. Verify session exists
    db_session = db.query(models.ChatSession).filter(models.ChatSession.id == session_id).first()
    if not db_session:
        raise HTTPException(status_code=404, detail="Chat session not found")
        
    # 2. Save user message
    user_msg = models.ChatMessage(session_id=session_id, role="user", content=message_data.content)
    db.add(user_msg)
    db.commit()
    
    # 3. Retrieve chat history
    history = db.query(models.ChatMessage).filter(models.ChatMessage.session_id == session_id).order_by(models.ChatMessage.created_at).all()
    
    # Exclude the message we just added from the history passed as context (or we can just pass everything except the last and then append it in chat.py)
    # Actually, chat.py signature takes history and new message separately, so let's exclude the last one.
    history_dicts = [{"role": msg.role, "content": msg.content} for msg in history[:-1]]
    
    # 4. Generate AI response
    try:
        ai_response_content = generate_chat_response(history_dicts, message_data.content)
    except Exception as e:
        error_details = traceback.format_exc()
        print(f"ERROR generating chat response:\n{error_details}")
        raise HTTPException(status_code=500, detail=f"Failed to generate response: {str(e)}\n\nDetails:\n{error_details}")
        
    # 5. Save AI message
    ai_msg = models.ChatMessage(session_id=session_id, role="assistant", content=ai_response_content)
    db.add(ai_msg)
    db.commit()
    db.refresh(ai_msg)
    
    return {
        "id": ai_msg.id,
        "role": ai_msg.role,
        "content": ai_msg.content,
        "created_at": ai_msg.created_at.isoformat()
    }

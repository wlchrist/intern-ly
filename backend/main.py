from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from pydantic import BaseModel
import httpx
import os
from dotenv import load_dotenv

load_dotenv()

# Initialize rate limiter (IP-based)
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Resume Tailor API")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS configuration for Chrome extension
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your extension ID
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Get API key from environment
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY environment variable not set")

ANTHROPIC_API_VERSION = os.getenv("ANTHROPIC_API_VERSION", "2023-06-01")


class RewriteRequest(BaseModel):
    draft: str
    temperature: float = 0.2
    max_tokens: int = 700


class RewriteResponse(BaseModel):
    rewritten: str


@app.get("/")
async def root():
    return {"status": "ok", "service": "Resume Tailor API"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/api/rewrite", response_model=RewriteResponse)
@limiter.limit("10/minute")  # 10 requests per minute per IP
async def rewrite_resume(request: Request, data: RewriteRequest):
    """
    Proxy endpoint for Anthropic API with rate limiting.
    Rate limit: 10 requests per minute per IP address.
    """
    
    if not data.draft or len(data.draft.strip()) == 0:
        raise HTTPException(status_code=400, detail="Draft content is required")
    
    # Prepare Anthropic API request
    anthropic_url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": ANTHROPIC_API_VERSION,
        "content-type": "application/json",
    }
    
    payload = {
        "model": "claude-3-5-haiku-latest",
        "max_tokens": data.max_tokens,
        "temperature": data.temperature,
        "messages": [
            {
                "role": "user",
                "content": f"""You are a professional resume writer. Rewrite the following resume draft to make it more compelling and professional while keeping ALL factual details unchanged.

STRICT REQUIREMENTS:
1. Do NOT add any new facts, experiences, or technologies not present in the original
2. Do NOT exaggerate or fabricate achievements
3. Keep all bullet points factual and specific
4. Improve clarity, impact, and professional tone
5. Maintain technical accuracy

Return ONLY valid JSON in this exact format:
{{"bullets": ["bullet 1", "bullet 2", ...], "skills": ["skill1", "skill2", ...]}}

DRAFT TO REWRITE:
{data.draft}"""
            }
        ]
    }
    
    # Call Anthropic API
    try:
        print(f"Calling Anthropic API with model: {payload['model']}")
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(anthropic_url, headers=headers, json=payload)
            response.raise_for_status()
            
            anthropic_response = response.json()
            
            # Extract text content from response
            content = anthropic_response.get("content", [])
            if not content or not isinstance(content, list):
                raise HTTPException(status_code=500, detail="Invalid response from AI service")
            
            text_content = content[0].get("text", "")
            if not text_content:
                raise HTTPException(status_code=500, detail="Empty response from AI service")
            
            return RewriteResponse(rewritten=text_content)
            
    except httpx.HTTPStatusError as e:
        error_detail = ""
        try:
            error_detail = e.response.text
        except:
            error_detail = str(e)
        
        print(f"Anthropic API Error {e.response.status_code}: {error_detail}")
        
        if e.response.status_code == 401:
            raise HTTPException(status_code=500, detail="API authentication failed - check your API key")
        elif e.response.status_code == 429:
            raise HTTPException(status_code=429, detail="AI service rate limit exceeded. Please try again later.")
        else:
            raise HTTPException(status_code=500, detail=f"AI service error {e.response.status_code}: {error_detail}")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="AI service request timed out")
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from pydantic import BaseModel
import httpx
import json
import os
from io import BytesIO
import logging
from dotenv import load_dotenv

from schemas import ResumeJSON, JobDescription
from services import parse_resume, rewrite_resume, build_pdf

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize rate limiter (IP-based)
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Resume Tailor API - Structured")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS configuration for Chrome extension
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Get API key from environment
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY environment variable not set")

ANTHROPIC_API_VERSION = os.getenv("ANTHROPIC_API_VERSION", "2023-06-01")


# Request/Response models
class ParseRequest(BaseModel):
    resume_content: str


class RewriteRequest(BaseModel):
    resume: ResumeJSON
    job_description: JobDescription
    temperature: float = 0.2


class BuildRequest(BaseModel):
    resume: ResumeJSON


class TailorRequest(BaseModel):
    """Combined request for full tailoring pipeline"""
    resume_content: str
    job_description: str
    temperature: float = 0.2


# Utility function
async def call_anthropic(prompt: str, temperature: float, max_tokens: int) -> str:
    """Call Anthropic Claude API"""
    anthropic_url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": ANTHROPIC_API_VERSION,
        "content-type": "application/json",
    }

    payload = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }

    async with httpx.AsyncClient(timeout=40.0) as client:
        response = await client.post(anthropic_url, headers=headers, json=payload)
        response.raise_for_status()
        body = response.json()
        content = body.get("content", [])
        if not content or not isinstance(content, list):
            raise HTTPException(status_code=500, detail="Invalid response from AI service")

        text_content = content[0].get("text", "")
        if not text_content:
            raise HTTPException(status_code=500, detail="Empty response from AI service")
        return text_content


# Routes - Health/Status
@app.get("/")
async def root():
    return {"status": "ok", "service": "Resume Tailor API - Structured"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


# Routes - Service endpoints
@app.post("/api/parse")
@limiter.limit("20/minute")
async def parse_endpoint(request: Request, data: ParseRequest):
    """Parse resume content into structured JSON"""
    try:
        logger.info("Parsing resume...")
        resume = await parse_resume(data.resume_content, call_anthropic)
        return resume
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Parse error: {e}")
        raise HTTPException(status_code=500, detail=f"Parse service error: {e}")


@app.post("/api/rewrite")
@limiter.limit("20/minute")
async def rewrite_endpoint(request: Request, data: RewriteRequest):
    """Rewrite resume bullets to match job description"""
    try:
        logger.info("Rewriting resume...")
        rewritten = await rewrite_resume(data.resume, data.job_description, call_anthropic)
        return rewritten
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Rewrite error: {e}")
        raise HTTPException(status_code=500, detail=f"Rewrite service error: {e}")


@app.post("/api/build")
@limiter.limit("20/minute")
async def build_endpoint(request: Request, data: BuildRequest):
    """Build PDF from resume JSON"""
    try:
        logger.info("Building PDF...")
        pdf_bytes = await build_pdf(data.resume)
        
        return StreamingResponse(
            BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=resume.pdf"},
        )
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Build error: {e}")
        raise HTTPException(status_code=500, detail=f"Build service error: {e}")


@app.post("/api/tailor")
@limiter.limit("10/minute")
async def tailor_endpoint(request: Request, data: TailorRequest):
    """
    Full tailoring pipeline: Parse → Rewrite → Build
    
    Accepts raw resume content and job description.
    Returns PDF directly.
    """
    try:
        logger.info("Starting full tailor pipeline...")
        
        # Step 1: Parse resume
        logger.info("Step 1/3: Parsing resume...")
        resume = await parse_resume(data.resume_content, call_anthropic)
        
        # Step 2: Extract job keywords and rewrite
        logger.info("Step 2/3: Rewriting resume...")
        job_desc = JobDescription(
            keywords=[],
            technologies=[],
            responsibilities=[data.job_description],
            nice_to_haves=[]
        )
        rewritten = await rewrite_resume(resume, job_desc, call_anthropic)
        
        # Step 3: Build PDF
        logger.info("Step 3/3: Building PDF...")
        pdf_bytes = await build_pdf(rewritten)
        
        logger.info("Tailor pipeline complete!")
        return StreamingResponse(
            BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=tailored_resume.pdf"},
        )
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except httpx.HTTPStatusError as e:
        error_detail = ""
        try:
            error_detail = e.response.text
        except Exception:
            error_detail = str(e)
        
        logger.error(f"Anthropic API Error {e.response.status_code}: {error_detail}")
        
        if e.response.status_code == 401:
            raise HTTPException(status_code=500, detail="API authentication failed - check your API key")
        elif e.response.status_code == 429:
            raise HTTPException(status_code=429, detail="AI service rate limit exceeded. Please try again later.")
        else:
            raise HTTPException(status_code=500, detail=f"AI service error {e.response.status_code}")
    
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="AI service timeout. Please try again.")
    
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

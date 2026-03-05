from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from pydantic import BaseModel
import httpx
import json
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
    job_description: str
    temperature: float = 0.2
    max_tokens: int = 700


class TailorRequest(BaseModel):
    master_latex: str
    job_description: str
    temperature: float = 0.2
    max_tokens: int = 1400


class RewriteResponse(BaseModel):
    rewritten: str


class TailorResponse(BaseModel):
    output: str
    latex: str


def escape_latex_text(value: str) -> str:
    return (
        value.replace("\\", "\\textbackslash{}")
        .replace("#", "\\#")
        .replace("$", "\\$")
        .replace("%", "\\%")
        .replace("&", "\\&")
        .replace("_", "\\_")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("~", "\\textasciitilde{}")
        .replace("^", "\\textasciicircum{}")
    )


def build_output_text(summary: str, bullets: list[str], skills: list[str]) -> str:
    safe_summary = summary.strip() if summary.strip() else "Tailored internship-ready summary."
    safe_bullets = bullets if bullets else ["Add more quantified and role-relevant bullets from your resume."]
    safe_skills = skills if skills else ["Add relevant skills from your resume"]

    return "\n".join(
        [
            "TAILORED INTERNSHIP RESUME DRAFT",
            "",
            "Summary",
            safe_summary,
            "",
            "Selected Experience Bullets",
            *[f"- {item}" for item in safe_bullets],
            "",
            "Relevant Skills",
            " | ".join(safe_skills),
            "",
            "Notes",
            "- Content is selected and tailored from your uploaded master resume.",
            "- Irrelevant content to this JD is intentionally excluded.",
        ]
    )


def build_base_template_latex(summary: str, bullets: list[str], skills: list[str]) -> str:
    safe_summary = escape_latex_text(summary.strip() or "Tailored internship-ready summary.")
    safe_bullets = bullets if bullets else ["Add more quantified and role-relevant bullets from your resume."]
    safe_bullets_latex = [f"  \\item {escape_latex_text(item)}" for item in safe_bullets]
    safe_skills = escape_latex_text(" · ".join(skills) if skills else "Add relevant skills from your resume")

    return "\n".join(
        [
            "\\documentclass[10pt]{article}",
            "\\usepackage[margin=0.75in]{geometry}",
            "\\usepackage[T1]{fontenc}",
            "\\usepackage{enumitem}",
            "\\setlist[itemize]{leftmargin=1.2em, itemsep=2pt, topsep=2pt}",
            "\\begin{document}",
            "",
            "\\section*{Summary}",
            safe_summary,
            "",
            "\\section*{Experience Highlights}",
            "\\begin{itemize}",
            *safe_bullets_latex,
            "\\end{itemize}",
            "",
            "\\section*{Skills}",
            safe_skills,
            "",
            "\\end{document}",
            "",
        ]
    )


def try_extract_json(raw: str) -> dict | None:
    first = raw.find("{")
    last = raw.rfind("}")
    if first < 0 or last <= first:
        return None

    snippet = raw[first:last + 1]
    try:
        return json.loads(snippet)
    except json.JSONDecodeError:
        return None


async def call_anthropic(prompt: str, temperature: float, max_tokens: int) -> str:
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
    
    try:
        prompt = f"""You are a professional resume writer. Tailor the following resume draft to better match the job description while keeping ALL factual details unchanged.

JOB DESCRIPTION:
{data.job_description}

STRICT REQUIREMENTS:
1. Do NOT add any new facts, experiences, or technologies not present in the original
2. Do NOT exaggerate or fabricate achievements
3. Keep all bullet points factual and specific
4. Improve clarity, impact, and professional tone aligned with the job
5. Maintain technical accuracy
6. Emphasize relevant skills from the job description

Return ONLY valid JSON in this exact format:
{{"bullets": ["bullet 1", "bullet 2", ...], "skills": ["skill1", "skill2", ...]}}

DRAFT TO REWRITE:
{data.draft}"""
        text_content = await call_anthropic(prompt, data.temperature, data.max_tokens)
        return RewriteResponse(rewritten=text_content)

    except httpx.HTTPStatusError as e:
        error_detail = ""
        try:
            error_detail = e.response.text
        except Exception:
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


@app.post("/api/tailor", response_model=TailorResponse)
@limiter.limit("10/minute")
async def tailor_resume(request: Request, data: TailorRequest):
    if not data.master_latex.strip():
        raise HTTPException(status_code=400, detail="Master LaTeX resume is required")
    if not data.job_description.strip():
        raise HTTPException(status_code=400, detail="Job description is required")

    prompt = f"""You are an expert resume strategist.

TASK:
1) Parse the candidate's master LaTeX resume.
2) Compare it against the job description.
3) Select only the most relevant content.
4) Discard irrelevant content.
5) Rewrite selected bullets with better impact but keep facts strictly unchanged.

HARD RULES:
- Never add new facts, employers, degrees, dates, tools, metrics, or responsibilities.
- You may reorder and rephrase existing facts for relevance.
- Keep bullets concise and results-oriented.
- Keep 4-6 bullets and up to 12 skills.

Return ONLY strict JSON with this schema:
{{
  "summary": "string",
  "bullets": ["string", "string"],
  "skills": ["string", "string"]
}}

JOB DESCRIPTION:
{data.job_description}

MASTER RESUME (LATEX):
{data.master_latex}
"""

    try:
        ai_text = await call_anthropic(prompt, data.temperature, data.max_tokens)
        parsed = try_extract_json(ai_text)
        if not parsed:
            raise HTTPException(status_code=500, detail="Could not parse AI output")

        summary = parsed.get("summary", "")
        bullets = parsed.get("bullets", [])
        skills = parsed.get("skills", [])

        if not isinstance(summary, str):
            summary = ""

        if not isinstance(bullets, list):
            bullets = []
        clean_bullets = [item.strip() for item in bullets if isinstance(item, str) and len(item.strip()) > 10][:6]

        if not isinstance(skills, list):
            skills = []
        clean_skills = [item.strip() for item in skills if isinstance(item, str) and len(item.strip()) > 1][:12]

        output = build_output_text(summary, clean_bullets, clean_skills)
        latex = build_base_template_latex(summary, clean_bullets, clean_skills)

        return TailorResponse(output=output, latex=latex)

    except httpx.HTTPStatusError as e:
        error_detail = ""
        try:
            error_detail = e.response.text
        except Exception:
            error_detail = str(e)

        print(f"Anthropic API Error {e.response.status_code}: {error_detail}")

        if e.response.status_code == 401:
            raise HTTPException(status_code=500, detail="API authentication failed - check your API key")
        if e.response.status_code == 429:
            raise HTTPException(status_code=429, detail="AI service rate limit exceeded. Please try again later.")
        raise HTTPException(status_code=500, detail=f"AI service error {e.response.status_code}: {error_detail}")
    except Exception as e:
        print(f"Tailor endpoint unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

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
    max_tokens: int = 2500  # Increased for structured extraction


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


def build_output_text(data: dict) -> str:
    """Build readable output text from structured resume data"""
    lines = ["TAILORED RESUME", ""]
    
    # Contact info
    if data.get("name"):
        lines.append(f"Name: {data['name']}")
    if data.get("email"):
        lines.append(f"Email: {data['email']}")
    lines.append("")
    
    # Education
    education = data.get("education", [])
    if education:
        lines.append("EDUCATION")
        for edu in education:
            if edu.get("school"):
                lines.append(f"- {edu.get('degree', 'Degree')} from {edu['school']} ({edu.get('dates', 'Dates')})")
        lines.append("")
    
    # Experience
    experience = data.get("experience", [])
    if experience:
        lines.append("EXPERIENCE")
        for exp in experience:
            if exp.get("role"):
                lines.append(f"- {exp['role']} at {exp.get('company', 'Company')} ({exp.get('dates', 'Dates')})")
                for bullet in exp.get("bullets", [])[:3]:
                    lines.append(f"  • {bullet}")
        lines.append("")
    
    # Projects
    projects = data.get("projects", [])
    if projects:
        lines.append("PROJECTS")
        for proj in projects:
            if proj.get("name"):
                lines.append(f"- {proj['name']} ({proj.get('tech', 'Tech stack')})")
                for bullet in proj.get("bullets", [])[:2]:
                    lines.append(f"  • {bullet}")
        lines.append("")
    
    # Skills
    skills = data.get("skills", {})
    if skills:
        lines.append("TECHNICAL SKILLS")
        if skills.get("languages"):
            lines.append(f"Languages: {skills['languages']}")
        if skills.get("frameworks"):
            lines.append(f"Frameworks: {skills['frameworks']}")
        if skills.get("tools"):
            lines.append(f"Tools: {skills['tools']}")
        lines.append("")
    
    lines.extend([
        "Notes:",
        "- Content selected and tailored from your master resume for this role.",
        "- Irrelevant content excluded.",
    ])
    
    return "\n".join(lines)


def build_base_template_latex(data: dict) -> str:
    """Build the Jake Ryan resume template with tailored content"""
    
    # Extract contact info with defaults
    name = escape_latex_text(data.get("name", "Your Name"))
    phone = escape_latex_text(data.get("phone", "123-456-7890"))
    email = escape_latex_text(data.get("email", "email@example.com"))
    linkedin = escape_latex_text(data.get("linkedin", "linkedin.com/in/yourprofile"))
    github = escape_latex_text(data.get("github", "github.com/yourusername"))
    
    # Build education section
    education_entries = data.get("education", [])
    education_latex = []
    for edu in education_entries[:2]:  # Limit to 2 entries
        school = escape_latex_text(edu.get("school", ""))
        location = escape_latex_text(edu.get("location", ""))
        degree = escape_latex_text(edu.get("degree", ""))
        dates = escape_latex_text(edu.get("dates", ""))
        if school:
            education_latex.append(
                f"    \\resumeSubheading\n"
                f"      {{{school}}}{{{location}}}\n"
                f"      {{{degree}}}{{{dates}}}"
            )
    
    education_section = "\n".join(education_latex) if education_latex else \
        "    \\resumeSubheading\n" \
        "      {Your University}{City, State}\n" \
        "      {Degree Program}{Expected Graduation Date}"
    
    # Build experience section
    experience_entries = data.get("experience", [])
    experience_latex = []
    for exp in experience_entries[:3]:  # Limit to 3 entries
        role = escape_latex_text(exp.get("role", ""))
        dates = escape_latex_text(exp.get("dates", ""))
        company = escape_latex_text(exp.get("company", ""))
        location = escape_latex_text(exp.get("location", ""))
        bullets = exp.get("bullets", [])
        
        if role and company:
            exp_block = [
                f"    \\resumeSubheading\n"
                f"      {{{role}}}{{{dates}}}\n"
                f"      {{{company}}}{{{location}}}"
            ]
            if bullets:
                exp_block.append("      \\resumeItemListStart")
                for bullet in bullets[:5]:  # Limit to 5 bullets per role
                    exp_block.append(f"        \\resumeItem{{{escape_latex_text(bullet)}}}")
                exp_block.append("      \\resumeItemListEnd")
            experience_latex.append("\n".join(exp_block))
    
    experience_section = "\n\n".join(experience_latex) if experience_latex else \
        "    \\resumeSubheading\n" \
        "      {Your Role}{Dates}\n" \
        "      {Company Name}{Location}\n" \
        "      \\resumeItemListStart\n" \
        "        \\resumeItem{Add your experience bullets here}\n" \
        "      \\resumeItemListEnd"
    
    # Build projects section
    projects = data.get("projects", [])
    projects_latex = []
    for proj in projects[:2]:  # Limit to 2 projects
        name = escape_latex_text(proj.get("name", ""))
        tech = escape_latex_text(proj.get("tech", ""))
        dates = escape_latex_text(proj.get("dates", ""))
        bullets = proj.get("bullets", [])
        
        if name:
            proj_block = [
                f"      \\resumeProjectHeading\n"
                f"          {{\\textbf{{{name}}} $|$ \\emph{{{tech}}}}}{{{dates}}}"
            ]
            if bullets:
                proj_block.append("          \\resumeItemListStart")
                for bullet in bullets[:4]:  # Limit to 4 bullets per project
                    proj_block.append(f"            \\resumeItem{{{escape_latex_text(bullet)}}}")
                proj_block.append("          \\resumeItemListEnd")
            projects_latex.append("\n".join(proj_block))
    
    projects_section = "\n".join(projects_latex) if projects_latex else \
        "      \\resumeProjectHeading\n" \
        "          {\\textbf{Project Name} $|$ \\emph{Technologies}}{Date}\n" \
        "          \\resumeItemListStart\n" \
        "            \\resumeItem{Add your project description}\n" \
        "          \\resumeItemListEnd"
    
    # Build technical skills section
    skills_data = data.get("skills", {})
    languages = escape_latex_text(skills_data.get("languages", "Add languages"))
    frameworks = escape_latex_text(skills_data.get("frameworks", "Add frameworks"))
    tools = escape_latex_text(skills_data.get("tools", "Add developer tools"))
    libraries = escape_latex_text(skills_data.get("libraries", "Add libraries"))
    
    # Return full template
    return f"""\\documentclass[letterpaper,11pt]{{article}}

\\usepackage{{latexsym}}
\\usepackage[empty]{{fullpage}}
\\usepackage{{titlesec}}
\\usepackage{{marvosym}}
\\usepackage[usenames,dvipsnames]{{color}}
\\usepackage{{verbatim}}
\\usepackage{{enumitem}}
\\usepackage[hidelinks]{{hyperref}}
\\usepackage{{fancyhdr}}
\\usepackage[english]{{babel}}
\\usepackage{{tabularx}}
\\input{{glyphtounicode}}

\\pagestyle{{fancy}}
\\fancyhf{{}}
\\fancyfoot{{}}
\\renewcommand{{\\headrulewidth}}{{0pt}}
\\renewcommand{{\\footrulewidth}}{{0pt}}

\\addtolength{{\\oddsidemargin}}{{-0.5in}}
\\addtolength{{\\evensidemargin}}{{-0.5in}}
\\addtolength{{\\textwidth}}{{1in}}
\\addtolength{{\\topmargin}}{{-.5in}}
\\addtolength{{\\textheight}}{{1.0in}}

\\urlstyle{{same}}

\\raggedbottom
\\raggedright
\\setlength{{\\tabcolsep}}{{0in}}

\\titleformat{{\\section}}{{
  \\vspace{{-4pt}}\\scshape\\raggedright\\large
}}{{}}{{0em}}{{}}[\\color{{black}}\\titlerule \\vspace{{-5pt}}]

\\pdfgentounicode=1

\\newcommand{{\\resumeItem}}[1]{{
  \\item\\small{{
    {{#1 \\vspace{{-2pt}}}}
  }}
}}

\\newcommand{{\\resumeSubheading}}[4]{{
  \\vspace{{-2pt}}\\item
    \\begin{{tabular*}}{{0.97\\textwidth}}[t]{{l@{{\\extracolsep{{\\fill}}}}r}}
      \\textbf{{#1}} & #2 \\\\
      \\textit{{\\small#3}} & \\textit{{\\small #4}} \\\\
    \\end{{tabular*}}\\vspace{{-7pt}}
}}

\\newcommand{{\\resumeSubSubheading}}[2]{{
    \\item
    \\begin{{tabular*}}{{0.97\\textwidth}}{{l@{{\\extracolsep{{\\fill}}}}r}}
      \\textit{{\\small#1}} & \\textit{{\\small #2}} \\\\
    \\end{{tabular*}}\\vspace{{-7pt}}
}}

\\newcommand{{\\resumeProjectHeading}}[2]{{
    \\item
    \\begin{{tabular*}}{{0.97\\textwidth}}{{l@{{\\extracolsep{{\\fill}}}}r}}
      \\small#1 & #2 \\\\
    \\end{{tabular*}}\\vspace{{-7pt}}
}}

\\newcommand{{\\resumeSubItem}}[1]{{\\resumeItem{{#1}}\\vspace{{-4pt}}}}

\\renewcommand\\labelitemii{{$\\vcenter{{\\hbox{{\\tiny$\\bullet$}}}}$}}

\\newcommand{{\\resumeSubHeadingListStart}}{{\\begin{{itemize}}[leftmargin=0.15in, label={{}}]}}
\\newcommand{{\\resumeSubHeadingListEnd}}{{\\end{{itemize}}}}
\\newcommand{{\\resumeItemListStart}}{{\\begin{{itemize}}}}
\\newcommand{{\\resumeItemListEnd}}{{\\end{{itemize}}\\vspace{{-5pt}}}}

\\begin{{document}}

\\begin{{center}}
    \\textbf{{\\Huge \\scshape {name}}} \\\\ \\vspace{{1pt}}
    \\small {phone} $|$ \\href{{mailto:{email}}}{{\\underline{{{email}}}}} $|$ 
    \\href{{https://{linkedin}}}{{\\underline{{{linkedin}}}}} $|$
    \\href{{https://{github}}}{{\\underline{{{github}}}}}
\\end{{center}}

\\section{{Education}}
  \\resumeSubHeadingListStart
{education_section}
  \\resumeSubHeadingListEnd

\\section{{Experience}}
  \\resumeSubHeadingListStart
{experience_section}
  \\resumeSubHeadingListEnd

\\section{{Projects}}
    \\resumeSubHeadingListStart
{projects_section}
    \\resumeSubHeadingListEnd

\\section{{Technical Skills}}
 \\begin{{itemize}}[leftmargin=0.15in, label={{}}]
    \\small{{\\item{{
     \\textbf{{Languages}}{{: {languages}}} \\\\
     \\textbf{{Frameworks}}{{: {frameworks}}} \\\\
     \\textbf{{Developer Tools}}{{: {tools}}} \\\\
     \\textbf{{Libraries}}{{: {libraries}}}
    }}}}
 \\end{{itemize}}

\\end{{document}}
"""


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

    prompt = f"""You are an expert resume strategist who extracts and tailors resume content.

TASK:
1) Parse the candidate's master LaTeX resume to extract ALL structured information
2) Compare it against the job description
3) Select only the most relevant experience bullets, projects, and skills
4) Rewrite selected bullets for impact while keeping facts strictly unchanged

HARD RULES:
- Never add new facts, employers, degrees, dates, tools, metrics, or responsibilities
- Extract name, contact info, education, experience, projects exactly as written
- You may reorder and rephrase experience bullets for relevance
- Keep bullets concise and results-oriented
- Select 2-3 most relevant experience roles (3-5 bullets each)
- Select 1-2 most relevant projects (2-4 bullets each)
- Categorize skills into: languages, frameworks, tools, libraries

Return ONLY strict JSON matching this schema:
{{
  "name": "Full Name",
  "email": "email@example.com",
  "phone": "123-456-7890",
  "linkedin": "linkedin.com/in/username",
  "github": "github.com/username",
  "education": [
    {{
      "school": "University Name",
      "location": "City, ST",
      "degree": "Bachelor of Science in Computer Science",
      "dates": "Aug. 2020 -- May 2024"
    }}
  ],
  "experience": [
    {{
      "role": "Software Engineering Intern",
      "company": "Company Name",
      "location": "City, ST",
      "dates": "June 2023 -- Aug. 2023",
      "bullets": ["Achievement 1", "Achievement 2"]
    }}
  ],
  "projects": [
    {{
      "name": "Project Name",
      "tech": "Python, React, PostgreSQL",
      "dates": "Jan. 2023 -- Present",
      "bullets": ["Description 1", "Description 2"]
    }}
  ],
  "skills": {{
    "languages": "Python, Java, JavaScript, C++",
    "frameworks": "React, Flask, Node.js",
    "tools": "Git, Docker, VS Code",
    "libraries": "pandas, NumPy, scikit-learn"
  }}
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

        # Validate and clean the data structure
        resume_data = {
            "name": parsed.get("name", "Your Name"),
            "email": parsed.get("email", "email@example.com"),
            "phone": parsed.get("phone", "123-456-7890"),
            "linkedin": parsed.get("linkedin", "linkedin.com/in/yourprofile"),
            "github": parsed.get("github", "github.com/yourusername"),
            "education": [],
            "experience": [],
            "projects": [],
            "skills": {}
        }
        
        # Clean education
        if isinstance(parsed.get("education"), list):
            for edu in parsed["education"][:2]:
                if isinstance(edu, dict) and edu.get("school"):
                    resume_data["education"].append({
                        "school": str(edu.get("school", "")).strip(),
                        "location": str(edu.get("location", "")).strip(),
                        "degree": str(edu.get("degree", "")).strip(),
                        "dates": str(edu.get("dates", "")).strip()
                    })
        
        # Clean experience
        if isinstance(parsed.get("experience"), list):
            for exp in parsed["experience"][:3]:
                if isinstance(exp, dict) and exp.get("role"):
                    bullets = []
                    if isinstance(exp.get("bullets"), list):
                        bullets = [str(b).strip() for b in exp["bullets"] if isinstance(b, str) and len(str(b).strip()) > 10][:5]
                    
                    resume_data["experience"].append({
                        "role": str(exp.get("role", "")).strip(),
                        "company": str(exp.get("company", "")).strip(),
                        "location": str(exp.get("location", "")).strip(),
                        "dates": str(exp.get("dates", "")).strip(),
                        "bullets": bullets
                    })
        
        # Clean projects
        if isinstance(parsed.get("projects"), list):
            for proj in parsed["projects"][:2]:
                if isinstance(proj, dict) and proj.get("name"):
                    bullets = []
                    if isinstance(proj.get("bullets"), list):
                        bullets = [str(b).strip() for b in proj["bullets"] if isinstance(b, str) and len(str(b).strip()) > 10][:4]
                    
                    resume_data["projects"].append({
                        "name": str(proj.get("name", "")).strip(),
                        "tech": str(proj.get("tech", "")).strip(),
                        "dates": str(proj.get("dates", "")).strip(),
                        "bullets": bullets
                    })
        
        # Clean skills
        if isinstance(parsed.get("skills"), dict):
            skills = parsed["skills"]
            resume_data["skills"] = {
                "languages": str(skills.get("languages", "")).strip() or "Add languages",
                "frameworks": str(skills.get("frameworks", "")).strip() or "Add frameworks",
                "tools": str(skills.get("tools", "")).strip() or "Add tools",
                "libraries": str(skills.get("libraries", "")).strip() or "Add libraries"
            }

        output = build_output_text(resume_data)
        latex = build_base_template_latex(resume_data)

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

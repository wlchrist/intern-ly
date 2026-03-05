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
    
    # Extract contact info
    name = escape_latex_text(data.get("name", "Your Name"))
    phone = escape_latex_text(data.get("phone", ""))
    email = escape_latex_text(data.get("email", ""))
    linkedin = escape_latex_text(data.get("linkedin", ""))
    github = escape_latex_text(data.get("github", ""))
    
    # Build contact line - only include non-empty fields
    contact_parts = [phone, f"\\href{{mailto:{email}}}{{\\underline{{{email}}}}}" if email else None, 
                    f"\\href{{https://{linkedin}}}{{\\underline{{{linkedin}}}}}" if linkedin else None,
                    f"\\href{{https://{github}}}{{\\underline{{{github}}}}}" if github else None]
    contact_line = " $|$ ".join([p for p in contact_parts if p]) or "Add contact info"
    
    # Build education section
    education_entries = data.get("education", [])
    education_latex = []
    for edu in education_entries[:2]:
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
    
    education_section = "\n".join(education_latex) if education_latex else ""
    
    # Build experience section
    experience_entries = data.get("experience", [])
    experience_latex = []
    for exp in experience_entries[:3]:
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
                for bullet in bullets[:5]:
                    exp_block.append(f"        \\resumeItem{{{escape_latex_text(bullet)}}}")
                exp_block.append("      \\resumeItemListEnd")
            experience_latex.append("\n".join(exp_block))
    
    experience_section = "\n\n".join(experience_latex) if experience_latex else ""
    
    # Build projects section
    projects = data.get("projects", [])
    projects_latex = []
    for proj in projects[:2]:
        proj_name = escape_latex_text(proj.get("name", ""))
        tech = escape_latex_text(proj.get("tech", ""))
        proj_dates = escape_latex_text(proj.get("dates", ""))
        bullets = proj.get("bullets", [])
        
        if proj_name:
            proj_block = [
                f"      \\resumeProjectHeading\n"
                f"          {{\\textbf{{{proj_name}}} $|$ \\emph{{{tech}}}}}{{{proj_dates}}}"
            ]
            if bullets:
                proj_block.append("          \\resumeItemListStart")
                for bullet in bullets[:4]:
                    proj_block.append(f"            \\resumeItem{{{escape_latex_text(bullet)}}}")
                proj_block.append("          \\resumeItemListEnd")
            projects_latex.append("\n".join(proj_block))
    
    projects_section = "\n".join(projects_latex) if projects_latex else ""
    
    # Build technical skills section
    skills_data = data.get("skills", {})
    skills_lines = []
    
    if skills_data.get("languages"):
        skills_lines.append(f"     \\textbf{{Languages}}{{: {escape_latex_text(skills_data['languages'])}}} \\\\")
    if skills_data.get("frameworks"):
        skills_lines.append(f"     \\textbf{{Frameworks}}{{: {escape_latex_text(skills_data['frameworks'])}}} \\\\")
    if skills_data.get("tools"):
        skills_lines.append(f"     \\textbf{{Developer Tools}}{{: {escape_latex_text(skills_data['tools'])}}} \\\\")
    if skills_data.get("libraries"):
        skills_lines.append(f"     \\textbf{{Libraries}}{{: {escape_latex_text(skills_data['libraries'])}}}")
    
    skills_section = "\n".join(skills_lines)
    
    # Build the final template
    result = f"""\\documentclass[letterpaper,11pt]{{article}}

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
    \\small {contact_line}
\\end{{center}}
"""
    
    if education_section:
        result += f"""
\\section{{Education}}
  \\resumeSubHeadingListStart
{education_section}
  \\resumeSubHeadingListEnd
"""
    
    if experience_section:
        result += f"""
\\section{{Experience}}
  \\resumeSubHeadingListStart
{experience_section}
  \\resumeSubHeadingListEnd
"""
    
    if projects_section:
        result += f"""
\\section{{Projects}}
    \\resumeSubHeadingListStart
{projects_section}
    \\resumeSubHeadingListEnd
"""
    
    if skills_section:
        result += f"""
\\section{{Technical Skills}}
 \\begin{{itemize}}[leftmargin=0.15in, label={{}}]
    \\small{{\\item{{
{skills_section}
    }}}}
 \\end{{itemize}}
"""
    
    result += """
\\end{document}
"""
    return result


def parse_extracted_resume(text: str) -> dict:
    """Parse resume data from simple key-value format"""
    lines = text.strip().split('\n')
    data = {
        "name": "",
        "email": "",
        "phone": "",
        "linkedin": "",
        "github": "",
        "education": [],
        "experience": [],
        "projects": [],
        "skills": {"languages": "", "frameworks": "", "tools": "", "libraries": ""}
    }
    
    current_section = None
    current_entry = None
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Parse key-value pairs
        if line.startswith("NAME:"):
            data["name"] = line.replace("NAME:", "").strip()
        elif line.startswith("EMAIL:"):
            data["email"] = line.replace("EMAIL:", "").strip()
        elif line.startswith("PHONE:"):
            data["phone"] = line.replace("PHONE:", "").strip()
        elif line.startswith("LINKEDIN:"):
            data["linkedin"] = line.replace("LINKEDIN:", "").strip()
        elif line.startswith("GITHUB:"):
            data["github"] = line.replace("GITHUB:", "").strip()
        elif line.startswith("LANGUAGES:"):
            data["skills"]["languages"] = line.replace("LANGUAGES:", "").strip()
        elif line.startswith("FRAMEWORKS:"):
            data["skills"]["frameworks"] = line.replace("FRAMEWORKS:", "").strip()
        elif line.startswith("TOOLS:"):
            data["skills"]["tools"] = line.replace("TOOLS:", "").strip()
        elif line.startswith("LIBRARIES:"):
            data["skills"]["libraries"] = line.replace("LIBRARIES:", "").strip()
        elif line.startswith("EDUCATION:"):
            current_entry = {"school": "", "location": "", "degree": "", "dates": ""}
            current_section = "education"
        elif line.startswith("EXPERIENCE:"):
            current_entry = {"role": "", "company": "", "location": "", "dates": "", "bullets": []}
            current_section = "experience"
        elif line.startswith("PROJECT:"):
            current_entry = {"name": "", "tech": "", "dates": "", "bullets": []}
            current_section = "projects"
        elif current_section == "education":
            if line.startswith("School:"):
                current_entry["school"] = line.replace("School:", "").strip()
            elif line.startswith("Location:"):
                current_entry["location"] = line.replace("Location:", "").strip()
            elif line.startswith("Degree:"):
                current_entry["degree"] = line.replace("Degree:", "").strip()
            elif line.startswith("Dates:"):
                current_entry["dates"] = line.replace("Dates:", "").strip()
                data["education"].append(current_entry)
                current_entry = None
        elif current_section == "experience":
            if line.startswith("Role:"):
                current_entry["role"] = line.replace("Role:", "").strip()
            elif line.startswith("Company:"):
                current_entry["company"] = line.replace("Company:", "").strip()
            elif line.startswith("Location:"):
                current_entry["location"] = line.replace("Location:", "").strip()
            elif line.startswith("Dates:"):
                current_entry["dates"] = line.replace("Dates:", "").strip()
            elif line.startswith("- "):
                current_entry["bullets"].append(line[2:])
            elif line.startswith("EDUCATION:") or line.startswith("PROJECT:"):
                if current_entry and current_entry.get("role"):
                    data["experience"].append(current_entry)
                current_entry = None
                current_section = None
        elif current_section == "projects":
            if line.startswith("Name:"):
                current_entry["name"] = line.replace("Name:", "").strip()
            elif line.startswith("Tech:"):
                current_entry["tech"] = line.replace("Tech:", "").strip()
            elif line.startswith("Dates:"):
                current_entry["dates"] = line.replace("Dates:", "").strip()
            elif line.startswith("- "):
                current_entry["bullets"].append(line[2:])
            elif line.startswith("EDUCATION:") or line.startswith("EXPERIENCE:"):
                if current_entry and current_entry.get("name"):
                    data["projects"].append(current_entry)
                current_entry = None
                current_section = None
    
    # Append last entry if exists
    if current_entry:
        if current_section == "education" and current_entry.get("school"):
            data["education"].append(current_entry)
        elif current_section == "experience" and current_entry.get("role"):
            data["experience"].append(current_entry)
        elif current_section == "projects" and current_entry.get("name"):
            data["projects"].append(current_entry)
    
    return data


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

    prompt = f"""Extract resume data from the LaTeX. Return ONLY the extracted data in this format (no JSON, no markdown, no explanation):

NAME: Full Name Here
EMAIL: email@example.com
PHONE: 123-456-7890
LINKEDIN: linkedin.com/in/username
GITHUB: github.com/username

EDUCATION:
School: University Name
Location: City, State
Degree: Degree Name
Dates: Date Range

EXPERIENCE:
Role: Job Title
Company: Company Name
Location: City, State
Dates: Date Range
- Bullet point text here
- Another bullet point

PROJECT:
Name: Project Name
Tech: Technology Stack
Dates: Dates
- Description or achievement
- Another description

LANGUAGES: Language1, Language2, Language3
FRAMEWORKS: Framework1, Framework2
TOOLS: Tool1, Tool2
LIBRARIES: Library1, Library2

RESUME:
{data.master_latex}

JOB DESCRIPTION:
{data.job_description}

Extract ALL details from the resume exactly as written. Use empty lines to separate sections. For missing fields, skip that line entirely."""

    try:
        ai_text = await call_anthropic(prompt, data.temperature, data.max_tokens)
        
        parsed = parse_extracted_resume(ai_text)
        
        if not parsed.get("name"):
            print(f"⚠️  No name extracted. AI Response:\n{ai_text[:500]}\n")
            # Fallback: try to extract at least the name from the LaTeX
            import re
            name_match = re.search(r'\\scshape\s+([^\\]+)', data.master_latex)
            fallback_name = name_match.group(1).strip() if name_match else "Your Name"
            parsed["name"] = fallback_name

        # Validate and clean the data structure
        resume_data = {
            "name": str(parsed.get("name", "")).strip() or "Your Name",
            "email": str(parsed.get("email", "")).strip() or "",
            "phone": str(parsed.get("phone", "")).strip() or "",
            "linkedin": str(parsed.get("linkedin", "")).strip() or "",
            "github": str(parsed.get("github", "")).strip() or "",
            "education": [],
            "experience": [],
            "projects": [],
            "skills": {}
        }
        
        # Clean education - keep empty if not provided
        if isinstance(parsed.get("education"), list) and len(parsed["education"]) > 0:
            for edu in parsed["education"][:2]:
                if isinstance(edu, dict) and edu.get("school"):
                    resume_data["education"].append({
                        "school": str(edu.get("school", "")).strip(),
                        "location": str(edu.get("location", "")).strip(),
                        "degree": str(edu.get("degree", "")).strip(),
                        "dates": str(edu.get("dates", "")).strip()
                    })
        
        # Clean experience
        if isinstance(parsed.get("experience"), list) and len(parsed["experience"]) > 0:
            for exp in parsed["experience"][:3]:
                if isinstance(exp, dict) and exp.get("role") and exp.get("company"):
                    bullets = []
                    if isinstance(exp.get("bullets"), list):
                        # Accept bullets even if short, since they're from the source
                        bullets = [str(b).strip() for b in exp["bullets"] if isinstance(b, str) and len(str(b).strip()) > 5][:5]
                    
                    if bullets or exp.get("role"):  # Include even if no bullets
                        resume_data["experience"].append({
                            "role": str(exp.get("role", "")).strip(),
                            "company": str(exp.get("company", "")).strip(),
                            "location": str(exp.get("location", "")).strip(),
                            "dates": str(exp.get("dates", "")).strip(),
                            "bullets": bullets
                        })
        
        # Clean projects
        if isinstance(parsed.get("projects"), list) and len(parsed["projects"]) > 0:
            for proj in parsed["projects"][:2]:
                if isinstance(proj, dict) and proj.get("name"):
                    bullets = []
                    if isinstance(proj.get("bullets"), list):
                        bullets = [str(b).strip() for b in proj["bullets"] if isinstance(b, str) and len(str(b).strip()) > 5][:4]
                    
                    resume_data["projects"].append({
                        "name": str(proj.get("name", "")).strip(),
                        "tech": str(proj.get("tech", "")).strip(),
                        "dates": str(proj.get("dates", "")).strip(),
                        "bullets": bullets
                    })
        
        # Clean skills - only include if actually present
        if isinstance(parsed.get("skills"), dict):
            skills = parsed["skills"]
            resume_data["skills"] = {
                "languages": str(skills.get("languages", "")).strip(),
                "frameworks": str(skills.get("frameworks", "")).strip(),
                "tools": str(skills.get("tools", "")).strip(),
                "libraries": str(skills.get("libraries", "")).strip()
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

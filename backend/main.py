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
import re
from dotenv import load_dotenv
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import Paragraph, Frame
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.units import inch

load_dotenv()

# Initialize rate limiter (IP-based)
# Note: LaTeX compilation requires texlive package installed via shell.nix
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
    master_resume: str | None = None
    master_latex: str | None = None
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
            
        # Check for section headers first
        if line.startswith("EDUCATION:"):
            # Save previous entry if exists
            if current_entry and current_section == "experience":
                if current_entry.get("role"):
                    data["experience"].append(current_entry)
            elif current_entry and current_section == "projects":
                if current_entry.get("name"):
                    data["projects"].append(current_entry)
            
            current_section = "education"
            current_entry = {"school": "", "location": "", "degree": "", "dates": ""}
        elif line.startswith("EXPERIENCE:"):
            # Save previous entry if exists
            if current_entry and current_section == "education":
                if current_entry.get("school"):
                    data["education"].append(current_entry)
            elif current_entry and current_section == "projects":
                if current_entry.get("name"):
                    data["projects"].append(current_entry)
                    
            current_section = "experience"
            current_entry = {"role": "", "company": "", "location": "", "dates": "", "bullets": []}
        elif line.startswith("PROJECT:"):
            # Save previous entry if exists
            if current_entry and current_section == "experience":
                if current_entry.get("role"):
                    data["experience"].append(current_entry)
            elif current_entry and current_section == "education":
                if current_entry.get("school"):
                    data["education"].append(current_entry)
                    
            current_section = "projects"
            current_entry = {"name": "", "tech": "", "dates": "", "bullets": []}
        elif line.startswith("LANGUAGES:"):
            # Save previous entry if exists
            if current_entry and current_section == "experience":
                if current_entry.get("role"):
                    data["experience"].append(current_entry)
            elif current_entry and current_section == "projects":
                if current_entry.get("name"):
                    data["projects"].append(current_entry)
            
            current_section = None
            current_entry = None
            data["skills"]["languages"] = line.replace("LANGUAGES:", "").strip()
        elif line.startswith("FRAMEWORKS:"):
            data["skills"]["frameworks"] = line.replace("FRAMEWORKS:", "").strip()
        elif line.startswith("TOOLS:"):
            data["skills"]["tools"] = line.replace("TOOLS:", "").strip()
        elif line.startswith("LIBRARIES:"):
            data["skills"]["libraries"] = line.replace("LIBRARIES:", "").strip()
        
        # Parse by section
        elif line.startswith("NAME:"):
            data["name"] = line.replace("NAME:", "").strip()
        elif line.startswith("EMAIL:"):
            data["email"] = line.replace("EMAIL:", "").strip()
        elif line.startswith("PHONE:"):
            data["phone"] = line.replace("PHONE:", "").strip()
        elif line.startswith("LINKEDIN:"):
            data["linkedin"] = line.replace("LINKEDIN:", "").strip()
        elif line.startswith("GITHUB:"):
            data["github"] = line.replace("GITHUB:", "").strip()
        elif current_section == "education" and current_entry:
            if line.startswith("School:"):
                current_entry["school"] = line.replace("School:", "").strip()
            elif line.startswith("Location:"):
                current_entry["location"] = line.replace("Location:", "").strip()
            elif line.startswith("Degree:"):
                current_entry["degree"] = line.replace("Degree:", "").strip()
            elif line.startswith("Dates:"):
                current_entry["dates"] = line.replace("Dates:", "").strip()
                data["education"].append(current_entry)
                current_entry = {"school": "", "location": "", "degree": "", "dates": ""}
        elif current_section == "experience" and current_entry:
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
            elif line.startswith("--") or (line and not line.startswith("-") and any(x in line for x in [":", "EDUCATION", "PROJECT", "LANGUAGES"])):
                # This might be a new entry or role line
                if ":" in line and current_entry.get("role"):
                    # Save current and start new
                    if current_entry["role"]:
                        data["experience"].append(current_entry)
                    current_entry = {"role": "", "company": "", "location": "", "dates": "", "bullets": []}
        elif current_section == "projects" and current_entry:
            if line.startswith("Name:"):
                current_entry["name"] = line.replace("Name:", "").strip()
            elif line.startswith("Tech:"):
                current_entry["tech"] = line.replace("Tech:", "").strip()
            elif line.startswith("Dates:"):
                current_entry["dates"] = line.replace("Dates:", "").strip()
                data["projects"].append(current_entry)
                current_entry = {"name": "", "tech": "", "dates": "", "bullets": []}
            elif line.startswith("- "):
                current_entry["bullets"].append(line[2:])
    
    # Append last entry if exists
    if current_entry:
        if current_section == "education" and current_entry.get("school"):
            data["education"].append(current_entry)
        elif current_section == "experience" and current_entry.get("role"):
            data["experience"].append(current_entry)
        elif current_section == "projects" and current_entry.get("name"):
            data["projects"].append(current_entry)
    
    return data


def extract_fallback_name(content: str) -> str:
    latex_name_match = re.search(r'\\scshape\s+([^\\}]+)', content)
    if latex_name_match:
        name = latex_name_match.group(1).strip()
        # Clean up any trailing braces or LaTeX formatting
        name = name.rstrip('}')
        return name

    lines = [line.strip() for line in content.splitlines() if line.strip()]
    for line in lines[:12]:
        # Skip lines with braces or section markers
        if len(line) > 2 and len(line.split()) <= 4 and "@" not in line and "section" not in line.lower() and "{" not in line and "}" not in line:
            return line

    return "Your Name"


def parse_markdown_sections(markdown_text: str) -> dict:
    """Parse structured markdown into sections with headers and bullets"""
    sections: dict[str, list[dict]] = {
        "education": [],
        "experience": [],
        "projects": [],
        "technical_skills": [],
    }

    current_section: str | None = None
    current_entry: dict | None = None

    def clean_markdown(text: str) -> str:
        """Remove markdown formatting characters but preserve content"""
        # Remove **bold** → bold
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        # Remove *italic* → italic
        text = re.sub(r"\*(.+?)\*", r"\1", text)
        # Clean trailing markdown
        text = text.replace("**", "").replace("*", "")
        return text.strip()

    def is_header_line(line: str) -> bool:
        """Check if line is an entry header (bold text or starts with **)"""
        return line.startswith("**") or "**" in line

    for raw_line in markdown_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # Check for section headers
        if line.startswith("##"):
            # Save previous entry if exists
            if current_entry and current_section:
                sections[current_section].append(current_entry)
                current_entry = None
            
            header = line.lstrip("#").strip().lower()
            if header == "education":
                current_section = "education"
            elif header == "experience":
                current_section = "experience"
            elif header == "projects":
                current_section = "projects"
            elif header in ("technical skills", "skills"):
                current_section = "technical_skills"
            continue

        if current_section is None:
            continue

        # Entry header (job title, project name, etc.)
        if is_header_line(line):
            # Save previous entry if exists
            if current_entry:
                sections[current_section].append(current_entry)
            
            cleaned = clean_markdown(line)
            current_entry = {
                "header": cleaned,
                "bullets": []
            }
        
        # Bullet point
        elif line.startswith("- "):
            bullet_text = line[2:].strip()  # Remove "- " prefix
            cleaned = clean_markdown(bullet_text)
            
            if current_entry:
                # Add to current entry's bullets
                current_entry["bullets"].append(cleaned)
            else:
                # Create implicit entry for bullets without headers
                current_entry = {
                    "header": "",
                    "bullets": [cleaned]
                }

    # Save final entry
    if current_entry and current_section:
        sections[current_section].append(current_entry)

    return sections


def extract_contact_info(resume_content: str) -> dict:
    # Try to extract from LaTeX \href{URL}{display_text} first
    linkedin_href = re.search(r"\\href\{(https?://(?:www\.)?linkedin\.com/in/[^}]+)\}", resume_content)
    github_href = re.search(r"\\href\{(https?://(?:www\.)?github\.com/[^}]+)\}", resume_content)
    
    # Fallback to plain URL search if no \href found
    email_match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", resume_content)
    phone_match = re.search(r"(?:\+?\d[\d\-\s().]{7,}\d)", resume_content)
    
    # Use href URLs if found, otherwise search for plain URLs
    if linkedin_href:
        linkedin_url = linkedin_href.group(1)
    else:
        linkedin_match = re.search(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[A-Za-z0-9_\-]+", resume_content)
        linkedin_url = linkedin_match.group(0) if linkedin_match else ""
    
    if github_href:
        github_url = github_href.group(1)
    else:
        github_match = re.search(r"(?:https?://)?(?:www\.)?github\.com/[A-Za-z0-9_\-]+", resume_content)
        github_url = github_match.group(0) if github_match else ""

    return {
        "name": extract_fallback_name(resume_content),
        "email": email_match.group(0) if email_match else "",
        "phone": phone_match.group(0) if phone_match else "",
        "linkedin": linkedin_url,
        "github": github_url,
    }


def build_pdf_bytes(contact: dict, sections: dict) -> bytes:
    """Build professional PDF matching Jake's resume template style using reportlab"""
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    # Margins matching Jake's template
    left_margin = 0.5 * inch
    right_margin = width - 0.5 * inch
    top_margin = height - 0.5 * inch
    
    y = top_margin
    
    def ensure_space(needed: float = 20):
        nonlocal y
        if y - needed < 0.75 * inch:
            pdf.showPage()
            y = top_margin
    
    def draw_section_header(title: str):
        nonlocal y
        ensure_space(28)
        # Section title in uppercase, large, bold
        pdf.setFont("Times-Bold", 12)
        pdf.drawString(left_margin, y, title.upper())
        y -= 3
        # Horizontal line under section
        pdf.setStrokeColorRGB(0, 0, 0)
        pdf.setLineWidth(0.5)
        pdf.line(left_margin, y, right_margin, y)
        y -= 14
    
    def wrap_text(text: str, font_name: str, font_size: int, max_width: float) -> list:
        """Wrap text to fit within max_width"""
        words = text.split()
        lines = []
        current_line = []
        
        for word in words:
            test_line = " ".join(current_line + [word])
            if pdf.stringWidth(test_line, font_name, font_size) <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(" ".join(current_line))
                current_line = [word]
        
        if current_line:
            lines.append(" ".join(current_line))
        
        return lines if lines else [""]
    
    def draw_entry_header(text: str):
        """Draw job title, project name, or education header (bold)"""
        nonlocal y
        ensure_space(16)
        
        # Bold, slightly larger than bullets
        pdf.setFont("Times-Bold", 11)
        header_width = right_margin - left_margin
        wrapped_lines = wrap_text(text, "Times-Bold", 11, header_width)
        
        for line in wrapped_lines:
            pdf.drawString(left_margin, y, line)
            y -= 14
    
    def draw_bullet_item(text: str):
        nonlocal y
        # Bullet with proper indentation
        bullet_x = left_margin + 10
        text_x = left_margin + 20
        text_width = right_margin - text_x
        
        # Wrap the text
        pdf.setFont("Times-Roman", 11)
        wrapped_lines = wrap_text(text, "Times-Roman", 11, text_width)
        
        for i, line in enumerate(wrapped_lines):
            ensure_space(14)
            if i == 0:
                # Draw bullet for first line
                pdf.setFont("Times-Roman", 11)
                pdf.drawString(bullet_x, y, "•")
            pdf.drawString(text_x, y, line)
            y -= 13
    
    # Header: Name (centered, large, bold, small caps effect)
    pdf.setTitle("Tailored Resume")
    name = (contact.get("name") or "Your Name").strip("{}")
    pdf.setFont("Times-Bold", 24)
    name_width = pdf.stringWidth(name, "Times-Bold", 24)
    pdf.drawString((width - name_width) / 2, y, name)
    y -= 20
    
    # Contact info - ALL on one line (Jake's template style)
    contact_parts = []
    
    if contact.get("email"):
        contact_parts.append(contact["email"])
    
    if contact.get("linkedin"):
        # Clean URL: https://linkedin.com/in/... → linkedin.com/in/...
        linkedin_clean = contact["linkedin"].replace("https://", "").replace("http://", "").replace("www.", "")
        contact_parts.append(linkedin_clean)
    
    if contact.get("github"):
        # Clean URL: https://github.com/... → github.com/...
        github_clean = contact["github"].replace("https://", "").replace("http://", "").replace("www.", "")
        contact_parts.append(github_clean)
    
    if contact.get("phone"):
        contact_parts.append(contact["phone"])
    
    if contact_parts:
        contact_line = " | ".join(contact_parts)
        pdf.setFont("Times-Roman", 10)
        contact_width = pdf.stringWidth(contact_line, "Times-Roman", 10)
        pdf.drawString((width - contact_width) / 2, y, contact_line)
        y -= 16
    
    y -= 6  # Extra space after header
    
    # Section order matching Jake's template
    section_order = [
        ("Education", "education"),
        ("Experience", "experience"),
        ("Technical Projects", "projects"),
        ("Technical Skills", "technical_skills")
    ]
    
    for section_title, section_key in section_order:
        entries = sections.get(section_key, [])
        if not entries:
            continue
        
        draw_section_header(section_title)
        
        for entry in entries:
            # Draw entry header (job title, project name, etc.)
            if entry.get("header"):
                draw_entry_header(entry["header"])
            
            # Draw bullets for this entry
            for bullet in entry.get("bullets", []):
                draw_bullet_item(bullet.strip())
            
            y -= 3  # Small space between entries
        
        y -= 5  # Extra space between sections
    
    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()


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


@app.post("/api/tailor")
@limiter.limit("10/minute")
async def tailor_resume(request: Request, data: TailorRequest):
    resume_content = (data.master_resume or data.master_latex or "").strip()

    if not resume_content:
        raise HTTPException(status_code=400, detail="Master resume content is required")
    if not data.job_description.strip():
        raise HTTPException(status_code=400, detail="Job description is required")

    prompt = f"""You are an expert resume editor.

TASK:
1) Parse the resume content below (any format: LaTeX/plain text/markdown).
2) Rewrite cleartext and bullets to be highly relevant to the job description.
3) Keep facts strictly true to source (no fabricated employers, dates, tools, or metrics).
4) Return ONLY markdown with these exact Jake template section headers:

## Education
**Degree, School, Location** (Dates)
- Optional bullet for relevant coursework or honors

## Experience
**Job Title** | Dates
**Company Name** | Location
- Bullet point for accomplishment 1
- Bullet point for accomplishment 2
- Bullet point for accomplishment 3

## Projects
**Project Name (Tech Stack)** | Dates
- Bullet point describing implementation
- Bullet point describing outcome

## Technical Skills
- Languages: list languages
- Frameworks: list frameworks
- Developer Tools: list tools
- Libraries: list libraries

RULES:
- Output markdown only; no JSON, no preface, no explanation.
- Use **bold** for job titles, company names, project names, and degree info
- Put dates on the same line with job/project titles using | separator
- Sub-bullets start with "- " (dash + space)
- Preserve all names, dates, and technologies from source exactly
- Prioritize entries relevant to the job description

JOB DESCRIPTION:
{data.job_description}

RESUME CONTENT:
{resume_content}
"""

    try:
        ai_text = await call_anthropic(prompt, data.temperature, data.max_tokens)
        
        sections = parse_markdown_sections(ai_text)
        contact = extract_contact_info(resume_content)
        pdf_bytes = build_pdf_bytes(contact, sections)

        return StreamingResponse(
            BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=tailored_resume.pdf"},
        )

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

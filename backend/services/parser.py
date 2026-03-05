"""Parser service: Extract resume content into structured JSON"""
import json
from schemas import ResumeJSON


async def parse_resume(resume_content: str, call_anthropic) -> ResumeJSON:
    """
    Parse resume content (any format) into structured JSON.
    Uses Claude to intelligently extract all resume fields.
    """
    
    prompt = f"""You are a resume parser. Extract the following resume into a structured JSON object.

Return ONLY valid JSON in this exact format:
{{
  "metadata": {{
    "name": "Full Name",
    "email": "email@example.com",
    "phone": "Phone number or empty string",
    "linkedin": "Full LinkedIn URL or empty string",
    "github": "Full GitHub URL or empty string"
  }},
  "sections": {{
    "education": [
      {{
        "title": "Degree",
        "institution": "University Name",
        "location": "City, State",
        "dates": "Graduation date",
        "highlights": ["Achievement or relevant coursework"]
      }}
    ],
    "experience": [
      {{
        "title": "Job Title",
        "company": "Company Name",
        "location": "City, State",
        "dates": "Start - End date",
        "highlights": ["Key accomplishment 1", "Key accomplishment 2"]
      }}
    ],
    "projects": [
      {{
        "title": "Project Name",
        "tech_stack": "Technologies used",
        "dates": "Project dates",
        "highlights": ["What you built", "Impact or outcome"]
      }}
    ],
    "skills": {{
      "Languages": ["Python", "JavaScript"],
      "Frameworks": ["FastAPI", "React"],
      "Developer Tools": ["Git", "Docker"],
      "Libraries": ["NumPy"]
    }}
  }}
}}

RULES:
- Extract all information accurately from the resume
- For dates, preserve the exact format from the source (e.g., "Nov 2023 - Present")
- For contact info, use full URLs for LinkedIn and GitHub (not shortened versions)
- If any information is not found, use empty string. This will be inserted into a resume, so we do not want bad data or hallucinated info.
- Keep highlights concise (1-2 sentences each)
- Do NOT fabricate or infer information not in the resume
- Return ONLY the JSON, no other text

RESUME TO PARSE:
{resume_content}
"""

    try:
        json_text = await call_anthropic(prompt, temperature=0.1, max_tokens=3000)
        
        # Parse and validate the JSON response
        resume_dict = json.loads(json_text)
        resume = ResumeJSON.model_validate(resume_dict)
        
        return resume
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse Claude's JSON response: {e}")
    except Exception as e:
        raise ValueError(f"Parser service error: {e}")

"""Parser service: Extract resume content into structured JSON"""
import json
import logging
from schemas import ResumeJSON

logger = logging.getLogger(__name__)


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
    "skills": {
      "languages": ["Python", "JavaScript"],
      "frameworks": ["FastAPI", "React"],
      "developer_tools": ["Git", "Docker"],
      "libraries": ["NumPy"]
    }
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
        
        # Log what Claude returned for debugging
        logger.info(f"Claude returned {len(json_text)} characters")
        logger.debug(f"Claude response: {json_text[:500]}...")  # First 500 chars
        
        if not json_text or not json_text.strip():
            raise ValueError("Claude returned empty response")
        
        # Try to extract JSON if Claude wrapped it in markdown
        json_text = json_text.strip()
        if json_text.startswith("```json"):
            json_text = json_text.split("```json")[1].split("```")[0].strip()
        elif json_text.startswith("```"):
            json_text = json_text.split("```")[1].split("```")[0].strip()
        
        # Parse and validate the JSON response
        resume_dict = json.loads(json_text)
        resume = ResumeJSON.model_validate(resume_dict)
        
        return resume
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error. Response was: {json_text[:1000]}")
        raise ValueError(f"Failed to parse Claude's JSON response: {e}")
    except Exception as e:
        logger.error(f"Parser error: {e}")
        raise ValueError(f"Parser service error: {e}")

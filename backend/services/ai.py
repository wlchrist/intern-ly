"""AI service: Rewrite resume bullets to match job description"""
import json
from schemas import ResumeJSON, JobDescription


async def rewrite_resume(resume: ResumeJSON, job_desc: JobDescription, call_anthropic) -> ResumeJSON:
    """
    Rewrite resume bullets to emphasize relevance to the job description.
    Returns the same JSON structure with rewritten highlights.
    """
    
    job_keywords = ", ".join(job_desc.keywords)
    job_technologies = ", ".join(job_desc.technologies)
    job_responsibilities = "\n".join(f"- {r}" for r in job_desc.responsibilities)
    job_nice_to_haves = ", ".join(job_desc.nice_to_haves)
    
    prompt = f"""You are an expert resume writer. Rewrite the given resume to better match the job description.

IMPORTANT RULES:
1. Do NOT fabricate or hallucinate facts, companies, technologies, or dates
2. Rewrite ONLY the highlight bullets to emphasize relevance
3. Keep all metadata (name, contact info, dates, company names) EXACTLY as provided
4. If a resume section has no highlights, return an empty array
5. Maximize relevance to the job description while staying factually accurate

JOB DESCRIPTION DETAILS:
Keys keywords: {job_keywords}
Technologies: {job_technologies}

Responsibilities:
{job_responsibilities}

Nice-to-haves (optional):
{job_nice_to_haves}

ORIGINAL RESUME (JSON):
{json.dumps(resume.model_dump(), indent=2)}

Return ONLY valid JSON in the exact same format as the input, with rewritten highlights.
Do not change structure, metadata, or any other fields—only rewrite highlight bullets for relevance.
"""

    try:
        json_text = await call_anthropic(prompt, temperature=0.2, max_tokens=3000)
        
        # Parse and validate the JSON response
        rewritten_dict = json.loads(json_text)
        rewritten_resume = ResumeJSON.model_validate(rewritten_dict)
        
        return rewritten_resume
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse Claude's JSON response: {e}")
    except Exception as e:
        raise ValueError(f"AI rewrite service error: {e}")

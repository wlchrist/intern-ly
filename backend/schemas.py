"""Pydantic schemas for resume parsing and generation"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict


class ContactInfo(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""
    linkedin: str = ""
    github: str = ""


class EducationEntry(BaseModel):
    title: str = ""
    institution: str = ""
    location: str = ""
    dates: str = ""
    highlights: List[str] = Field(default_factory=list)


class ExperienceEntry(BaseModel):
    title: str = ""
    company: str = ""
    location: str = ""
    dates: str = ""
    highlights: List[str] = Field(default_factory=list)


class ProjectEntry(BaseModel):
    title: str = ""
    tech_stack: str = ""
    dates: str = ""
    highlights: List[str] = Field(default_factory=list)


class SkillsSection(BaseModel):
    languages: List[str] = Field(default_factory=list, alias="Languages")
    frameworks: List[str] = Field(default_factory=list, alias="Frameworks")
    developer_tools: List[str] = Field(default_factory=list, alias="Developer Tools")
    libraries: List[str] = Field(default_factory=list, alias="Libraries")

    class Config:
        populate_by_name = True


class ResumeSections(BaseModel):
    education: List[EducationEntry] = Field(default_factory=list)
    experience: List[ExperienceEntry] = Field(default_factory=list)
    projects: List[ProjectEntry] = Field(default_factory=list)
    skills: SkillsSection = Field(default_factory=SkillsSection)


class ResumeJSON(BaseModel):
    metadata: ContactInfo
    sections: ResumeSections


class JobDescription(BaseModel):
    keywords: List[str] = Field(default_factory=list)
    technologies: List[str] = Field(default_factory=list)
    responsibilities: List[str] = Field(default_factory=list)
    nice_to_haves: List[str] = Field(default_factory=list)

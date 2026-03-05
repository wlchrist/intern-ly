"""Builder service: Convert resume JSON to LaTeX"""
from schemas import ResumeJSON


def format_line(value: str, length: int = 100) -> str:
    """Format text, truncating if needed"""
    if not value:
        return ""
    return value[:length] if len(value) > length else value


def truncate_at_word(text: str, max_len: int = 65) -> str:
    """Truncate text at word boundary to prevent overflow"""
    if len(text) <= max_len:
        return text
    
    # Find last space within max_len
    truncated = text[:max_len]
    last_space = truncated.rfind(' ')
    
    if last_space > 0:
        return text[:last_space] + "..."
    else:
        return truncated[:max_len-3] + "..."


def escape_latex(text: str) -> str:
    """Escape special LaTeX characters and truncate long text"""
    if not text:
        return ""
    
    # Truncate at word boundary to prevent overflow
    text = truncate_at_word(text, max_len=65)
    
    replacements = {
        "_": "\\_",
        "&": "\\&",
        "%": "\\%",
        "$": "\\$",
        "#": "\\#",
        "{": "\\{",
        "}": "\\}",
        "~": "\\textasciitilde{}",
        "^": "\\textasciicircum{}",
    }
    result = text
    for char, escaped in replacements.items():
        result = result.replace(char, escaped)
    return result


def build_resume_latex(resume: ResumeJSON) -> str:
    """Build full LaTeX document from resume JSON"""
    
    latex = r"""%-------------------------
% Resume in Latex
% Author : Jake Gutierrez
% Based off of: https://github.com/sb2nov/resume
% License : MIT
%------------------------

\documentclass[letterpaper,11pt]{article}

\usepackage{latexsym}
\usepackage[empty]{fullpage}
\usepackage{titlesec}
\usepackage{marvosym}
\usepackage[usenames,dvipsnames]{color}
\usepackage{verbatim}
\usepackage{enumitem}
\usepackage[hidelinks]{hyperref}
\usepackage{fancyhdr}
\usepackage[english]{babel}
\usepackage{tabularx}
\input{glyphtounicode}

\pagestyle{fancy}
\fancyhf{}
\fancyfoot{}
\renewcommand{\headrulewidth}{0pt}
\renewcommand{\footrulewidth}{0pt}

\addtolength{\oddsidemargin}{-0.5in}
\addtolength{\evensidemargin}{-0.5in}
\addtolength{\textwidth}{1in}
\addtolength{\topmargin}{-.5in}
\addtolength{\textheight}{1.0in}

\urlstyle{same}

\raggedbottom
\raggedright
\setlength{\tabcolsep}{0in}

\titleformat{\section}{
  \vspace{-4pt}\scshape\raggedright\large
}{}{0em}{}[\color{black}\titlerule \vspace{-5pt}]

\pdfgentounicode=1

%-------------------------
% Custom commands
\newcommand{\resumeItem}[1]{
  \item\small{
    {#1 \vspace{-2pt}}
  }
}

\newcommand{\resumeSubheading}[4]{
  \vspace{-2pt}\item
    \begin{tabular*}{0.97\textwidth}[t]{l@{\extracolsep{\fill}}r}
      \textbf{#1} & #2 \\
      \textit{\small#3} & \textit{\small #4} \\
    \end{tabular*}\vspace{-7pt}
}

\newcommand{\resumeSubheadingSimple}[2]{
  \vspace{-2pt}\item
    \begin{tabular*}{0.97\textwidth}[t]{l@{\extracolsep{\fill}}r}
      \textbf{#1} & \textit{\small #2} \\
    \end{tabular*}\vspace{-7pt}
}

\newcommand{\resumeSubHeadingListStart}{\begin{itemize}[leftmargin=0.15in, label={}]}
\newcommand{\resumeSubHeadingListEnd}{\end{itemize}}
\newcommand{\resumeItemListStart}{\begin{itemize}}
\newcommand{\resumeItemListEnd}{\end{itemize}\vspace{-5pt}}

%-------------------------------------------
%%%%%%  RESUME STARTS HERE  %%%%%%%%%%%%%%%%%%%%%%%%%%%%

\begin{document}

\begin{center}
    \textbf{\Huge \scshape """ + escape_latex(resume.metadata.name) + r"""} \\ \vspace{1pt}
    \small """
    
    # Contact line
    contact_parts = []
    if resume.metadata.email:
        contact_parts.append(f"\\href{{mailto:{escape_latex(resume.metadata.email)}}}{{\\underline{{{escape_latex(resume.metadata.email)}}}}}")
    if resume.metadata.linkedin:
        linkedin_display = resume.metadata.linkedin.replace("https://", "").replace("http://", "")
        contact_parts.append(f"\\href{{{resume.metadata.linkedin}}}{{\\underline{{{escape_latex(linkedin_display)}}}}}")
    if resume.metadata.github:
        github_display = resume.metadata.github.replace("https://", "").replace("http://", "")
        contact_parts.append(f"\\href{{{resume.metadata.github}}}{{\\underline{{{escape_latex(github_display)}}}}}")
    if resume.metadata.phone:
        contact_parts.append(escape_latex(resume.metadata.phone))
    
    if contact_parts:
        latex += " $|$ ".join(contact_parts)
    
    latex += r"""
\end{center}

"""
    
    # Education section
    if resume.sections.education:
        latex += r"""%-----------EDUCATION-----------
\section{Education}
  \resumeSubHeadingListStart
"""
        for entry in resume.sections.education:
            latex += f"""    \\resumeSubheading
      {{{escape_latex(entry.title)}}}{{{escape_latex(entry.location)}}}
      {{{escape_latex(entry.institution)}}}{{{escape_latex(entry.dates)}}}
"""
            if entry.highlights:
                latex += "      \\resumeItemListStart\n"
                for highlight in entry.highlights:
                    latex += f"        \\resumeItem{{{escape_latex(highlight)}}}\n"
                latex += "      \\resumeItemListEnd\n"
        latex += "  \\resumeSubHeadingListEnd\n\n"
    
    # Experience section
    if resume.sections.experience:
        latex += r"""%-----------EXPERIENCE-----------
\section{Experience}
  \resumeSubHeadingListStart
"""
        for entry in resume.sections.experience:
            latex += f"""\\resumeSubheading
{{{escape_latex(entry.title)}}}{{{escape_latex(entry.dates)}}}
{{{escape_latex(entry.company)}}}{{{escape_latex(entry.location)}}}
"""
            if entry.highlights:
                latex += "\\resumeItemListStart\n"
                for highlight in entry.highlights:
                    latex += f"\\resumeItem{{{escape_latex(highlight)}}}\n"
                latex += "\\resumeItemListEnd\n"
        latex += "  \\resumeSubHeadingListEnd\n\n"
    
    # Projects section
    if resume.sections.projects:
        latex += r"""%-----------PROJECTS-----------
\section{Technical Projects}
  \resumeSubHeadingListStart
"""
        for entry in resume.sections.projects:
            tech_and_dates = f"{entry.tech_stack} | {entry.dates}" if entry.tech_stack else entry.dates
            # Truncate tech/dates to prevent overflow on right side of heading
            tech_and_dates = truncate_at_word(tech_and_dates, max_len=50)
            latex += f"  \\resumeSubheadingSimple{{{escape_latex(entry.title)}}}{{{escape_latex(tech_and_dates)}}}\n"
            if entry.highlights:
                latex += "  \\resumeItemListStart\n"
                for highlight in entry.highlights:
                    latex += f"    \\resumeItem{{{escape_latex(highlight)}}}\n"
                latex += "  \\resumeItemListEnd\n\n"
        latex += "  \\resumeSubHeadingListEnd\n\n"
    
    # Skills section
    if resume.sections.skills:
        latex += r"""%-----------TECHNICAL SKILLS-----------
\section{Technical Skills}
 \begin{itemize}[leftmargin=0.15in, label={}]
    \small{\item{
"""
        skill_lines = []
        if resume.sections.skills.languages:
            langs = ", ".join(escape_latex(s) for s in resume.sections.skills.languages)
            skill_lines.append(f"     \\textbf{{Languages}}: {langs} \\\\")
        if resume.sections.skills.frameworks:
            frameworks = ", ".join(escape_latex(s) for s in resume.sections.skills.frameworks)
            skill_lines.append(f"     \\textbf{{Frameworks}}: {frameworks} \\\\")
        if resume.sections.skills.developer_tools:
            tools = ", ".join(escape_latex(s) for s in resume.sections.skills.developer_tools)
            skill_lines.append(f"     \\textbf{{Developer Tools}}: {tools} \\\\")
        if resume.sections.skills.libraries:
            libraries = ", ".join(escape_latex(s) for s in resume.sections.skills.libraries)
            skill_lines.append(f"     \\textbf{{Libraries}}: {libraries}")
        
        latex += "\n".join(skill_lines)
        latex += r"""
    }}
 \end{itemize}

%-------------------------------------------
\end{document}
"""
    
    return latex


async def build_tex(resume: ResumeJSON) -> str:
    """
    Build resume LaTeX source from JSON.
    Returns the LaTeX source code as a string.
    """
    latex_content = build_resume_latex(resume)
    return latex_content

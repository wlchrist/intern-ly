import { useEffect, useMemo, useState } from 'react';
import { jsPDF } from 'jspdf';
import './App.css';

// Backend API URL - update this with your deployed backend URL
const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';

type ParsedResume = {
  bullets: string[];
  skills: string[];
  plainText: string;
};

type DraftContent = {
  summary: string;
  bullets: string[];
  skills: string[];
  keywords: string[];
};

const STOPWORDS = new Set([
  'the',
  'and',
  'for',
  'with',
  'that',
  'this',
  'you',
  'your',
  'from',
  'into',
  'have',
  'has',
  'are',
  'our',
  'about',
  'will',
  'able',
  'job',
  'role',
  'team',
  'work',
  'using',
  'experience',
  'internship',
  'intern',
  'candidate',
  'responsibilities',
  'requirements',
  'resume',
  'draft',
  'tailored',
  'summary',
  'selected',
  'relevant',
  'skills',
  'notes',
  'student',
  'candidate',
]);

const LATEX_ARTIFACT_RE_GLOBAL =
  /\b(tabular\*?|itemize|enumerate|leftmargin|rightmargin|label|extracolsep|textwidth|hfill|vspace|small|large|normalsize|bfseries|itshape|textbf|textit|hspace|quad|qquad)\b/gi;
const LATEX_ARTIFACT_RE_SINGLE =
  /\b(tabular\*?|itemize|enumerate|leftmargin|rightmargin|label|extracolsep|textwidth|hfill|vspace|small|large|normalsize|bfseries|itshape|textbf|textit|hspace|quad|qquad)\b/i;

const SKILL_LABELS = new Set([
  'hardware & systems',
  'languages & scripting',
  'networking & os',
  'networking and os',
  'ai/ml',
  'ai',
  'ml',
  'skills',
  'technical skills',
]);

function normalizeSkillToken(token: string): string {
  return token
    .replace(/\\&/g, '&')
    .replace(/\\\//g, '/')
    .replace(/\s+/g, ' ')
    .replace(/^[-=:\s]+/, '')
    .replace(/[\s,:;.-]+$/, '')
    .trim();
}

function cleanLatex(input: string): string {
  let text = input;
  text = text.replace(/%.*$/gm, '');
  text = text.replace(/\\&/g, ' & ');
  text = text.replace(/\\\\/g, '\n');
  text = text.replace(/\\begin\{[^}]+\}|\\end\{[^}]+\}/g, ' ');
  for (let i = 0; i < 6; i += 1) {
    text = text.replace(/\\[a-zA-Z*]+(?:\[[^\]]*\])?\{([^{}]*)\}/g, '$1');
  }
  text = text.replace(/\\[a-zA-Z*]+(?:\[[^\]]*\])?/g, ' ');
  text = text.replace(/[\[\]]/g, ' ');
  text = text.replace(LATEX_ARTIFACT_RE_GLOBAL, ' ');
  text = text.replace(/[{}]/g, ' ');
  text = text.replace(/\s+/g, ' ').trim();
  return text;
}

function parseLatexResume(latex: string): ParsedResume {
  const lines = latex.split('\n');
  const itemBullets = lines
    .map((line) => line.trim())
    .filter((line) => line.startsWith('\\item'))
    .map((line) => line.replace(/^\\item(?:\[[^\]]*\])?\s*/, ''))
    .map((line) => cleanLatex(line));

  const resumeItemBullets = lines
    .map((line) => line.trim())
    .filter((line) => line.includes('\\resumeItem'))
    .map((line) => {
      const match = line.match(/\\resumeItem\s*\{(.+)\}\s*$/);
      return cleanLatex(match ? match[1] : line);
    });

  const cleanedText = cleanLatex(latex);
  const sentenceFallback = cleanedText
    .split(/(?<=[.!?])\s+/)
    .map((sentence) => sentence.trim())
    .filter((sentence) => sentence.length >= 45 && sentence.length <= 220)
    .slice(0, 20);

  const rawBullets = [...itemBullets, ...resumeItemBullets];
  const normalizedBullets = (rawBullets.length > 0 ? rawBullets : sentenceFallback)
    .map((bullet) => bullet.replace(/^[-•\s]+/, '').trim())
    .filter((bullet) => bullet.length >= 20 && bullet.length <= 240)
    .filter((bullet) => !LATEX_ARTIFACT_RE_SINGLE.test(bullet))
    .filter((bullet) => !/^[a-zA-Z0-9\s\\{}\[\].,:;|()@#%&*+-]+$/.test(bullet) || bullet.includes(' '))
    .filter((bullet) => (bullet.match(/\b[a-zA-Z]{3,}\b/g)?.length ?? 0) >= 4)
    .filter(
      (value, index, arr) => arr.findIndex((x) => x.toLowerCase() === value.toLowerCase()) === index,
    );

  const allText = cleanedText;
  const skillSource = allText
    .split(/[,|•\n:;]+/)
    .map((chunk) => normalizeSkillToken(chunk))
    .filter((chunk) => chunk.length > 1)
    .filter((chunk) => !SKILL_LABELS.has(chunk.toLowerCase()))
    .filter((chunk) => !LATEX_ARTIFACT_RE_SINGLE.test(chunk));

  const skills = skillSource
    .filter((s) => s.length >= 2 && s.length <= 32)
    .filter((s) => !/^[-=]+$/.test(s))
    .filter((s) => !/^(and|or|with|using)$/i.test(s))
    .slice(0, 30)
    .filter((value, index, arr) => arr.findIndex((x) => x.toLowerCase() === value.toLowerCase()) === index);

  return {
    bullets: normalizedBullets,
    skills,
    plainText: allText,
  };
}

function extractKeywords(jobDescription: string): string[] {
  const tokens = jobDescription
    .toLowerCase()
    .replace(/[^a-z0-9\s+#.-]/g, ' ')
    .split(/\s+/)
    .filter((token) => token.length >= 3 && token.length <= 24 && !STOPWORDS.has(token))
    .filter((token) => !/^\d+$/.test(token));

  const freq = new Map<string, number>();
  for (const token of tokens) {
    freq.set(token, (freq.get(token) ?? 0) + 1);
  }

  return Array.from(freq.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 20)
    .map(([token]) => token);
}

function scoreBullet(bullet: string, keywords: string[]): number {
  const lower = bullet.toLowerCase();
  return keywords.reduce((score, keyword) => score + (lower.includes(keyword) ? 1 : 0), 0);
}

function canonicalizeSkill(skill: string): string {
  return skill.toLowerCase().replace(/[^a-z0-9+#/]+/g, ' ').trim();
}

function isSkillNoise(skill: string): boolean {
  const lower = skill.toLowerCase();
  if (lower.length < 2 || lower.length > 36) {
    return true;
  }

  if (/^(and|or|with|using|systems|skills)$/i.test(lower)) {
    return true;
  }

  if (
    lower.includes('networking & os') ||
    lower.includes('languages & scripting') ||
    lower.includes('hardware & systems') ||
    lower.includes('technical skills')
  ) {
    return true;
  }

  return false;
}

function rankSkills(skills: string[], keywords: string[]): string[] {
  const seen = new Set<string>();

  const ranked = skills
    .map((skill) => skill.trim())
    .filter((skill) => !isSkillNoise(skill))
    .map((skill) => {
      const lower = skill.toLowerCase();
      const keywordScore = keywords.reduce((score, keyword) => {
        if (lower.includes(keyword) || keyword.includes(lower)) {
          return score + 2;
        }
        return score;
      }, 0);
      const specificityBoost = /[+#/]|\d/.test(skill) ? 1 : 0;
      return { skill, score: keywordScore + specificityBoost };
    })
    .sort((a, b) => b.score - a.score || a.skill.length - b.skill.length)
    .map((entry) => entry.skill)
    .filter((skill) => {
      const key = canonicalizeSkill(skill);
      if (!key || seen.has(key)) {
        return false;
      }
      seen.add(key);
      return true;
    });

  return ranked.slice(0, 12);
}

function escapeLatexText(value: string): string {
  return value
    .replace(/\\/g, '\\textbackslash{}')
    .replace(/([#$%&_{}])/g, '\\$1')
    .replace(/~/g, '\\textasciitilde{}')
    .replace(/\^/g, '\\textasciicircum{}');
}

function parseOutputToSections(output: string): {
  summary: string;
  bullets: string[];
  skills: string[];
} {
  const lines = output.split('\n').map((line) => line.trim());

  const summaryIndex = lines.findIndex((line) => line.toLowerCase() === 'summary');
  const bulletsIndex = lines.findIndex((line) => line.toLowerCase() === 'selected experience bullets');
  const skillsIndex = lines.findIndex((line) => line.toLowerCase() === 'relevant skills');
  const notesIndex = lines.findIndex((line) => line.toLowerCase() === 'notes');

  const summary = summaryIndex >= 0 ? (lines[summaryIndex + 1] ?? '') : '';

  const bulletsRaw =
    bulletsIndex >= 0
      ? lines.slice(bulletsIndex + 1, skillsIndex > bulletsIndex ? skillsIndex : lines.length)
      : [];

  const bullets = bulletsRaw
    .filter((line) => line.startsWith('- '))
    .map((line) => line.replace(/^-\s*/, '').trim())
    .filter((line) => line.length > 0);

  const skillsLine = skillsIndex >= 0 ? (lines[skillsIndex + 1] ?? '') : '';
  const skills = skillsLine
    .split('|')
    .map((skill) => skill.trim())
    .filter((skill) => skill.length > 0);

  return {
    summary,
    bullets,
    skills: notesIndex > -1 ? skills.slice(0, 15) : skills,
  };
}

function buildLatexResume(output: string): string {
  const { summary, bullets, skills } = parseOutputToSections(output);

  const safeSummary = escapeLatexText(summary || 'Tailored internship-ready summary.');
  const safeBullets = (bullets.length > 0
    ? bullets
    : ['Add bullets from your uploaded resume and regenerate.']
  ).map((bullet) => `  \\item ${escapeLatexText(bullet)}`);

  const safeSkills = escapeLatexText(
    skills.length > 0 ? skills.join(' \u00b7 ') : 'Add relevant skills from your resume',
  );

  return [
    '\\documentclass[10pt]{article}',
    '\\usepackage[margin=0.75in]{geometry}',
    '\\usepackage[T1]{fontenc}',
    '\\usepackage{enumitem}',
    '\\setlist[itemize]{leftmargin=1.2em, itemsep=2pt, topsep=2pt}',
    '\\begin{document}',
    '',
    '\\section*{Summary}',
    safeSummary,
    '',
    '\\section*{Experience Highlights}',
    '\\begin{itemize}',
    ...safeBullets,
    '\\end{itemize}',
    '',
    '\\section*{Skills}',
    safeSkills,
    '',
    '\\end{document}',
    '',
  ].join('\n');
}

function sanitizeComment(value: string): string {
  return value.replace(/\s+/g, ' ').replace(/%/g, '').trim();
}

function buildTemplateInjectedLatex(masterLatex: string, output: string): string {
  const { summary, bullets, skills } = parseOutputToSections(output);
  const safeBullets = (bullets.length > 0
    ? bullets
    : ['Add bullet points to your LaTeX resume with \\item for better tailoring.']
  ).map((bullet) => escapeLatexText(bullet));

  let bulletIndex = 0;
  const lines = masterLatex.split('\n');
  const replacedLines = lines.map((line) => {
    if (bulletIndex >= safeBullets.length) {
      return line;
    }

    const itemMatch = line.match(/^(\s*\\item(?:\[[^\]]*\])?\s*)(.*)$/);
    if (!itemMatch) {
      return line;
    }

    const prefix = itemMatch[1];
    const nextLine = `${prefix}${safeBullets[bulletIndex]}`;
    bulletIndex += 1;
    return nextLine;
  });

  const hasAnyItem = bulletIndex > 0;
  if (!hasAnyItem) {
    return buildLatexResume(output);
  }

  const contextComments = [
    '% Internly Tailoring Context',
    `% Summary: ${sanitizeComment(summary || 'Generated from provided job description')}`,
    `% Skills Focus: ${sanitizeComment(skills.slice(0, 12).join(', ') || 'N/A')}`,
    '',
  ];

  const beginDocIndex = replacedLines.findIndex((line) => /\\begin\{document\}/.test(line));
  if (beginDocIndex >= 0) {
    replacedLines.splice(beginDocIndex + 1, 0, ...contextComments);
    return replacedLines.join('\n');
  }

  return [...contextComments, ...replacedLines].join('\n');
}

function downloadBlob(content: BlobPart, mimeType: string, fileName: string): void {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');

  anchor.href = url;
  anchor.download = fileName;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function buildPdfFromOutput(output: string): jsPDF {
  const { summary, bullets, skills } = parseOutputToSections(output);
  const doc = new jsPDF({ unit: 'pt', format: 'letter' });
  const pageWidth = doc.internal.pageSize.getWidth();
  const pageHeight = doc.internal.pageSize.getHeight();
  const margin = 44;
  const maxWidth = pageWidth - margin * 2;
  let y = margin;

  const ensureSpace = (nextHeight: number) => {
    if (y + nextHeight > pageHeight - margin) {
      doc.addPage();
      y = margin;
    }
  };

  const addHeading = (text: string) => {
    ensureSpace(26);
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(13);
    doc.text(text, margin, y);
    y += 18;
  };

  const addWrappedText = (text: string, indent = 0) => {
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(11);
    const lines = doc.splitTextToSize(text, maxWidth - indent);
    for (const line of lines) {
      ensureSpace(14);
      doc.text(line, margin + indent, y);
      y += 14;
    }
  };

  addHeading('TAILORED INTERNSHIP RESUME DRAFT');
  addHeading('Summary');
  addWrappedText(summary || 'Tailored internship-ready summary.');
  y += 8;

  addHeading('Selected Experience Bullets');
  if (bullets.length === 0) {
    addWrappedText('• Add bullet points to your LaTeX resume with \\item for better tailoring.');
  } else {
    for (const bullet of bullets) {
      addWrappedText(`• ${bullet}`);
      y += 2;
    }
  }
  y += 6;

  addHeading('Relevant Skills');
  addWrappedText(skills.length > 0 ? skills.join(' | ') : 'Add relevant skills from your resume.');

  return doc;
}

function buildDraftContent(masterLatex: string, jobDescription: string): DraftContent {
  const parsed = parseLatexResume(masterLatex);
  const keywords = extractKeywords(jobDescription);

  const rankedBullets = parsed.bullets
    .map((bullet) => ({ bullet, score: scoreBullet(bullet, keywords) }))
    .sort((a, b) => b.score - a.score || b.bullet.length - a.bullet.length)
    .map((item) => item.bullet);

  const selectedBullets = rankedBullets.slice(0, 6);
  const selectedSkills = rankSkills(parsed.skills, keywords);

  const summaryKeywords = keywords.slice(0, 6).join(', ');
  const summary =
    summaryKeywords.length > 0
      ? `Student candidate with hands-on project and technical experience aligned with: ${summaryKeywords}.`
      : 'Student candidate with project-driven experience and practical technical background aligned to the internship scope.';

  return {
    summary,
    bullets: selectedBullets,
    skills: selectedSkills,
    keywords,
  };
}

function formatDraftOutput(draft: DraftContent): string {
  return [
    'TAILORED INTERNSHIP RESUME DRAFT',
    '',
    'Summary',
    draft.summary,
    '',
    'Selected Experience Bullets',
    ...(draft.bullets.length > 0
      ? draft.bullets.map((bullet) => `- ${bullet}`)
      : ['- Add bullet points to your LaTeX resume with \\item for better tailoring.']),
    '',
    'Relevant Skills',
    draft.skills.length > 0 ? draft.skills.join(' | ') : 'Add relevant skills from your resume',
    '',
    'Notes',
    '- This draft only rewrites and prioritizes content from your uploaded resume.',
    '- Review wording and metrics before submitting applications.',
  ].join('\n');
}

function tryExtractJsonObject(raw: string): Record<string, unknown> | null {
  const first = raw.indexOf('{');
  const last = raw.lastIndexOf('}');
  if (first < 0 || last <= first) {
    return null;
  }

  const maybeJson = raw.slice(first, last + 1);
  try {
    return JSON.parse(maybeJson) as Record<string, unknown>;
  } catch {
    return null;
  }
}

async function rewriteDraftWithAnthropic(
  draft: DraftContent,
  jobDescription: string,
): Promise<DraftContent> {
  const draftText = [
    'BULLETS:',
    ...draft.bullets.map((bullet, index) => `${index + 1}. ${bullet}`),
    '',
    'SKILLS:',
    draft.skills.join(' | '),
  ].join('\n');

  const response = await fetch(`${BACKEND_URL}/api/rewrite`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
    },
    body: JSON.stringify({
      draft: draftText,
      job_description: jobDescription,
      temperature: 0.2,
      max_tokens: 700,
    }),
  });

  if (!response.ok) {
    const errorText = await response.text().catch(() => 'Unknown error');
    throw new Error(`Backend request failed: ${response.status} - ${errorText}`);
  }

  const data = (await response.json()) as {
    rewritten?: string;
  };
  const text = data.rewritten ?? '';
  const parsed = tryExtractJsonObject(text);

  if (!parsed) {
    throw new Error('Could not parse AI response.');
  }

  const rewrittenSummary = typeof parsed.summary === 'string' && parsed.summary.trim().length > 0
    ? parsed.summary.trim()
    : draft.summary;

  const rewrittenBullets = Array.isArray(parsed.bullets)
    ? parsed.bullets
        .filter((item): item is string => typeof item === 'string')
        .map((item) => item.trim())
        .filter((item) => item.length > 15)
        .slice(0, 6)
    : draft.bullets;

  const rewrittenSkills = Array.isArray(parsed.skills)
    ? parsed.skills
        .filter((item): item is string => typeof item === 'string')
        .map((item) => item.trim())
        .filter((item) => item.length > 1)
        .slice(0, 12)
    : draft.skills;

  return {
    ...draft,
    summary: rewrittenSummary,
    bullets: rewrittenBullets.length > 0 ? rewrittenBullets : draft.bullets,
    skills: rewrittenSkills.length > 0 ? rewrittenSkills : draft.skills,
  };
}

function generateTailoredResume(masterLatex: string, jobDescription: string): string {
  const draft = buildDraftContent(masterLatex, jobDescription);
  return formatDraftOutput(draft);
}

function App() {
  const [masterLatex, setMasterLatex] = useState('');
  const [jobDescription, setJobDescription] = useState('');
  const [fileName, setFileName] = useState('');
  const [output, setOutput] = useState('');
  const [error, setError] = useState('');
  const [hasGenerated, setHasGenerated] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [useAiRewrite, setUseAiRewrite] = useState(false);
  const isReady = useMemo(() => masterLatex.trim().length > 0 && jobDescription.trim().length > 0, [masterLatex, jobDescription]);

  const handleUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    setError('');
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    if (!file.name.toLowerCase().endsWith('.tex')) {
      setError('Please upload a .tex file.');
      return;
    }
    setFileName(file.name);
    const text = await file.text();
    setMasterLatex(text);
  };

  const handleGenerate = async () => {
    setError('');
    if (!isReady) {
      setError('Upload your master resume and paste a job description first.');
      return;
    }

    setIsGenerating(true);
    try {
      let draft = buildDraftContent(masterLatex, jobDescription);

      if (useAiRewrite) {
        try {
          draft = await rewriteDraftWithAnthropic(draft, jobDescription);
        } catch (err) {
          const message = err instanceof Error ? err.message : 'Unknown error';
          setError(`AI rewrite failed: ${message}. Used rule-based output instead.`);
        }
      }

      const generated = formatDraftOutput(draft);
      setOutput(generated);
      setHasGenerated(true);

      if (typeof chrome !== 'undefined' && chrome.storage?.local) {
        chrome.storage.local
          .set({
            internly_last_output: generated,
          })
          .catch(() => undefined);
      }
    } finally {
      setIsGenerating(false);
    }
  };

  const downloadLatex = () => {
    if (!output.trim()) {
      setError('Generate a resume draft before downloading .tex.');
      return;
    }

    const tex = buildTemplateInjectedLatex(masterLatex, output);
    const baseName = fileName ? fileName.replace(/\.tex$/i, '') : 'internly_resume';
    downloadBlob(tex, 'application/x-tex;charset=utf-8', `${baseName}_tailored.tex`);
  };

  const downloadPdf = () => {
    if (!output.trim()) {
      setError('Generate a resume draft before downloading .pdf.');
      return;
    }
    const baseName = fileName ? fileName.replace(/\.tex$/i, '') : 'internly_resume';
    const pdf = buildPdfFromOutput(output);
    pdf.save(`${baseName}_tailored.pdf`);
  };

  return (
    <div className="app">
      <h1>Intern.ly</h1>
      <p className="subtitle">Tailor resume drafts for internship applications.</p>

      <div className="section">
        <label htmlFor="resume-upload">1) Upload master resume (.tex)</label>
        <input id="resume-upload" type="file" accept=".tex" onChange={handleUpload} />
        {fileName && <p className="hint">Loaded: {fileName}</p>}
      </div>

      <div className="section">
        <label htmlFor="job-description">2) Paste job description</label>
        <textarea
          id="job-description"
          value={jobDescription}
          onChange={(e) => setJobDescription(e.target.value)}
          placeholder="Paste internship description here..."
          rows={6}
        />
      </div>

      <div className="section">
        <label className="hint" htmlFor="enable-ai">
          <input
            id="enable-ai"
            type="checkbox"
            checked={useAiRewrite}
            onChange={(e) => setUseAiRewrite(e.target.checked)}
            style={{ marginRight: 8 }}
          />
          3) Use AI to improve phrasing (subject to rate limits)
        </label>
      </div>

      <div className="actions">
        <button type="button" onClick={handleGenerate} disabled={!isReady || isGenerating}>
          {isGenerating ? 'Generating...' : 'Generate Files'}
        </button>
        <button type="button" className="secondary" onClick={downloadLatex} disabled={!output}>
          Download .tex
        </button>
        <button type="button" className="secondary" onClick={downloadPdf} disabled={!output}>
          Download .pdf
        </button>
      </div>

      {error && <p className="error">{error}</p>}

      {hasGenerated && !error && (
        <p className="hint">Resume files are ready. Download your .tex and .pdf outputs.</p>
      )}
    </div>
  );
}

export default App;

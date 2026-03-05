import { useMemo, useState } from 'react';
import { jsPDF } from 'jspdf';
import './App.css';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';

type TailorResponse = {
  output: string;
  latex: string;
};

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
    addWrappedText('• Add bullet points to your LaTeX resume and regenerate.');
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

async function tailorResumeWithAi(masterResume: string, jobDescription: string): Promise<TailorResponse> {
  const response = await fetch(`${BACKEND_URL}/api/tailor`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
    },
    body: JSON.stringify({
      master_resume: masterResume,
      job_description: jobDescription,
      temperature: 0.2,
      max_tokens: 1400,
    }),
  });

  if (!response.ok) {
    const errorText = await response.text().catch(() => 'Unknown error');
    throw new Error(`Backend request failed: ${response.status} - ${errorText}`);
  }

  const data = (await response.json()) as TailorResponse;
  if (!data.output || !data.latex) {
    throw new Error('Backend returned an incomplete tailored resume response.');
  }

  return data;
}

function App() {
  const [masterResume, setMasterResume] = useState('');
  const [jobDescription, setJobDescription] = useState('');
  const [fileName, setFileName] = useState('');
  const [output, setOutput] = useState('');
  const [generatedLatex, setGeneratedLatex] = useState('');
  const [error, setError] = useState('');
  const [hasGenerated, setHasGenerated] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);

  const isReady = useMemo(
    () => masterResume.trim().length > 0 && jobDescription.trim().length > 0,
    [masterResume, jobDescription],
  );

  const handleUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    setError('');
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    const supportedExtensions = ['.tex', '.txt', '.md', '.rtf'];
    const lowerName = file.name.toLowerCase();
    const isSupported = supportedExtensions.some((ext) => lowerName.endsWith(ext));
    if (!isSupported) {
      setError('Please upload a text-based resume file (.tex, .txt, .md, or .rtf).');
      return;
    }
    setFileName(file.name);
    const text = await file.text();
    setMasterResume(text);
  };

  const handleGenerate = async () => {
    setError('');
    if (!isReady) {
      setError('Upload your master resume and paste a job description first.');
      return;
    }

    setIsGenerating(true);
    try {
      const tailored = await tailorResumeWithAi(masterResume, jobDescription);
      setOutput(tailored.output);
      setGeneratedLatex(tailored.latex);
      setHasGenerated(true);

      if (typeof chrome !== 'undefined' && chrome.storage?.local) {
        chrome.storage.local
          .set({
            internly_last_output: tailored.output,
          })
          .catch(() => undefined);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      setError(`AI tailoring failed: ${message}`);
    } finally {
      setIsGenerating(false);
    }
  };

  const downloadLatex = () => {
    if (!generatedLatex.trim()) {
      setError('Generate a resume draft before downloading .tex.');
      return;
    }

    const baseName = fileName ? fileName.replace(/\.tex$/i, '') : 'internly_resume';
    downloadBlob(generatedLatex, 'application/x-tex;charset=utf-8', `${baseName}_tailored.tex`);
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
      <p className="subtitle">Tailor resumes with AI parsing and a consistent base template.</p>

      <div className="section">
        <label htmlFor="resume-upload">1) Upload master resume (.tex, .txt, .md, .rtf)</label>
        <input id="resume-upload" type="file" accept=".tex,.txt,.md,.rtf,text/plain,text/markdown,application/rtf" onChange={handleUpload} />
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
        <p className="hint">3) Generate tailored resume (AI parsing + relevance filtering)</p>
      </div>

      <div className="actions">
        <button type="button" onClick={handleGenerate} disabled={!isReady || isGenerating}>
          {isGenerating ? 'Generating...' : 'Generate Files'}
        </button>
        <button type="button" className="secondary" onClick={downloadLatex} disabled={!generatedLatex}>
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

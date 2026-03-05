import { useMemo, useState, useEffect, useRef } from 'react';
import './App.css';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';

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

async function tailorResumeWithAi(masterResume: string, jobDescription: string): Promise<Blob> {
  const response = await fetch(`${BACKEND_URL}/api/tailor`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
    },
    body: JSON.stringify({
      master_resume: masterResume,
      master_latex: masterResume,
      job_description: jobDescription,
      temperature: 0.2,
      max_tokens: 1400,
    }),
  });

  if (!response.ok) {
    const errorText = await response.text().catch(() => 'Unknown error');
    throw new Error(`Backend request failed: ${response.status} - ${errorText}`);
  }

  const contentType = response.headers.get('content-type') ?? '';
  if (!contentType.includes('text/plain') && !contentType.includes('application/pdf')) {
    const errorText = await response.text().catch(() => 'Unexpected response.');
    throw new Error(`Expected LaTeX or PDF response but got ${contentType || 'unknown type'}: ${errorText}`);
  }

  return await response.blob();
}

function App() {
  const [masterResume, setMasterResume] = useState('');
  const [jobDescription, setJobDescription] = useState('');
  const [fileName, setFileName] = useState('');
  const [generatedPdf, setGeneratedPdf] = useState<Blob | null>(null);
  const [error, setError] = useState('');
  const [hasGenerated, setHasGenerated] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [githubUser, setGithubUser] = useState<string | null>(null);
  const [useGitHubProjects, setUseGitHubProjects] = useState(false);
  const [showOptions, setShowOptions] = useState(false);
  const hasAutoResumedRef = useRef(false);

  // Load persisted data from storage when component mounts
  useEffect(() => {
    if (typeof chrome !== 'undefined' && chrome.storage?.local) {
      chrome.storage.local
        .get([
          'internly_master_resume',
          'internly_job_description',
          'internly_file_name',
          'internly_is_generating',
          'internly_has_generated',
        ])
        .then((result) => {
          if (result.internly_master_resume) {
            setMasterResume(result.internly_master_resume);
          }
          if (result.internly_job_description) {
            setJobDescription(result.internly_job_description);
          }
          if (result.internly_file_name) {
            setFileName(result.internly_file_name);
          }
          if (result.internly_is_generating) {
            setIsGenerating(true);
          }
          if (result.internly_has_generated) {
            setHasGenerated(true);
          }
        })
        .catch(() => undefined);
    }
  }, []);

  // Save masterResume to storage whenever it changes
  useEffect(() => {
    if (typeof chrome !== 'undefined' && chrome.storage?.local && masterResume) {
      chrome.storage.local
        .set({
          internly_master_resume: masterResume,
        })
        .catch(() => undefined);
    }
  }, [masterResume]);

  // Save jobDescription to storage whenever it changes
  useEffect(() => {
    if (typeof chrome !== 'undefined' && chrome.storage?.local && jobDescription) {
      chrome.storage.local
        .set({
          internly_job_description: jobDescription,
        })
        .catch(() => undefined);
    }
  }, [jobDescription]);

  // Save useGitHubProjects to storage
  useEffect(() => {
    if (typeof chrome !== 'undefined' && chrome.storage?.local) {
      chrome.storage.local
        .set({
          internly_use_github_projects: useGitHubProjects,
        })
        .catch(() => undefined);
    }
  }, [useGitHubProjects]);

  // Save githubUser to storage
  useEffect(() => {
    if (typeof chrome !== 'undefined' && chrome.storage?.local) {
      chrome.storage.local
        .set({
          internly_github_user: githubUser || '',
        })
        .catch(() => undefined);
    }
  }, [githubUser]);

  // Save isGenerating state to storage
  useEffect(() => {
    if (typeof chrome !== 'undefined' && chrome.storage?.local) {
      chrome.storage.local
        .set({
          internly_is_generating: isGenerating,
        })
        .catch(() => undefined);
    }
  }, [isGenerating]);

  // Save hasGenerated state to storage
  useEffect(() => {
    if (typeof chrome !== 'undefined' && chrome.storage?.local) {
      chrome.storage.local
        .set({
          internly_has_generated: hasGenerated,
        })
        .catch(() => undefined);
    }
  }, [hasGenerated]);

  // If generation was in progress when popup closed, resume it
  useEffect(() => {
    const resumeGeneration = async () => {
      // Only auto-resume once per mount
      if (hasAutoResumedRef.current) {
        return;
      }

      if (isGenerating && masterResume && jobDescription) {
        hasAutoResumedRef.current = true;
        try {
          const tailoredPdf = await tailorResumeWithAi(masterResume, jobDescription);
          setGeneratedPdf(tailoredPdf);
          setHasGenerated(true);
          setIsGenerating(false);
        } catch (err) {
          const message = err instanceof Error ? err.message : 'Unknown error';
          setError(`AI tailoring failed: ${message}`);
          setIsGenerating(false);
        }
      }
    };

    resumeGeneration();
  }, [isGenerating, masterResume, jobDescription]);

  const handleGitHubLogin = () => {
    // Placeholder for GitHub OAuth flow
    setGithubUser('wlchrist'); // Mock user for now
  };

  const handleGitHubLogout = () => {
    setGithubUser(null);
  };

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
      const tailoredPdf = await tailorResumeWithAi(masterResume, jobDescription);
      setGeneratedPdf(tailoredPdf);
      setHasGenerated(true);

      if (typeof chrome !== 'undefined' && chrome.storage?.local) {
        chrome.storage.local
          .set({
            internly_last_output: 'PDF generated',
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

  const downloadTex = () => {
    if (!generatedPdf) {
      setError('Generate a resume draft before downloading .tex.');
      return;
    }
    const baseName = fileName ? fileName.replace(/\.[^/.]+$/, '') : 'internly_resume';
    downloadBlob(generatedPdf, 'text/plain', `${baseName}_tailored.tex`);
  };

  return (
    <div className="app">
      <div className="header">
        <div className="title-section">
          <h1>Intern.ly</h1>
          <p className="subtitle">Tailor resumes with AI parsing and a consistent base template.</p>
        </div>
        <div className="auth-section">
          {githubUser ? (
            <div className="github-user">
              <span className="user-badge">💻 {githubUser}</span>
              <button type="button" className="logout-btn" onClick={handleGitHubLogout}>
                Logout
              </button>
            </div>
          ) : (
            <button type="button" className="github-btn" onClick={handleGitHubLogin}>
              Login with GitHub
            </button>
          )}
        </div>
      </div>

      <div className="options-toggle">
        <button type="button" className="toggle-btn" onClick={() => setShowOptions(!showOptions)}>
          {showOptions ? '✕' : '⚙'} Options
        </button>
      </div>

      {showOptions && (
        <div className="options-panel">
          <div className="option-item">
            <label htmlFor="use-github-projects">
              <input
                id="use-github-projects"
                type="checkbox"
                checked={useGitHubProjects}
                onChange={(e) => setUseGitHubProjects(e.target.checked)}
                disabled={!githubUser}
              />
              <span>Pull projects from GitHub</span>
            </label>
            <p className="option-hint">Automatically fetch and include your GitHub projects in the resume</p>
          </div>
        </div>
      )}

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
        <p className="hint">3) Generate tailored resume LaTeX file (AI parsing + job-relevant rewriting)</p>
      </div>

      <div className="actions">
        <button type="button" onClick={handleGenerate} disabled={!isReady || isGenerating}>
          {isGenerating ? 'Generating...' : 'Generate Resume'}
        </button>
        <button type="button" className="secondary" onClick={downloadTex} disabled={!generatedPdf}>
          Download .tex
        </button>
      </div>

      {error && <p className="error">{error}</p>}

      {hasGenerated && !error && (
        <p className="hint">Tailored resume LaTeX is ready. Download and compile with pdflatex, Overleaf, or your local LaTeX tool.</p>
      )}
    </div>
  );
}

export default App;

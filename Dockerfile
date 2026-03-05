FROM python:3.11-slim

# Install LaTeX and required system packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    texlive-latex-base \
    texlive-fonts-recommended \
    texlive-latex-extra \
    texlive-xetex \
    cm-super \
    dvipng \
    && rm -rf /var/lib/apt/lists/*

# Verify pdflatex is installed
RUN which pdflatex || (echo "pdflatex not found!" && exit 1)

WORKDIR /app

# Copy requirements and install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code and template
COPY backend/*.py .
COPY backend/resume_template.tex .

# Expose port
EXPOSE 8000

# Run the application
CMD ["python", "main.py"]

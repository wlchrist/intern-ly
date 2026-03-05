# Resume Tailor - Quick Start Guide

Simple setup to get the extension working with backend rate limiting (no user API keys required).

## For Local Testing

### 1. Start the Backend

```bash
cd backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure API key
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY

# Run server
python main.py
# Backend running at http://localhost:8000
```

### 2. Load the Extension

```bash
cd wxt-dev-wxt

# Install dependencies (if not done)
pnpm install

# Build for development
pnpm run dev
# OR for production build:
# pnpm wxt build
```

**Load in Chrome**:
1. Open `chrome://extensions/`
2. Enable "Developer mode"
3. Click "Load unpacked"
4. Select `.output/chrome-mv3-dev/` folder (or `.output/chrome-mv3/` for production build)

### 3. Test the Extension

1. Click the extension icon in Chrome toolbar
2. Upload a `.tex` resume file
3. Paste a job description
4. Check "Use AI to improve phrasing" (optional)
5. Click "Generate Files"
6. Download `.tex` and `.pdf` outputs

**Rate Limits**: 10 requests per minute per IP (configurable in `backend/main.py`)

---

## For Public Deployment

See [DEPLOYMENT.md](./DEPLOYMENT.md) for complete production deployment guide including:
- Backend deployment to Render/Railway/Fly.io
- Chrome Web Store publication
- Rate limiting configuration
- Cost management
- Privacy policy requirements

---

## Architecture

```
Extension (React + WXT)
    ↓
Backend (FastAPI + Rate Limiting)
    ↓
Anthropic Claude 3.5 Haiku API
```

**Key Features**:
- ✅ Users never see or need API keys
- ✅ Rate limiting prevents abuse (10 req/min per IP)
- ✅ Deterministic parsing fallback (works without AI)
- ✅ Privacy-first (local resume parsing, optional cloud rewrite)

---

## Configuration

### Backend Rate Limits

Edit `backend/main.py`:
```python
@limiter.limit("10/minute")  # Change to "50/hour", "100/day", etc.
async def rewrite_resume(...):
```

### Extension Backend URL

Edit `wxt-dev-wxt/.env`:
```bash
VITE_BACKEND_URL=http://localhost:8000  # Local testing
# VITE_BACKEND_URL=https://your-backend.onrender.com  # Production
```

Rebuild after changes: `pnpm wxt build`

---

## Troubleshooting

**Backend not connecting?**
- Check backend is running: `curl http://localhost:8000/health`
- Verify `.env` has correct `VITE_BACKEND_URL`
- Rebuild extension: `pnpm wxt build`

**AI rewrite fails?**
- Check `backend/.env` has valid `ANTHROPIC_API_KEY`
- Check backend logs for errors
- Extension will fallback to deterministic mode if backend fails

**Rate limit hit?**
- Wait 1 minute and try again
- Adjust limits in `backend/main.py` if testing locally

---

## API Endpoints

**Health Check**: `GET /health`  
Response: `{"status": "healthy"}`

**Rewrite Resume**: `POST /api/rewrite`  
Request:
```json
{
  "draft": "BULLETS:\n- Bullet 1\n\nSKILLS:\nPython, React",
  "temperature": 0.2,
  "max_tokens": 700
}
```

Response:
```json
{
  "rewritten": "{\"bullets\": [...], \"skills\": [...]}"
}
```

Rate Limit: 10 requests/minute per IP

---

## Cost Estimates

**Anthropic Claude 3.5 Haiku**:
- ~$0.0004 per resume rewrite request
- 10 req/min max = $0.40/hour at full capacity
- Free tier hosting on Render/Railway covers moderate usage

**Recommended Budget Cap**: $10/month = ~25,000 rewrites

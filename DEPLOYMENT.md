# Resume Tailor - Deployment Guide

Complete guide for deploying the Resume Tailor Chrome extension with backend API for public use.

## Architecture Overview

```
┌─────────────────┐       ┌──────────────────┐       ┌──────────────────┐
│ Chrome          │       │ Backend API      │       │ Anthropic API    │
│ Extension       │──────▶│ (FastAPI)        │──────▶│ Claude 3.5 Haiku │
│ (WXT + React)   │       │ Rate Limiting    │       │                  │
└─────────────────┘       └──────────────────┘       └──────────────────┘
```

**Key Features:**
- **Frontend**: Chrome extension with React UI (client-side resume parsing + optional AI)
- **Backend**: Python FastAPI proxy with rate limiting (10 req/min per IP)
- **Security**: API key stored server-side, never exposed to users
- **Cost Control**: Rate limiting prevents abuse, customizable limits

---

## Part 1: Deploy Backend API

### Option A: Render (Recommended - Free Tier)

1. **Sign up**: https://render.com (free tier available)

2. **Create Web Service**:
   - Click "New +" → "Web Service"
   - Connect your GitHub repository
   - Select the `backend` directory

3. **Configure Build**:
   - **Name**: `resume-tailor-api` (or your preferred name)
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python main.py`

4. **Set Environment Variables**:
   - Go to "Environment" tab
   - Add: `ANTHROPIC_API_KEY` = `your_anthropic_api_key`
   - (Optional) Add: `PORT` = `8000` (Render usually auto-sets this)

5. **Deploy**:
   - Click "Create Web Service"
   - Wait 2-3 minutes for deployment
   - Copy your service URL (e.g., `https://resume-tailor-api.onrender.com`)

**Free Tier Limits**:
- Service sleeps after 15 mins of inactivity (first request takes ~30s to wake)
- 750 hours/month free (enough for moderate use)

---

### Option B: Railway (Alternative Free Tier)

1. **Sign up**: https://railway.app

2. **Create New Project**:
   - Click "New Project" → "Deploy from GitHub repo"
   - Select your repository
   - Railway auto-detects Python

3. **Configure**:
   - Select the `backend` directory
   - Add environment variable: `ANTHROPIC_API_KEY`

4. **Deploy**:
   - Railway auto-deploys
   - Copy your generated URL from the deployment

**Free Tier**: $5 credit/month (covers ~200K API requests)

---

### Option C: Fly.io (More Control)

```bash
# Install flyctl
brew install flyctl  # macOS
# or download from https://fly.io/docs/hands-on/install-flyctl/

# Login
flyctl auth login

# Navigate to backend folder
cd backend

# Launch app (follow prompts)
flyctl launch

# Set API key secret
flyctl secrets set ANTHROPIC_API_KEY=your_key_here

# Deploy
flyctl deploy
```

**Free Tier**: 3 shared VMs, 3GB persistent storage

---

## Part 2: Configure Extension for Production

### Step 1: Update Backend URL

1. **Copy environment template**:
   ```bash
   cd wxt-dev-wxt
   cp .env.example .env
   ```

2. **Edit `.env`** with your deployed backend URL:
   ```bash
   VITE_BACKEND_URL=https://your-backend.onrender.com
   ```

   Examples:
   - Render: `https://resume-tailor-api.onrender.com`
   - Railway: `https://resume-tailor-production.up.railway.app`
   - Fly.io: `https://resume-tailor.fly.dev`

### Step 2: Build Extension

```bash
cd wxt-dev-wxt
pnpm install  # if not already done
pnpm wxt build
```

Output folder: `.output/chrome-mv3/`

### Step 3: Test Locally

1. Open Chrome → `chrome://extensions/`
2. Enable "Developer mode" (top right)
3. Click "Load unpacked"
4. Select `.output/chrome-mv3/` folder
5. Test the extension with AI rewrite enabled

### Step 4: Package for Distribution

For Chrome Web Store publication:

```bash
pnpm wxt zip
```

Output: `.output/chrome-mv3.zip`

---

## Part 3: Chrome Web Store Publication

### Prerequisites

- Google Developer account ($5 one-time fee)
- Extension tested and working with production backend
- Privacy policy URL (required for extensions requesting permissions)

### Steps

1. **Go to**: https://chrome.google.com/webstore/devconsole

2. **Create New Item**:
   - Upload `.output/chrome-mv3.zip`

3. **Fill Store Listing**:
   - **Name**: Intern.ly
   - **Description**: 
     ```
     Tailor your resume for internship applications in seconds.
     
     Upload your master LaTeX resume, paste a job description, and get:
     - Relevant experience bullets ranked by JD keywords
     - Skills aligned with job requirements
     - Optional AI-powered phrasing improvements
     - Downloadable .tex and .pdf outputs
     
     Features:
     ✓ 100% local resume parsing (privacy-first)
     ✓ Free tier with rate-limited AI enhancements
     ✓ No hallucinated experience - only rewrites your actual content
     ✓ Template-preserving LaTeX export
     ```
   - **Category**: Productivity
   - **Language**: English
   - **Screenshots**: (Take 5 screenshots at 1280x800 or 640x400)
     1. Upload screen
     2. Job description input
     3. Generated output preview
     4. File download buttons
     5. Extension popup overview

4. **Privacy**:
   - **Single Purpose**: "Help students tailor resumes for internship applications"
   - **Permissions Justification**:
     - `storage`: Save user preferences and last output
     - Host permissions: Connect to backend API for optional AI features
   - **Data Usage**: "Resume content processed locally; only anonymized text sent to backend if AI rewrite enabled"

5. **Submit for Review**:
   - Initial review takes 3-7 days
   - Respond promptly to any reviewer questions

---

## Part 4: Rate Limiting & Cost Management

### Current Configuration

**Backend Rate Limits** (in `backend/main.py`):
```python
@limiter.limit("10/minute")  # 10 requests per minute per IP
async def rewrite_resume(request: Request, data: RewriteRequest):
```

### Adjust Rate Limits

Edit `backend/main.py` and change the decorator:

```python
# Examples:
@limiter.limit("50/hour")         # 50 requests per hour per IP
@limiter.limit("100/day")         # 100 requests per day per IP
@limiter.limit("5/minute;50/day") # Multiple limits (most restrictive wins)
```

Redeploy after changes:
```bash
git push  # If using Render/Railway auto-deploy
# OR
flyctl deploy  # If using Fly.io
```

### Cost Estimation

**Anthropic Claude 3.5 Haiku Pricing**:
- Input: ~$0.25 per 1M tokens
- Output: ~$1.25 per 1M tokens

**Typical Request**:
- Input: ~500 tokens (resume draft)
- Output: ~300 tokens (rewritten version)
- Cost per request: ~$0.0004

**Monthly Cost Examples**:
- 1,000 requests/month: ~$0.40
- 10,000 requests/month: ~$4
- 100,000 requests/month: ~$40

**Rate Limit Impact**:
- 10 req/min = 14,400 req/day max
- At full capacity: ~$172/month
- With 10% utilization: ~$17/month

### Budget Protection

Add daily budget cap in `backend/main.py`:

```python
import time
from collections import defaultdict

# Simple daily counter (for production, use Redis or database)
daily_counter = {"count": 0, "date": time.strftime("%Y-%m-%d")}
MAX_DAILY_REQUESTS = 1000  # Adjust based on your budget

@app.post("/api/rewrite")
@limiter.limit("10/minute")
async def rewrite_resume(request: Request, data: RewriteRequest):
    today = time.strftime("%Y-%m-%d")
    
    # Reset counter if new day
    if daily_counter["date"] != today:
        daily_counter["date"] = today
        daily_counter["count"] = 0
    
    # Check daily limit
    if daily_counter["count"] >= MAX_DAILY_REQUESTS:
        raise HTTPException(
            status_code=429,
            detail="Daily usage limit reached. Try again tomorrow."
        )
    
    daily_counter["count"] += 1
    # ... rest of function
```

---

## Part 5: Monitoring & Maintenance

### Backend Health Checks

**Monitor endpoint**: `https://your-backend.com/health`

Set up uptime monitoring (free options):
- **UptimeRobot**: https://uptimerobot.com
- **Pingdom**: https://www.pingdom.com
- **BetterStack**: https://betterstack.com

### Anthropic API Usage

Monitor usage at: https://console.anthropic.com

Recommended alerts:
- Daily spend > $5
- Rate limit warnings
- Error rate > 5%

### Logs

**Render**: Navigate to your service → "Logs" tab  
**Railway**: Project dashboard → "Deployments" → Click deployment → "View Logs"  
**Fly.io**: `flyctl logs` or web dashboard

Common issues to watch:
- `401 Unauthorized`: API key invalid/expired
- `429 Rate Limit`: Too many Anthropic API requests (upgrade tier or reduce usage)
- `504 Timeout`: Increase timeout in backend (>30s)

---

## Part 6: Scaling Options

### For Higher Traffic

1. **Upgrade Hosting**:
   - Render: $7/month for persistent instances (no cold starts)
   - Railway: Pay-as-you-go beyond free tier
   - Fly.io: Scale to multiple regions

2. **Add Caching**:
   - Cache identical requests (same resume + JD)
   - Use Redis for session management
   - Reduces API costs by 30-50%

3. **User Authentication** (optional):
   - Add user accounts
   - Track per-user limits
   - Offer paid tiers for higher limits

4. **Switch to Cheaper AI Models**:
   - Use Claude Haiku (already cheapest option)
   - Consider local models (slower, privacy-focused)
   - Batch processing for non-urgent requests

---

## Part 7: Privacy Policy (Required for Chrome Web Store)

Create a simple privacy policy page (host on GitHub Pages or your site):

```markdown
# Intern.ly Privacy Policy

Last Updated: [Date]

## Data Collection
- Resume content is processed locally in your browser
- When AI rewrite is enabled, anonymized resume text is sent to our backend API
- No personal information, names, or contact details are stored
- Job descriptions are not logged or retained

## Data Usage
- Resume text used only for AI-powered rewriting
- Requests rate-limited to prevent abuse
- No data sold or shared with third parties

## Data Storage
- Local browser storage: User preferences and last generated output
- Server storage: None (stateless API)

## Third-Party Services
- Anthropic Claude API: Processes resume text for rewriting (subject to Anthropic's privacy policy)

## Your Rights
- All data processing happens on-demand
- No account creation required
- Clear local data via browser's "Clear browsing data"

Contact: [Your Email]
```

Update extension listing with privacy policy URL.

---

## Part 8: Rollout Checklist

**Before Going Public**:

- [ ] Backend deployed and health check returns 200
- [ ] Extension built with production backend URL
- [ ] Tested AI rewrite with real resumes (5+ test cases)
- [ ] Rate limiting working (test with rapid requests)
- [ ] Error messages user-friendly
- [ ] Privacy policy published and linked
- [ ] Chrome Web Store listing complete with screenshots
- [ ] Monitoring/alerts configured
- [ ] Budget cap set (if needed)
- [ ] Backup plan for API key rotation

**Post-Launch**:

- [ ] Monitor logs for first 48 hours
- [ ] Track error rates
- [ ] Check Anthropic API usage daily for first week
- [ ] Gather user feedback
- [ ] Iterate on rate limits based on actual usage

---

## Troubleshooting

### Extension shows "Backend request failed: 403"
**Cause**: CORS issue or missing host permissions  
**Fix**: Check `wxt.config.ts` has correct `host_permissions`

### AI rewrite always fails
**Cause**: Backend not reachable or API key invalid  
**Fix**: 
1. Test backend health: `curl https://your-backend.com/health`
2. Verify API key in backend environment variables
3. Check backend logs for error details

### Rate limit errors too frequent
**Cause**: Limit too restrictive for user traffic  
**Fix**: Increase limit in `backend/main.py`:
```python
@limiter.limit("20/minute")  # Doubled limit
```

### Cold start delays on Render
**Cause**: Free tier spins down after inactivity  
**Fix**: Upgrade to paid tier ($7/month) or accept 30s delay for first request after idle

---

## Support & Updates

- **Backend Source**: `/backend/`
- **Extension Source**: `/wxt-dev-wxt/`
- **Issues**: File bugs via GitHub Issues (if using Git)
- **Updates**: Re-run `pnpm wxt build` and re-upload to Chrome Web Store

For backend updates:
```bash
git push  # Auto-deploys on Render/Railway
# OR
flyctl deploy  # Manual deploy on Fly.io
```

For extension updates:
```bash
pnpm wxt build
pnpm wxt zip
# Upload new .zip to Chrome Web Store → "Package" tab
```

---

## Quick Reference

**Backend Health**: `https://your-backend.com/health`  
**API Endpoint**: `https://your-backend.com/api/rewrite`  
**Extension Build**: `pnpm wxt build` (output: `.output/chrome-mv3/`)  
**Extension Zip**: `pnpm wxt zip` (output: `.output/chrome-mv3.zip`)  
**Anthropic Console**: https://console.anthropic.com  
**Chrome Web Store**: https://chrome.google.com/webstore/devconsole

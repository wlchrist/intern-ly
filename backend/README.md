# Resume Tailor Backend

FastAPI backend that proxies AI requests with rate limiting for the Resume Tailor Chrome extension.

## Features

- **Rate Limiting**: 10 requests per minute per IP address
- **Secure API Key Storage**: API key stored in environment variables, never exposed to clients
- **CORS Enabled**: Supports Chrome extension requests
- **Health Checks**: `/health` endpoint for monitoring
- **Error Handling**: Proper error messages and status codes

## Local Development

### Prerequisites

- Python 3.9+
- pip or uv

### Setup

1. **Create virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables**:
   ```bash
   cp .env.example .env
   # Edit .env and add your ANTHROPIC_API_KEY
   ```

4. **Run the server**:
   ```bash
   python main.py
   # Or use uvicorn directly:
   uvicorn main:app --reload --port 8000
   ```

5. **Test the API**:
   ```bash
   curl http://localhost:8000/health
   ```

## API Endpoints

### `GET /`
Health check endpoint.

**Response**:
```json
{"status": "ok", "service": "Resume Tailor API"}
```

### `GET /health`
Service health status.

**Response**:
```json
{"status": "healthy"}
```

### `POST /api/rewrite`
Rewrite resume draft using AI.

**Rate Limit**: 10 requests per minute per IP

**Request Body**:
```json
{
  "draft": "BULLETS:\n- Bullet 1\n- Bullet 2\n\nSKILLS:\nPython, JavaScript",
  "temperature": 0.2,
  "max_tokens": 700
}
```

**Response**:
```json
{
  "rewritten": "{\"bullets\": [...], \"skills\": [...]}"
}
```

**Error Responses**:
- `400`: Invalid request (missing draft)
- `429`: Rate limit exceeded
- `500`: API authentication failed or service error
- `504`: Request timeout

## Deployment

### Option 1: Render (Free Tier)

1. **Create account**: https://render.com
2. **Create new Web Service**:
   - Connect your GitHub repository
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python main.py`
3. **Set environment variables**:
   - `ANTHROPIC_API_KEY`: Your Anthropic API key
   - `PORT`: (Render sets this automatically)
4. **Deploy**: Render will auto-deploy from your repo

### Option 2: Railway (Free Tier)

1. **Create account**: https://railway.app
2. **Create new project** from GitHub repo
3. **Configure**:
   - Railway auto-detects Python projects
   - Add environment variable: `ANTHROPIC_API_KEY`
4. **Deploy**: Automatic deployment

### Option 3: Fly.io (Free Allowance)

1. **Install flyctl**: https://fly.io/docs/hands-on/install-flyctl/
2. **Login**: `flyctl auth login`
3. **Launch app**:
   ```bash
   flyctl launch
   ```
4. **Set secrets**:
   ```bash
   flyctl secrets set ANTHROPIC_API_KEY=your_key_here
   ```
5. **Deploy**:
   ```bash
   flyctl deploy
   ```

### Option 4: Local/VPS with Docker (Optional)

Create `Dockerfile`:
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["python", "main.py"]
```

Build and run:
```bash
docker build -t resume-tailor-backend .
docker run -p 8000:8000 -e ANTHROPIC_API_KEY=your_key resume-tailor-backend
```

## Production Configuration

After deployment, update your Chrome extension to use the backend URL:

1. Get your deployed URL (e.g., `https://resume-tailor-api.onrender.com`)
2. Update `wxt-dev-wxt/wxt.config.ts`:
   ```typescript
   host_permissions: ['https://your-backend-url.com/*']
   ```
3. Update `wxt-dev-wxt/entrypoints/popup/App.tsx`:
   ```typescript
   const BACKEND_URL = 'https://your-backend-url.com';
   ```
4. Rebuild extension: `pnpm wxt build`

## Rate Limits

Current configuration:
- **Per IP**: 10 requests/minute
- **Global**: Unlimited (adjust in production based on your Anthropic API budget)

To modify rate limits, edit `main.py`:
```python
@limiter.limit("10/minute")  # Change to "50/hour", "100/day", etc.
```

## Monitoring

- Check logs on your hosting platform
- Monitor Anthropic API usage at https://console.anthropic.com
- Set up alerts for high usage or errors

## Cost Considerations

- **Hosting**: Free tiers available on Render, Railway, Fly.io
- **Anthropic API**: Pay-per-use (~$0.25 per 1M input tokens for Haiku)
- **Rate Limiting**: Adjust limits based on your budget

Example cost calculation:
- Average request: ~500 tokens
- Cost per request: ~$0.000125
- 10 req/min = ~$0.07/hour = ~$50/month at full usage

Consider implementing:
- Daily/monthly budget caps
- User authentication for stricter limits
- Caching for repeated requests

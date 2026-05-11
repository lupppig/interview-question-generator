# Interview Question Generator

A simple web app that takes a job title and returns 3 thoughtful, role-specific interview questions using Google's Gemini API.

**Stack:** FastAPI (Python) backend + static HTML/CSS/JS frontend, deployed on Vercel.

## Local development

1. Create a virtual environment and install dependencies:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and add your [Gemini API key](https://ai.google.dev/):

   ```bash
   cp .env.example .env
   # then edit .env and set GEMINI_API_KEY
   ```

3. Run the server:

   ```bash
   GEMINI_API_KEY=$(grep GEMINI_API_KEY .env | cut -d= -f2) \
   uvicorn api.index:app --reload --port 8000
   ```

4. Open <http://localhost:8000>.

## Deploy to Vercel

1. Push this repo to GitHub.
2. Import the repo in the [Vercel dashboard](https://vercel.com/new).
3. In **Project Settings → Environment Variables**, add `GEMINI_API_KEY`.
4. Deploy. The `vercel.json` routes all traffic to the FastAPI function, which serves both the API and the static frontend.

## Project layout

```
api/index.py        FastAPI app: /api/generate endpoint + static file routes
public/             Frontend assets (index.html, styles.css, app.js)
requirements.txt    Python dependencies
vercel.json         Vercel build + routing config
```

## API

`POST /api/generate`

```json
{ "job_title": "Customer Success Manager" }
```

Response:

```json
{
  "job_title": "Customer Success Manager",
  "questions": ["...", "...", "..."]
}
```

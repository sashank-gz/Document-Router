# Document Router Platform

Intelligent document classification and routing for insurance PDFs. Upload documents, automatically classify them into 7 types, and route to the right extraction pipeline.

## Quick Start

### 1. Install Python dependencies

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Set up your environment

```bash
copy .env.example .env
```

Open `.env` and configure:

```env
# Pick your LLM provider (at least one must be enabled for AI classification)
GROQ_ENABLED=true
GROQ_API_KEY=your-groq-api-key-here

# Or use Gemini instead/as fallback
GEMINI_ENABLED=false
GEMINI_API_KEY=your-gemini-api-key-here
```

> **Tip:** Get a free Groq API key at [console.groq.com](https://console.groq.com)

### 3. Start the server

```bash
uvicorn app.main:app --reload
```

### 4. Open the app

Go to **http://127.0.0.1:8000** in your browser.

That's it — drag and drop PDF files to classify them.

---

## How Classification Works

Each uploaded document goes through a 3-tier classifier. The **first tier to match wins**:

| Tier | Method | Speed | Cost |
|---|---|---|---|
| 1 | Filename keywords (e.g. file named `loss_run.pdf`) | Instant | Free |
| 2 | Text keywords on page 1 (e.g. "claim number") | Instant | Free |
| 3 | AI/LLM classification (Groq or Gemini) | ~1-2 sec | Free tier |

If no tier matches → document goes to **Manual Review**.

## Document Types

| Type | Pipeline |
|---|---|
| Loss Run | OCR |
| Acord | OCR |
| Policy | LLM |
| Schedule of Insurance (SOI) | LLM |
| Schedule of Values (SOV) | LLM |
| Binder | LLM |
| Quote | LLM |

## Customizing (No Code Required)

All classification rules live in the `config/` folder as plain text files:

| What to change | File to edit |
|---|---|
| Add/remove document types | `config/routes.txt` |
| Change filename keywords | `config/filename_hints/<TYPE>.txt` |
| Change text keywords | `config/keyword_hints/<TYPE>.txt` |
| Change the AI prompt | `config/prompt.txt` |

See `config/README.txt` for detailed instructions.

## API Endpoints

| Method | URL | Description |
|---|---|---|
| `GET` | `/` | Frontend UI |
| `POST` | `/upload` | Upload and classify PDFs |
| `GET` | `/jobs` | List all jobs |
| `GET` | `/jobs/{id}` | Get one job |
| `GET` | `/health` | Health check |

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `GROQ_ENABLED` | `false` | Enable Groq LLM provider |
| `GROQ_API_KEY` | — | Your Groq API key |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Groq model |
| `GEMINI_ENABLED` | `false` | Enable Gemini LLM provider |
| `GEMINI_API_KEY` | — | Your Gemini API key |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model |
| `CLASSIFICATION_MAX_PAGES` | `3` | Pages to extract for LLM |
| `DEBUG_MODE` | `false` | Show extracted text and LLM responses in API output |
| `PIPELINE_DRY_RUN` | `false` | Skip actual pipeline calls (for testing) |
| `LLM_MAX_TEXT_CHARS` | `4000` | Max characters sent to LLM |
| `LLM_TEMPERATURE` | `0.0` | LLM creativity (0 = deterministic) |
| `LLM_MAX_TOKENS` | `150` | Max tokens LLM can return |
| `OCR_ENDPOINT` | `http://ocr-service/process` | OCR service URL |
| `LLM_ENDPOINT` | `http://llm-service/process` | LLM service URL |
| `PIPELINE_TIMEOUT` | `30` | Pipeline HTTP timeout (seconds) |

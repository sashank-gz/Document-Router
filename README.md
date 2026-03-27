# Document Router Platform

Intelligent document classification and routing for insurance PDFs. Upload documents, automatically classify them into 7 types, and route to the right extraction pipeline.

## Project Structure

```
document-router-platform/
├── app/                        # Core application package
│   ├── __init__.py             # HuggingFace env var setup
│   ├── main.py                 # FastAPI app, endpoints, startup
│   ├── config.py               # Centralized config (env + settings.txt)
│   ├── document_types.py       # Dynamic enum & config loading from config/
│   ├── classifier.py           # 3-tier classification orchestrator
│   ├── llm_classifier.py       # Tier 3 – Groq / Gemini LLM calls
│   ├── router_engine.py        # Save → Classify → Route → Track workflow
│   ├── extractor.py            # Docling-based text extraction (OCR + EasyOCR)
│   ├── file_service.py         # File I/O: save, extract, move
│   ├── pdf_utils.py            # PyMuPDF: rotation, traits, unlock
│   ├── pipeline_clients.py     # HTTP clients for OCR/LLM services
│   ├── models.py               # JobRecord model + SQLite JobStore
│   └── templates/
│       └── viewer.html         # File viewer HTML template
├── config/                     # User-editable rules (no code changes needed)
│   ├── routes.txt              # Document type → pipeline mapping
│   ├── settings.txt            # Tunable parameters (pages, confidence, etc.)
│   ├── prompt.txt              # LLM system prompt
│   ├── README.txt              # Config editing guide
│   ├── descriptions/           # One .txt per type (used in LLM prompt)
│   ├── filename_hints/         # One .txt per type (Tier 1 keywords)
│   └── keyword_hints/          # One .txt per type (Tier 2 keywords)
├── static/                     # Frontend UI
│   ├── index.html
│   ├── app.js
│   └── styles.css
├── tests/                      # Unit tests
│   ├── test_classifier.py
│   └── test_document_types.py
├── uploads/                    # Uploaded PDFs (gitignored)
├── processed/                  # Processed output files (gitignored)
├── .env.example                # Environment template (secrets only)
├── .gitignore
├── requirements.txt
└── README.md
```

## Quick Start

### 1. Install Python dependencies

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
```

### 2. Set up your environment

```bash
copy .env.example .env        # Windows
# cp .env.example .env        # macOS/Linux
```

Open `.env` and configure your LLM provider:

```env
GROQ_ENABLED=true
GROQ_API_KEY=your-groq-api-key-here

# Or use Gemini as fallback
GEMINI_ENABLED=false
GEMINI_API_KEY=your-gemini-api-key-here
```

> **Tip:** Get a free Groq API key at [console.groq.com](https://console.groq.com)

### 3. Start the server

```bash
uvicorn app.main:app --reload
```

### 4. Open the app

Go to **http://127.0.0.1:8000** — drag and drop PDF files to classify them.

---

## How Classification Works

Each uploaded document goes through a 3-tier classifier:

| Tier | Method | Speed | Cost |
|---|---|---|---|
| 1 | Filename keywords (e.g. file named `loss_run.pdf`) | Instant | Free |
| 2 | Text keywords on first pages (e.g. "claim number") | Instant | Free |
| 3 | AI/LLM classification (Groq or Gemini) | ~1-2 sec | Free tier |

**Decision logic:**
- Tier 2 is the primary classifier
- Tier 1 alone does NOT classify — it only detects conflicts
- If Tier 1 and Tier 2 disagree, Tier 3 (LLM) breaks the tie
- If no tier matches → document goes to **Manual Review**

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

## Configuration

### Secrets (`.env`)

API keys and provider toggles — see `.env.example`.

### Tunable Settings (`config/settings.txt`)

All behavioral parameters can be adjusted without touching code or `.env`:

| Setting | Default | Purpose |
|---|---|---|
| `KEYWORD_SCAN_MAX_PAGES` | 3 | Pages to scan for keyword classification |
| `LLM_SCAN_MAX_PAGES` | 3 | Pages to extract for LLM context |
| `LLM_MAX_TEXT_CHARS` | 4000 | Max chars sent to LLM |
| `LLM_TEMPERATURE` | 0.0 | LLM creativity (0 = deterministic) |
| `CONFIDENCE_FILENAME` | 0.7 | Confidence for filename matches |
| `CONFIDENCE_KEYWORD` | 0.9 | Confidence for keyword matches |
| `PIPELINE_TIMEOUT` | 30 | Pipeline HTTP timeout (seconds) |
| `ENABLE_PDF_TRAITS` | true | Analyze PDFs for traits (Scanned, etc.) |
| `DOCLING_SAVE_MD` | true | Save Markdown extraction output |
| `DOCLING_SAVE_JSON` | true | Save JSON extraction output |

### Classification Rules (`config/`)

All rules are plain text files — no code changes needed:

| What to change | File to edit |
|---|---|
| Add/remove document types | `config/routes.txt` |
| Change filename keywords | `config/filename_hints/<TYPE>.txt` |
| Change text keywords | `config/keyword_hints/<TYPE>.txt` |
| Change the AI prompt | `config/prompt.txt` |
| Add type descriptions (for LLM) | `config/descriptions/<TYPE>.txt` |

See `config/README.txt` for detailed instructions.

## API Endpoints

| Method | URL | Description |
|---|---|---|
| `GET` | `/` | Frontend UI |
| `POST` | `/upload` | Upload and classify PDFs |
| `GET` | `/jobs` | List all jobs |
| `GET` | `/jobs/{id}` | Get one job |
| `GET` | `/jobs/{id}/logs` | Streaming terminal logs for a job |
| `POST` | `/jobs/{id}/unlock` | Unlock a password-protected PDF |
| `GET` | `/view/{filename}` | View processed file (MD/JSON/HTML) |
| `GET` | `/health` | Health check |

## Testing

```bash
# Install test dependencies
pip install pytest

# Run all tests
python -m pytest tests/ -v
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `GROQ_ENABLED` | `false` | Enable Groq LLM provider |
| `GROQ_API_KEY` | — | Your Groq API key |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Groq model |
| `GEMINI_ENABLED` | `false` | Enable Gemini LLM provider |
| `GEMINI_API_KEY` | — | Your Gemini API key |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model |
| `DEBUG_MODE` | `false` | Show debug info in API output |
| `PIPELINE_DRY_RUN` | `false` | Skip pipeline calls (testing) |
| `OCR_ENDPOINT` | `http://ocr-service/process` | OCR service URL |
| `LLM_ENDPOINT` | `http://llm-service/process` | LLM service URL |
| `OCR_UI_URL` | `http://localhost:3001` | OCR service UI link |
| `LLM_UI_URL` | `http://localhost:8080` | LLM service UI link |

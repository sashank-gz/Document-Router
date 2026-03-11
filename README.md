# Document-Router-Platform

Document-Router-Platform is a FastAPI service that receives uploaded PDFs, classifies each document into one of seven insurance document types, and routes it to the best extraction pipeline:

- **OCR pipeline** — Loss Runs, Acord forms
- **LLM pipeline** — Policies, SOI, SOV, Binders, Quotes
- **Manual review** — unknown / unclassified documents

## Architecture

```text
document-router-platform/
├── app/
│   ├── main.py                # FastAPI app and API routes
│   ├── router_engine.py       # Core routing workflow
│   ├── classifier.py          # 3-tier classification orchestrator
│   ├── llm_classifier.py      # Tier 3 – LLM classification (Groq / Gemini)
│   ├── document_types.py      # Document type enum and route mapping
│   ├── config.py              # Env-driven configuration
│   ├── pipeline_clients.py    # OCR/LLM HTTP clients
│   ├── file_service.py        # File save/move + PDF text extraction
│   └── models.py              # SQLite job model/store
├── uploads/                   # Incoming files
├── processed/                 # Routed files after processing
├── .env.example               # Environment variable template
├── requirements.txt
└── README.md
```

## Document Types and Routes

| Document Type | Pipeline |
|---|---|
| Loss Run | OCR |
| Acord | OCR |
| Policy | LLM |
| Schedule of Insurance (SOI) | LLM |
| Schedule of Values (SOV) | LLM |
| Binder | LLM |
| Quote | LLM |
| Unknown | Manual Review |

## Classification — 3-Tier Fallback

Each uploaded document is classified using a tiered approach. The first tier to match wins:

| Tier | Method | Details |
|---|---|---|
| 1 | **Filename keywords** | Checks if the filename contains known keywords (e.g. `loss`, `acord`, `policy`, `soi`, `binder`, `quote`) |
| 2 | **First-page text keywords** | Extracts text from page 1 and looks for domain-specific phrases (e.g. `claim number`, `certificate of insurance`, `schedule of values`) |
| 3 | **LLM classification** | Extracts text from up to 3 pages and sends it to Groq or Gemini to classify |

If no tier matches → document is routed to **Manual Review**.

## Getting Started

### 1. Create and activate a virtual environment

```bash
python -m venv .venv
.venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
copy .env.example .env
```

Open `.env` and set your LLM provider:

```env
# Enable Groq (set to false to disable)
GROQ_ENABLED=true
GROQ_API_KEY=your-groq-api-key-here
GROQ_MODEL=llama-3.3-70b-versatile

# Enable Gemini (set to false to disable)
GEMINI_ENABLED=false
GEMINI_API_KEY=your-gemini-api-key-here
GEMINI_MODEL=gemini-2.5-flash
```

> If both providers are enabled, Groq is tried first and Gemini is used as a fallback.  
> If neither is enabled, Tier 3 (LLM classification) is skipped and unrecognized documents go to Manual Review.

### 4. Start the server

```bash
uvicorn app.main:app --reload
```

From project root: `document-router-platform/`

## Routing Logic

For each uploaded file:

1. Save file to `uploads/`
2. Extract text from the PDF
3. Classify document using the 3-tier pipeline
4. Route to OCR, LLM, or Manual based on the classification
5. Track job status in SQLite (`jobs.db`)
6. Move processed file to `processed/`

## Job Tracking

SQLite table: `jobs`

Columns:
- `id`
- `file_name`
- `route`
- `status`
- `created_at`

Status values used by the app:
- `UPLOADED`
- `CLASSIFIED`
- `ROUTED`
- `PROCESSING`
- `COMPLETED`
- `FAILED`

## API Endpoints

- `POST /upload` - Upload one or more PDFs and process routing
- `GET /jobs` - List all jobs
- `GET /jobs/{id}` - Get one job
- `GET /health` - Health check

## Example cURL Requests

Health:

```bash
curl -X GET http://127.0.0.1:8000/health
```

Batch upload:

```bash
curl -X POST "http://127.0.0.1:8000/upload" \
  -F "files=@sample1.pdf" \
  -F "files=@sample2.pdf"
```

List jobs:

```bash
curl -X GET http://127.0.0.1:8000/jobs
```

Get one job:

```bash
curl -X GET http://127.0.0.1:8000/jobs/1
```

## Environment Variables Reference

| Variable | Default | Description |
|---|---|---|
| `GROQ_ENABLED` | `false` | Enable Groq as an LLM classification provider |
| `GROQ_API_KEY` | — | Your Groq API key |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Groq model to use |
| `GEMINI_ENABLED` | `false` | Enable Gemini as an LLM classification provider |
| `GEMINI_API_KEY` | — | Your Google Gemini API key |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model to use |
| `CLASSIFICATION_MAX_PAGES` | `3` | Number of pages to extract for LLM classification |
| `OCR_ENDPOINT` | `http://ocr-service/process` | OCR pipeline service URL |
| `LLM_ENDPOINT` | `http://llm-service/process` | LLM pipeline service URL |
| `PIPELINE_TIMEOUT` | `30` | HTTP timeout in seconds for pipeline calls |

## Notes for Production

- Pipeline URLs (`OCR_ENDPOINT`, `LLM_ENDPOINT`) should be pointed to real services.
- Add retry/backoff and circuit breaker behavior for pipeline calls.
- Add authn/authz and request size limits.
- Add async queue processing (Celery/RQ/Kafka) for very large batches.

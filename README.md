# CONTINUUM Agentic AI

> **An autonomous, multimodal life-logging and auto-publishing research platform powered by Google Gemini.**

---

## Overview

CONTINUUM is a fully autonomous agentic AI system designed to ingest raw personal media and communications, synthesise them into polished narratives, and publish structured content to the web — all without human intervention.

It is simultaneously a **production publishing engine** and a **research platform** for studying the efficacy of LLM-driven autonomous content creation at scale.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    CONTINUUM Pipeline                           │
│                                                                 │
│  Google Photos ──► GeminiBrain (Vision) ──► WordPress Posts    │
│                                                                 │
│  Gmail          ──► GeminiBrain (Text)  ──► Research Logs      │
│                                                                 │
│  system_memory.json ◄──────────────────── ResearchLogger       │
└─────────────────────────────────────────────────────────────────┘
```

### Core Modules

| Module | File | Responsibility |
|---|---|---|
| **GooglePhotosClient** | `src/google_photos_client.py` | OAuth2 access to Google Photos; incremental media fetching |
| **GmailBookingClient** | `src/gmail_booking_client.py` | Gmail API; booking confirmation extraction |
| **GeminiBrain** | `src/gemini_brain.py` | Gemini 1.5 Pro multimodal processing; JSON extraction |
| **WordPressPublisher** | `src/wordpress_publisher.py` | WordPress REST API; post creation, media upload |
| **ResearchLogger** | `src/research_logger.py` | JSONL event logging; system memory management |

---

## Quick Start

### 1. Clone & Set Up Environment

```bash
git clone https://github.com/YOUR_USERNAME/CONTINUUM-Agentic-AI.git
cd CONTINUUM-Agentic-AI
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Secrets

Copy the example and fill in your credentials:

```bash
cp .env.example .env
```

Required environment variables (see `config/settings.py`):

| Variable | Description |
|---|---|
| `GEMINI_API_KEY` | Google AI Studio API key |
| `WP_URL` | Your WordPress site URL (e.g., `https://example.com`) |
| `WP_USER` | WordPress username |
| `WP_APP_PASSWORD` | WordPress Application Password (Settings → Users) |
| `GOOGLE_PHOTOS_REFRESH_TOKEN` | OAuth2 refresh token for Google Photos |
| `GOOGLE_CLIENT_ID` | Google OAuth2 Client ID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth2 Client Secret |
| `GMAIL_REFRESH_TOKEN` | OAuth2 refresh token for Gmail (optional) |

### 3. Run the Pipeline

```bash
python main.py
```

---

## Automated Scheduling (GitHub Actions)

The pipeline runs automatically every 6 hours via `.github/workflows/continuum_cron.yml`.

Add all environment variables as **Repository Secrets** under:
`Settings → Secrets and variables → Actions`

---

## System Memory

CONTINUUM tracks its state in `data/system_memory.json` to support **incremental processing** — only media items and emails newer than the last run are processed. This prevents duplicate posts and redundant API calls.

---

## Research Logs

All pipeline events are logged as JSONL entries in `research_logs/YYYY-MM-DD.jsonl`. A Gemini-powered research summary is generated every 7 pipeline sessions and included in the log.

Log event types:
- `photo_processed` — A Google Photos item was analysed
- `post_published` — A WordPress post was created
- `booking_parsed` — A Gmail booking email was extracted
- `research_summary_generated` — Weekly analytics summary
- `pipeline_error` — Unhandled exception in the pipeline

---

## Project Structure

```
continuum-agentic-ai/
├── .github/workflows/continuum_cron.yml   # Scheduled GitHub Actions trigger
├── config/
│   ├── settings.py                        # Environment variable loader
│   └── system_prompts.py                  # All Gemini prompt templates
├── src/
│   ├── google_photos_client.py            # Google Photos API module
│   ├── gmail_booking_client.py            # Gmail booking parser
│   ├── gemini_brain.py                    # Gemini multimodal engine
│   ├── wordpress_publisher.py             # WordPress REST API client
│   └── research_logger.py                 # Metrics logger & state manager
├── data/system_memory.json                # Persistent pipeline state
├── research_logs/                         # JSONL event logs (gitignored)
├── main.py                                # Master orchestration script
├── requirements.txt                       # Python dependencies
└── README.md                              # This file
```

---

## Technology Stack

- **AI Engine**: Google Gemini 1.5 Pro (multimodal text + vision)
- **Data Sources**: Google Photos Library API, Gmail API
- **Publishing**: WordPress REST API with Application Passwords
- **Auth**: Google OAuth2 with automatic token refresh
- **Scheduling**: GitHub Actions (cron)
- **Retry Logic**: `tenacity` with exponential back-off
- **Logging**: `rich` for beautiful terminal output + JSONL for structured research logs

---

## Research Context

CONTINUUM is being developed as part of an ongoing independent research study into:

1. **Autonomous Content Velocity**: Can an AI agent maintain a consistent, high-quality publishing cadence without human editorial input?
2. **Multimodal Narrative Synthesis**: How accurately does Gemini Vision reconstruct personal narratives from raw photo metadata + visual context?
3. **Logistics Intelligence**: What is the precision rate of LLM-based extraction of structured booking data from unstructured email text?

Research findings and publication metrics are logged automatically and analysed weekly by the CONTINUUM research summary module.

---

## License

MIT License. See `LICENSE` for details.

---

*Built with ❤️ and autonomous ambition by the CONTINUUM research project.*

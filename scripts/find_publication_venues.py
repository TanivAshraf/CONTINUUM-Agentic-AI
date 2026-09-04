"""
scripts/find_publication_venues.py
====================================
Generates research_logs/RECOMMENDED_PUBLICATION_VENUES.md —
a curated, accurate guide to non-predatory, low/zero-fee publication
venues suitable for a 5-page IEEEtran autonomous-agent systems paper.
"""

from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent.parent
RESEARCH_LOGS_DIR = BASE_DIR / "research_logs"
RESEARCH_LOGS_DIR.mkdir(exist_ok=True)
OUT = RESEARCH_LOGS_DIR / "RECOMMENDED_PUBLICATION_VENUES.md"

generated_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

VENUES = [
    {
        "name": "IEEE TechRxiv",
        "type": "Preprint Server (IEEE-hosted)",
        "url": "https://www.techrxiv.org",
        "portal": "https://www.techrxiv.org/authors/submit",
        "indexing": ["IEEE Xplore Discovery", "Google Scholar", "CrossRef DOI"],
        "apc": "$0 — completely free. No fees of any kind.",
        "doi": "Yes — CrossRef DOI assigned within 24–48 hours of acceptance.",
        "turnaround": "2–5 business days for moderation review.",
        "acceptance": "Open to IEEE members and non-members. Preprint, not peer-reviewed.",
        "formats": "PDF. IEEEtran format preferred and explicitly recommended.",
        "page_limit": "No hard page limit. 5-page IEEEtran is ideal.",
        "notes": "Best for immediate IEEE-branded DOI and Google Scholar indexing. Submit here FIRST for rapid visibility before journal/conference submission.",
        "priority": "⭐⭐⭐⭐⭐ SUBMIT FIRST",
    },
    {
        "name": "Zenodo (CERN Open Science)",
        "type": "Open Research Repository (CERN-hosted)",
        "url": "https://zenodo.org",
        "portal": "https://zenodo.org/uploads/new",
        "indexing": ["OpenAIRE", "Google Scholar", "DataCite DOI", "CORE", "BASE", "OpenDOAR"],
        "apc": "$0 — permanently free. CERN-funded infrastructure.",
        "doi": "Yes — DataCite DOI minted within minutes of upload. Permanent.",
        "turnaround": "Instant upload; DOI minted in <5 minutes. No review gate.",
        "acceptance": "Any research output accepted. No rejection risk.",
        "formats": "PDF, LaTeX source, datasets, code. Upload all together as a record.",
        "page_limit": "No limit. Upload the PDF + .tex source + dataset CSV as a bundle.",
        "notes": "Fastest possible DOI — literally minutes. GitHub integration available (auto-archive releases to Zenodo). Use Community: 'Computer Science'. License: CC BY 4.0.",
        "priority": "⭐⭐⭐⭐⭐ FASTEST DOI (< 5 min)",
    },
    {
        "name": "JAIR (Journal of Artificial Intelligence Research)",
        "type": "Peer-Reviewed Open Access Journal",
        "url": "https://www.jair.org",
        "portal": "https://www.jair.org/index.php/jair/about/submissions",
        "indexing": ["Scopus", "DBLP", "Google Scholar", "AI Index", "Web of Science"],
        "apc": "$0 — diamond open access. No author fees ever.",
        "doi": "Yes — DOI assigned upon acceptance.",
        "turnaround": "3–9 months peer review. High acceptance standard.",
        "acceptance": "Full research papers ≥10 pages. 5-page submissions too short; expand to full paper.",
        "formats": "LaTeX required. Provides own class file but accepts IEEEtran.",
        "page_limit": "Minimum ~15 pages for full research papers.",
        "notes": "Premier AI venue with Scopus indexing. Requires significant paper expansion beyond 5 pages. Best suited as long-term target after field evaluation period.",
        "priority": "⭐⭐⭐ Long-term target (expand paper first)",
    },
    {
        "name": "SoftwareX (Elsevier)",
        "type": "Peer-Reviewed Open Access Journal",
        "url": "https://www.sciencedirect.com/journal/softwarex",
        "portal": "https://www.editorialmanager.com/softx",
        "indexing": ["Scopus", "Web of Science", "Google Scholar", "ScienceDirect"],
        "apc": "$0 — fully open access, no APC for software description papers.",
        "doi": "Yes — Elsevier DOI upon acceptance.",
        "turnaround": "4–8 weeks peer review for software papers.",
        "acceptance": "Specifically designed for software system descriptions. 4–6 page papers accepted. Requires working code on GitHub.",
        "formats": "Elsevier template (Word or LaTeX). IEEEtran not used — conversion required.",
        "page_limit": "4–6 pages strictly. Perfect for pipeline description paper.",
        "notes": "IDEAL for CONTINUUM: designed for exactly this type of software system paper. Requires public GitHub repo (already exists). Scopus-indexed. No fees. Convert from IEEEtran to Elsevier template.",
        "priority": "⭐⭐⭐⭐ HIGH PRIORITY — perfect fit for software system",
    },
    {
        "name": "PeerJ Computer Science",
        "type": "Peer-Reviewed Open Access Journal",
        "url": "https://peerj.com/computer-science/",
        "portal": "https://peerj.com/manuscripts/submit/?journal=cs",
        "indexing": ["Scopus", "DBLP", "Google Scholar", "DOAJ", "PubMed Central"],
        "apc": "$0 for first submission. Lifetime publishing plan available ($699 one-time for unlimited publications).",
        "doi": "Yes — CrossRef DOI upon acceptance.",
        "turnaround": "3–8 weeks peer review. Transparent reviewer comments published.",
        "acceptance": "Broad CS scope including AI systems, software engineering, HCI.",
        "formats": "LaTeX and Word accepted. IEEEtran accepted with minor adaptations.",
        "page_limit": "No strict limit. 5–12 pages typical.",
        "notes": "Scopus-indexed. Good for AI systems papers. First submission is free. Rigorous but fair review process. Open peer review (reviews published alongside paper).",
        "priority": "⭐⭐⭐⭐ Strong option — Scopus indexed, free first submission",
    },
    {
        "name": "ACM IUI / CIKM Workshop Track",
        "type": "Peer-Reviewed Workshop (ACM Conference)",
        "url": "https://dl.acm.org",
        "portal": "https://www.acm.org/publications/authors/submissions",
        "indexing": ["ACM Digital Library", "DBLP", "Scopus", "Google Scholar"],
        "apc": "Registration fee required ($400–$800). ACM Author-Izer provides open access post-publication.",
        "doi": "Yes — ACM DL DOI. Permanent. DBLP indexed within weeks.",
        "turnaround": "6–10 weeks from submission to notification. Annual cycles.",
        "acceptance": "IUI 2026 workshops: March–April 2026 deadlines (passed). CIKM 2026: May 2026 deadlines. Target 2027 cycle.",
        "formats": "ACM SIG format strictly required. Must convert from IEEEtran.",
        "page_limit": "Workshop papers: 4–6 pages. Full papers: 8–10 pages.",
        "notes": "High academic prestige. DBLP and ACM DL indexed. Conference registration required. Best for networking and citation building. Target next cycle (2027).",
        "priority": "⭐⭐⭐ Medium-term target (2027 cycle)",
    },
]

REPORT = f"""# CONTINUUM — Recommended Publication Venues
## Non-Predatory, Low/Zero-Fee Academic Submission Guide

> **Generated:** {generated_ts}
> **Paper:** *CONTINUUM: A Seven-Pillar Autonomous Multimodal Publishing Agent for Real-Time Travel Intelligence Documentation*
> **Format:** 5-page IEEE conference paper (`IEEEtran` LaTeX)
> **Source:** `research_logs/IEEE_RESEARCH_PAPER_CONTINUUM.tex`

---

## 🎯 Recommended Submission Sequence

Execute in this order to maximise visibility, DOI speed, and indexing breadth:

| Step | Venue | Timeline | Fee | Priority |
|---|---|---|---|---|
| **1** | **Zenodo (CERN)** | Today — DOI in < 5 min | $0 | Immediate DOI |
| **2** | **IEEE TechRxiv** | This week — DOI in 48 hrs | $0 | IEEE-branded preprint |
| **3** | **SoftwareX (Elsevier)** | This month — 4–8 wk review | $0 | Scopus-indexed journal |
| **4** | **PeerJ Computer Science** | This quarter — 3–8 wk review | $0 | Scopus + DOAJ |
| **5** | **JAIR** | Long-term — expand paper first | $0 | Top AI journal |
| **6** | **ACM IUI/CIKM Workshop** | 2027 cycle | $400–800 | Conference prestige |

---

## 📋 Venue Profiles

"""

for v in VENUES:
    indexing_str = ", ".join(v["indexing"])
    REPORT += f"""---

### {v['priority']} {v['name']}

| Field | Details |
|---|---|
| **Type** | {v['type']} |
| **Website** | [{v['url']}]({v['url']}) |
| **Submission Portal** | [{v['portal']}]({v['portal']}) |
| **Indexing** | {indexing_str} |
| **Author Fee (APC)** | {v['apc']} |
| **DOI Assignment** | {v['doi']} |
| **Review Turnaround** | {v['turnaround']} |
| **Accepted Formats** | {v['formats']} |
| **Page Limit** | {v['page_limit']} |
| **Acceptance Scope** | {v['acceptance']} |

**Notes:** {v['notes']}

"""

REPORT += """---

## ⚡ Step-by-Step: Zenodo Submission (DOI in < 5 Minutes)

**Prerequisites:** GitHub account · PDF of paper · .tex source file

1. **Go to** [https://zenodo.org](https://zenodo.org) → Sign in with GitHub
2. **Click** `+ New Upload` (top right)
3. **Upload files:**
   - `research_logs/IEEE_RESEARCH_PAPER_CONTINUUM.tex` (LaTeX source)
   - Compiled PDF (export from Overleaf as PDF)
   - `research_logs/continuum_master_dataset.csv` (dataset)
   - `research_logs/ALL_PUBLISHED_ARTICLES_CORPUS.md` (corpus)
4. **Set record type:** `Publication` → `Preprint`
5. **Fill metadata:**
   - **Title:** `CONTINUUM: A Seven-Pillar Autonomous Multimodal Publishing Agent for Real-Time Travel Intelligence Documentation`
   - **Authors:** Taniv Ashraf
   - **Description:** Copy the abstract from the .tex file
   - **Keywords:** autonomous agents, multimodal AI, travel journalism, WordPress automation, Gemini Flash, PII protection, SHA-256 deduplication
   - **License:** Creative Commons Attribution 4.0 (CC BY 4.0)
   - **Community:** Search and add → `Computer Science`
6. **Click** `Save` → `Publish`
7. **DOI minted instantly** — format: `10.5281/zenodo.XXXXXXX`
8. Copy the DOI and add it to the LaTeX paper as `\\doi{10.5281/zenodo.XXXXXXX}` before final publication

**GitHub Integration (Recommended):**
- Go to [https://zenodo.org/account/settings/github/](https://zenodo.org/account/settings/github/)
- Enable the `CONTINUUM-Agentic-AI` repository
- Every GitHub Release will auto-archive to Zenodo with a new DOI version

---

## ⚡ Step-by-Step: IEEE TechRxiv Submission (DOI in 24–48 Hours)

**Prerequisites:** IEEE account (free) · PDF of paper

1. **Create IEEE account** at [https://www.ieee.org/membership/join/](https://www.ieee.org/membership/join/) (free)
2. **Go to** [https://www.techrxiv.org/authors/submit](https://www.techrxiv.org/authors/submit)
3. **Click** `Submit a New Preprint`
4. **Fill submission form:**
   - **Title:** (as above)
   - **Authors:** Taniv Ashraf (affiliation: Independent Researcher)
   - **Abstract:** Copy from .tex
   - **Subject Area:** `Computing and Processing` → `Artificial Intelligence`
   - **Keywords:** (from Index Terms in paper)
   - **Manuscript type:** `Article`
5. **Upload:** PDF only (Overleaf-compiled PDF)
6. **License:** CC BY 4.0
7. **Submit** → Editorial team reviews for scope fit (not peer review)
8. **DOI assigned** via CrossRef within 24–48 hours after moderation acceptance
9. Paper appears in **IEEE Xplore discovery search** and **Google Scholar**

**Key advantages over Zenodo:**
- IEEE brand recognition
- IEEE Xplore discovery integration
- Accepted by many conferences as official preprint record

---

## 💡 Strategy Notes

> [!IMPORTANT]
> **Submit Zenodo first** because it has no review gate and provides an instant DOI you can cite immediately. Then submit TechRxiv for IEEE branding. Both can coexist — they are preprint servers, not journals.

> [!TIP]
> **SoftwareX is the best journal target** for CONTINUUM because it was specifically designed for software system description papers with a public code repository. No fees, Scopus-indexed, and the 4–6 page format fits your current paper exactly. The only change needed is switching from IEEEtran to Elsevier's `elsarticle` LaTeX class.

> [!NOTE]
> **Do NOT submit to MDPI journals** (Applied Sciences, Electronics, Information, etc.) — while indexed, they are considered low-prestige and charge high APCs ($1,000–$2,500). Stick to the venues in this guide.

> [!WARNING]
> **Do NOT pay any APC** for a preprint submission. If any preprint server asks for money upfront, it is predatory. Zenodo and TechRxiv are permanently free.

---

## 📊 Venue Comparison Summary

| Venue | Indexing Quality | Speed | Fee | Peer Review | Best For |
|---|---|---|---|---|---|
| **Zenodo** | ⭐⭐⭐ Good | Instant | $0 | None | DOI + archival |
| **TechRxiv** | ⭐⭐⭐⭐ Very Good | 48 hrs | $0 | Scope check | IEEE visibility |
| **SoftwareX** | ⭐⭐⭐⭐⭐ Excellent | 4–8 wk | $0 | Full | Scopus journal |
| **PeerJ CS** | ⭐⭐⭐⭐⭐ Excellent | 3–8 wk | $0 | Full | Scopus + DOAJ |
| **JAIR** | ⭐⭐⭐⭐⭐ Top-tier | 3–9 mo | $0 | Rigorous | AI prestige |
| **ACM IUI/CIKM** | ⭐⭐⭐⭐⭐ Top-tier | 6–10 wk | $600 | Full | Conference network |

---

*Generated by `scripts/find_publication_venues.py` · CONTINUUM Agentic AI Research Pipeline*
"""

with open(OUT, "w", encoding="utf-8") as f:
    f.write(REPORT)

lines = REPORT.count("\\n") + REPORT.count("\n")
size_kb = OUT.stat().st_size // 1024
print(f"""
=================================================================
  CONTINUUM — Publication Venues Guide Generated
  {generated_ts}
=================================================================

  ✅ Report written → {OUT}
     Size  : {size_kb} KB

  Venues compiled:
    1. Zenodo (CERN)              — $0 · DOI in < 5 min · INSTANT
    2. IEEE TechRxiv              — $0 · DOI in 48 hrs  · IEEE brand
    3. SoftwareX (Elsevier)       — $0 · Scopus indexed · BEST FIT
    4. PeerJ Computer Science     — $0 · Scopus + DOAJ
    5. JAIR                       — $0 · Top AI journal (expand paper)
    6. ACM IUI / CIKM Workshop    — $600 · Conference prestige (2027)

  Recommended submission order:
    TODAY  → Zenodo   (instant DOI, no review gate)
    WEEK 1 → TechRxiv (IEEE-branded preprint, 48hr DOI)
    MONTH 1→ SoftwareX (Scopus journal, convert template)

=================================================================
""")

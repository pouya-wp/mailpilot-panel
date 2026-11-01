<div align="center">

# 📬 MailPilot Panel

### Smart AI Campaigns & Autonomous Email Marketing Agent Platform

[![Platform](https://img.shields.io/badge/Platform-Web%20%7C%20Cloud-24292E?style=flat-square&logo=googlecloud)](https://cloud.google.com)
[![React](https://img.shields.io/badge/Frontend-React%20%2B%20Vite-61DAFB?style=flat-square&logo=react)](https://react.dev/)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI%20(Python)-009688?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-blue?style=flat-square)](LICENSE)
[![Author](https://img.shields.io/badge/Author-Pouya%20Sadeghpour-181717?style=flat-square&logo=github)](https://github.com/pouya-wp)

<p align="center">
  <b>MailPilot Panel</b> is an enterprise-grade AI email marketing command center. It orchestrates intelligent outbound campaigns with dynamic recipient personalization, multi-variant A/B subject testing, pre-send SPF/DKIM health auditing, and autonomous AI reply drafting.
</p>

</div>

---

## ✨ Features

- 🤖 **Autonomous AI Copywriter** — Generates context-aware, hyper-personalized email variants tailored to individual prospect industry and role.
- 🧪 **Multi-Variant A/B Decision Engine** — Automated sample delivery with early statistical significance gates before full campaign dispatch.
- 🩺 **Sender Health & Pre-Flight Gate** — Real-time SPF, DKIM, DMARC, and domain reputation scoring prior to send approval.
- 📬 **Two-Way Gmail & SMTP Sync** — Seamless OAuth2 Gmail synchronization and reply detection with sentiment tagging.
- 📈 **Real-Time Funnel Analytics** — Live telemetry on opens, clicks, bounces, and reply conversions.

---

## 🏗️ Architecture

```
MailPilot Architecture
├── Frontend (React 18 + Vite + Tailwind CSS)
│    ├── Campaign Wizard & A/B Matrix Builder
│    ├── Sender Reputation & DNS Diagnostic Dashboard
│    └── Unified Inbox & AI Reply Assistant
└── Backend (FastAPI + Python 3.11 + SQLite / SQLAlchemy)
     ├── Gmail OAuth2 & IMAP/SMTP Pipeline
     ├── Task Scheduler (Async background sending & pacing)
     └── LLM Personalization & Reply Classification Service
```

| Layer | Technologies | Responsibility |
|:---|:---|:---|
| **Frontend** | React, Vite, Tailwind CSS, Lucide | Interactive dashboards, campaign wizard, analytics charts |
| **Backend** | Python 3.11, FastAPI, SQLAlchemy | REST API, OAuth2 session manager, dispatch queue |
| **Integrations** | Google Workspace, OpenAI, Traefik | Email transport, reverse proxy, SSL termination |

---

## 🚀 Quick Start

### Prerequisites
- Node.js 20+
- Python 3.11+
- Git

### Frontend Setup

```bash
# Clone the repository
git clone https://github.com/pouya-wp/mailpilot-panel.git
cd mailpilot-panel

# Install and launch frontend
npm install
npm run dev
```

### Backend Setup

```bash
cd backend
python -m venv .venv
# On Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

---

## 📄 License

Distributed under the MIT License.

---

<div align="center">
  <sub>Crafted with precision & passion by <b><a href="https://github.com/pouya-wp">Pouya Sadeghpour</a></b></sub>
</div>

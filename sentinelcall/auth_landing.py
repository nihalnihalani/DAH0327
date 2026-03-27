"""Page0 Auth0 Landing Page — production-grade SaaS login experience.

Serves a visually polished landing/login page at /auth with Auth0 CIBA
branding, dark/light mode toggle, and professional hero + feature sections.
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from sentinelcall.config import AUTH0_DOMAIN, AUTH0_CLIENT_ID

router = APIRouter(tags=["auth"])

AUTH_LANDING_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Page0 — Sign In</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>
/* ==========================================================================
   DESIGN TOKENS — Light / Dark via CSS custom properties
   ========================================================================== */

:root {
  /* Light mode defaults */
  --bg-page:      #ffffff;
  --bg-surface:   #f8fafc;
  --bg-card:      #ffffff;
  --bg-card-hover:#f1f5f9;
  --bg-input:     #f1f5f9;
  --bg-header:    rgba(255,255,255,0.82);
  --bg-hero-glow: radial-gradient(ellipse 60% 50% at 50% -10%, rgba(139,92,246,0.08) 0%, transparent 70%);

  --border:       #e2e8f0;
  --border-2:     #cbd5e1;
  --border-focus: rgba(139,92,246,0.5);

  --violet:       #8b5cf6;
  --violet-2:     #7c3aed;
  --violet-light: #a78bfa;
  --violet-bg:    rgba(139,92,246,0.08);
  --violet-glow:  rgba(139,92,246,0.12);

  --teal:         #14b8a6;
  --teal-2:       #0d9488;
  --teal-bg:      rgba(20,184,166,0.08);

  --red:          #ef4444;
  --red-bg:       rgba(239,68,68,0.08);
  --orange:       #f97316;
  --orange-bg:    rgba(249,115,22,0.08);

  --text-0:       #0f172a;
  --text-1:       #334155;
  --text-2:       #475569;
  --text-3:       #94a3b8;
  --text-4:       #cbd5e1;
  --text-inv:     #ffffff;

  --shadow-sm:    0 1px 2px rgba(0,0,0,0.04);
  --shadow-md:    0 4px 12px rgba(0,0,0,0.06);
  --shadow-lg:    0 8px 30px rgba(0,0,0,0.08);
  --shadow-card:  0 1px 3px rgba(0,0,0,0.04), 0 0 0 1px rgba(0,0,0,0.02);

  --radius:       8px;
  --radius-lg:    12px;
  --radius-xl:    16px;
  --ease:         cubic-bezier(0.16, 1, 0.3, 1);

  --stat-bg:      #f8fafc;
}

/* === DARK MODE === */
body.dark {
  --bg-page:      #000000;
  --bg-surface:   #050505;
  --bg-card:      #0a0a0a;
  --bg-card-hover:#111111;
  --bg-input:     rgba(255,255,255,0.04);
  --bg-header:    rgba(0,0,0,0.82);
  --bg-hero-glow: radial-gradient(ellipse 60% 50% at 50% -10%, rgba(139,92,246,0.12) 0%, transparent 70%);

  --border:       rgba(255,255,255,0.08);
  --border-2:     rgba(255,255,255,0.14);

  --text-0:       #fafafa;
  --text-1:       #a1a1aa;
  --text-2:       #71717a;
  --text-3:       #52525b;
  --text-4:       #3f3f46;
  --text-inv:     #000000;

  --shadow-sm:    0 1px 2px rgba(0,0,0,0.3);
  --shadow-md:    0 4px 12px rgba(0,0,0,0.4);
  --shadow-lg:    0 8px 30px rgba(0,0,0,0.5);
  --shadow-card:  0 1px 3px rgba(0,0,0,0.3), 0 0 0 1px rgba(255,255,255,0.04);

  --stat-bg:      #0a0a0a;
}

/* === RESET === */
*,*::before,*::after{margin:0;padding:0;box-sizing:border-box;}

html{scroll-behavior:smooth;}

body{
  background:var(--bg-page);
  color:var(--text-0);
  font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  font-size:16px;
  line-height:1.6;
  min-height:100vh;
  -webkit-font-smoothing:antialiased;
  -moz-osx-font-smoothing:grayscale;
  transition:background .35s var(--ease), color .35s var(--ease);
}

/* Scrollbar */
::-webkit-scrollbar{width:6px;}
::-webkit-scrollbar-track{background:transparent;}
::-webkit-scrollbar-thumb{background:var(--text-4);border-radius:6px;}
*{scrollbar-width:thin;scrollbar-color:var(--text-4) transparent;}

a{color:inherit;text-decoration:none;}

/* ==========================================================================
   HEADER
   ========================================================================== */
.header{
  position:fixed;top:0;left:0;right:0;z-index:100;
  background:var(--bg-header);
  backdrop-filter:blur(20px) saturate(180%);
  -webkit-backdrop-filter:blur(20px) saturate(180%);
  border-bottom:1px solid var(--border);
  height:64px;
  transition:background .35s var(--ease), border-color .35s var(--ease);
}
.header-inner{
  max-width:1200px;margin:0 auto;padding:0 32px;height:100%;
  display:flex;justify-content:space-between;align-items:center;
}
.h-left{display:flex;align-items:center;gap:32px;}
.logo{
  font-size:18px;font-weight:800;letter-spacing:1.2px;
  color:var(--text-0);text-transform:uppercase;
  transition:color .35s var(--ease);
}
.logo span{color:var(--violet);}

.nav{display:flex;gap:28px;list-style:none;}
.nav a{
  font-size:14px;font-weight:500;color:var(--text-2);
  transition:color .2s var(--ease);letter-spacing:0.2px;
}
.nav a:hover{color:var(--text-0);}

.h-right{display:flex;align-items:center;gap:16px;}

/* Theme toggle */
.theme-toggle{
  width:40px;height:40px;border-radius:50%;
  background:var(--bg-input);border:1px solid var(--border);
  display:flex;align-items:center;justify-content:center;
  cursor:pointer;transition:all .25s var(--ease);
  color:var(--text-2);font-size:18px;
}
.theme-toggle:hover{
  background:var(--bg-card-hover);border-color:var(--border-2);
  color:var(--text-0);
}

.btn-signin-sm{
  background:var(--violet);color:#fff;border:none;
  padding:9px 22px;border-radius:var(--radius);
  font-family:inherit;font-size:13px;font-weight:600;
  letter-spacing:0.3px;cursor:pointer;
  transition:all .2s var(--ease);
}
.btn-signin-sm:hover{background:var(--violet-2);transform:translateY(-1px);box-shadow:0 4px 16px var(--violet-glow);}

/* ==========================================================================
   HERO
   ========================================================================== */
.hero{
  padding:160px 32px 80px;
  text-align:center;
  position:relative;
  overflow:hidden;
}
.hero::before{
  content:'';position:absolute;inset:0;
  background:var(--bg-hero-glow);
  pointer-events:none;
  transition:background .35s var(--ease);
}

.hero-badge{
  display:inline-flex;align-items:center;gap:8px;
  background:var(--violet-bg);border:1px solid rgba(139,92,246,0.15);
  border-radius:999px;padding:6px 18px 6px 12px;
  font-size:13px;font-weight:600;color:var(--violet);
  letter-spacing:0.5px;margin-bottom:28px;
  transition:all .35s var(--ease);
}
.hero-badge-dot{
  width:7px;height:7px;border-radius:50%;background:var(--violet);
  animation:pulse-dot 2s ease-in-out infinite;
}
@keyframes pulse-dot{
  0%,100%{opacity:1;transform:scale(1);}
  50%{opacity:.5;transform:scale(1.3);}
}

.hero h1{
  font-size:clamp(36px, 5vw, 64px);
  font-weight:800;
  line-height:1.08;
  letter-spacing:-1.5px;
  color:var(--text-0);
  max-width:800px;
  margin:0 auto 24px;
  transition:color .35s var(--ease);
}
.hero h1 em{
  font-style:normal;
  background:linear-gradient(135deg, var(--violet) 0%, var(--violet-light) 50%, var(--teal) 100%);
  -webkit-background-clip:text;
  -webkit-text-fill-color:transparent;
  background-clip:text;
}

.hero-sub{
  font-size:18px;
  line-height:1.7;
  color:var(--text-2);
  max-width:620px;
  margin:0 auto 40px;
  font-weight:400;
  transition:color .35s var(--ease);
}

.hero-ctas{
  display:flex;gap:16px;justify-content:center;align-items:center;
  flex-wrap:wrap;margin-bottom:28px;
}

.btn-primary{
  display:inline-flex;align-items:center;gap:10px;
  background:var(--violet);color:#fff;border:none;
  padding:14px 32px;border-radius:var(--radius-lg);
  font-family:inherit;font-size:15px;font-weight:600;
  letter-spacing:0.3px;cursor:pointer;
  transition:all .25s var(--ease);
  text-decoration:none;
}
.btn-primary:hover{
  background:var(--violet-2);
  transform:translateY(-2px);
  box-shadow:0 8px 30px var(--violet-glow);
}
.btn-primary:active{transform:translateY(0);}

.btn-primary svg{width:20px;height:20px;flex-shrink:0;}

.btn-ghost{
  display:inline-flex;align-items:center;gap:8px;
  background:transparent;color:var(--text-1);
  border:1px solid var(--border-2);
  padding:14px 28px;border-radius:var(--radius-lg);
  font-family:inherit;font-size:15px;font-weight:600;
  letter-spacing:0.3px;cursor:pointer;
  transition:all .25s var(--ease);
  text-decoration:none;
}
.btn-ghost:hover{
  border-color:var(--text-3);
  background:var(--bg-card-hover);
  transform:translateY(-2px);
}
.btn-ghost svg{width:18px;height:18px;flex-shrink:0;}

.hero-trust{
  font-size:13px;color:var(--text-3);
  display:flex;align-items:center;gap:8px;
  justify-content:center;
  transition:color .35s var(--ease);
}
.hero-trust svg{width:16px;height:16px;color:var(--teal);flex-shrink:0;}

/* ==========================================================================
   FEATURES
   ========================================================================== */
.section{
  max-width:1200px;margin:0 auto;padding:80px 32px;
}
.section-label{
  font-size:12px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;
  color:var(--violet);text-align:center;margin-bottom:12px;
  transition:color .35s var(--ease);
}
.section-title{
  font-size:clamp(24px, 3vw, 36px);
  font-weight:700;letter-spacing:-0.5px;
  text-align:center;color:var(--text-0);
  margin-bottom:16px;
  transition:color .35s var(--ease);
}
.section-desc{
  font-size:16px;color:var(--text-2);text-align:center;
  max-width:560px;margin:0 auto 56px;
  transition:color .35s var(--ease);
}

.features-grid{
  display:grid;
  grid-template-columns:repeat(auto-fit, minmax(300px, 1fr));
  gap:20px;
}

.f-card{
  background:var(--bg-card);
  border:1px solid var(--border);
  border-radius:var(--radius-xl);
  padding:36px 32px;
  transition:all .3s var(--ease);
  position:relative;
  overflow:hidden;
}
.f-card::before{
  content:'';position:absolute;top:0;left:32px;right:32px;height:1px;
  background:linear-gradient(90deg, transparent, var(--violet-bg), transparent);
  opacity:0;transition:opacity .3s var(--ease);
}
.f-card:hover{
  border-color:var(--border-2);
  transform:translateY(-4px);
  box-shadow:var(--shadow-lg);
}
.f-card:hover::before{opacity:1;}

.f-icon{
  width:48px;height:48px;border-radius:var(--radius-lg);
  background:var(--violet-bg);border:1px solid rgba(139,92,246,0.12);
  display:flex;align-items:center;justify-content:center;
  margin-bottom:20px;color:var(--violet);font-size:22px;
  transition:all .3s var(--ease);
}
.f-card:hover .f-icon{
  background:var(--violet);color:#fff;
  box-shadow:0 4px 16px var(--violet-glow);
}
.f-card.teal .f-icon{
  background:var(--teal-bg);border-color:rgba(20,184,166,0.12);
  color:var(--teal);
}
.f-card.teal:hover .f-icon{
  background:var(--teal);color:#fff;
  box-shadow:0 4px 16px rgba(20,184,166,0.12);
}

.f-title{
  font-size:17px;font-weight:700;color:var(--text-0);
  margin-bottom:10px;letter-spacing:-0.2px;
  transition:color .35s var(--ease);
}
.f-desc{
  font-size:14px;line-height:1.7;color:var(--text-2);
  transition:color .35s var(--ease);
}
.f-tag{
  display:inline-block;margin-top:16px;
  font-size:11px;font-weight:700;letter-spacing:0.8px;text-transform:uppercase;
  color:var(--violet);background:var(--violet-bg);
  padding:4px 12px;border-radius:999px;
  transition:all .35s var(--ease);
}
.f-card.teal .f-tag{color:var(--teal);background:var(--teal-bg);}

/* ==========================================================================
   STATS
   ========================================================================== */
.stats-section{
  max-width:1200px;margin:0 auto;padding:0 32px 80px;
}
.stats-grid{
  display:grid;
  grid-template-columns:repeat(4, 1fr);
  gap:1px;
  background:var(--border);
  border:1px solid var(--border);
  border-radius:var(--radius-xl);
  overflow:hidden;
  transition:background .35s var(--ease), border-color .35s var(--ease);
}
.stat-item{
  background:var(--stat-bg);
  padding:40px 32px;
  text-align:center;
  transition:all .3s var(--ease);
}
.stat-item:hover{background:var(--bg-card-hover);}
.stat-val{
  font-size:clamp(32px, 4vw, 48px);
  font-weight:800;
  letter-spacing:-1px;
  color:var(--text-0);
  line-height:1;
  margin-bottom:8px;
  transition:color .35s var(--ease);
}
.stat-val .accent{color:var(--violet);}
.stat-label{
  font-size:13px;font-weight:500;color:var(--text-3);
  letter-spacing:0.3px;
  transition:color .35s var(--ease);
}

/* ==========================================================================
   CTA SECTION
   ========================================================================== */
.cta-section{
  max-width:1200px;margin:0 auto;padding:0 32px 100px;
}
.cta-card{
  background:var(--bg-card);
  border:1px solid var(--border);
  border-radius:var(--radius-xl);
  padding:64px 40px;
  text-align:center;
  position:relative;overflow:hidden;
  transition:all .35s var(--ease);
}
.cta-card::before{
  content:'';position:absolute;inset:0;
  background:radial-gradient(ellipse 80% 60% at 50% 120%, var(--violet-glow) 0%, transparent 70%);
  pointer-events:none;
}
.cta-card h2{
  font-size:clamp(24px, 3vw, 32px);
  font-weight:700;letter-spacing:-0.5px;
  color:var(--text-0);margin-bottom:16px;
  position:relative;
  transition:color .35s var(--ease);
}
.cta-card p{
  font-size:16px;color:var(--text-2);
  max-width:480px;margin:0 auto 32px;
  position:relative;
  transition:color .35s var(--ease);
}
.cta-card .btn-primary{position:relative;}

/* ==========================================================================
   FOOTER
   ========================================================================== */
.footer{
  border-top:1px solid var(--border);
  padding:32px;
  transition:border-color .35s var(--ease);
}
.footer-inner{
  max-width:1200px;margin:0 auto;
  display:flex;justify-content:space-between;align-items:center;
  flex-wrap:wrap;gap:16px;
}
.footer-left{
  font-size:13px;color:var(--text-3);
  transition:color .35s var(--ease);
}
.footer-left strong{color:var(--text-2);font-weight:600;}
.footer-links{display:flex;gap:24px;list-style:none;}
.footer-links a{
  font-size:13px;color:var(--text-3);
  transition:color .2s var(--ease);
}
.footer-links a:hover{color:var(--text-0);}

/* ==========================================================================
   RESPONSIVE
   ========================================================================== */
@media(max-width:768px){
  .header-inner{padding:0 20px;}
  .nav{display:none;}
  .hero{padding:120px 20px 60px;}
  .section{padding:60px 20px;}
  .stats-grid{grid-template-columns:repeat(2,1fr);}
  .features-grid{grid-template-columns:1fr;}
  .footer-inner{flex-direction:column;text-align:center;}
  .stats-section{padding:0 20px 60px;}
  .cta-section{padding:0 20px 60px;}
  .cta-card{padding:48px 24px;}
}
@media(max-width:480px){
  .hero h1{font-size:32px;letter-spacing:-0.5px;}
  .hero-ctas{flex-direction:column;gap:12px;}
  .btn-primary,.btn-ghost{width:100%;justify-content:center;}
  .stats-grid{grid-template-columns:1fr 1fr;}
  .stat-item{padding:28px 16px;}
}

/* ==========================================================================
   ANIMATIONS
   ========================================================================== */
@keyframes fade-up{
  from{opacity:0;transform:translateY(20px);}
  to{opacity:1;transform:translateY(0);}
}
.fade-up{animation:fade-up .6s var(--ease) forwards;opacity:0;}
.fade-up-d1{animation-delay:.1s;}
.fade-up-d2{animation-delay:.2s;}
.fade-up-d3{animation-delay:.3s;}
.fade-up-d4{animation-delay:.4s;}
.fade-up-d5{animation-delay:.5s;}
.fade-up-d6{animation-delay:.6s;}
</style>
</head>
<body>

<!-- ======= HEADER ======= -->
<header class="header">
  <div class="header-inner">
    <div class="h-left">
      <a href="/" class="logo">PAGE<span>.0</span></a>
      <ul class="nav">
        <li><a href="#features">Features</a></li>
        <li><a href="#stats">How It Works</a></li>
        <li><a href="/dashboard">Dashboard</a></li>
      </ul>
    </div>
    <div class="h-right">
      <button class="theme-toggle" id="themeToggle" aria-label="Toggle theme" title="Toggle light/dark mode">
        <span id="themeIcon">&#9790;</span>
      </button>
      <a href="/login" class="btn-signin-sm">Sign In</a>
    </div>
  </div>
</header>

<!-- ======= HERO ======= -->
<section class="hero">
  <div class="hero-badge fade-up">
    <span class="hero-badge-dot"></span>
    Autonomous SRE Agent
  </div>
  <h1 class="fade-up fade-up-d1">Autonomous Incident Response in <em>47 Seconds</em></h1>
  <p class="hero-sub fade-up fade-up-d2">Page0 monitors your infrastructure, detects anomalies, diagnoses root cause, and resolves incidents&mdash;all without human intervention.</p>
  <div class="hero-ctas fade-up fade-up-d3">
    <a href="/login" class="btn-primary">
      <!-- Auth0 shield icon -->
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
      Sign in with Auth0
    </a>
    <a href="/dashboard" class="btn-ghost">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
      Go to Dashboard
    </a>
  </div>
  <div class="hero-trust fade-up fade-up-d4">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
    Secured by Auth0 CIBA Backchannel Authentication &amp; Token Vault
  </div>
</section>

<!-- ======= FEATURES ======= -->
<section class="section" id="features">
  <div class="section-label fade-up">Core Capabilities</div>
  <h2 class="section-title fade-up fade-up-d1">Enterprise-Grade Security, Zero Friction</h2>
  <p class="section-desc fade-up fade-up-d2">Every authentication flow and API credential is managed through Auth0 &mdash; the agent operates with full authorization but never touches raw secrets.</p>
  <div class="features-grid">
    <div class="f-card fade-up fade-up-d3">
      <div class="f-icon">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg>
      </div>
      <div class="f-title">CIBA Backchannel Auth</div>
      <div class="f-desc">Phone-based authentication. Your voice is the approval. No passwords, no tokens to manage. The on-call engineer approves remediation by speaking to the AI agent.</div>
      <span class="f-tag">Auth0 CIBA</span>
    </div>
    <div class="f-card fade-up fade-up-d4">
      <div class="f-icon">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
      </div>
      <div class="f-title">Token Vault</div>
      <div class="f-desc">All API credentials managed through Auth0 Token Vault. The agent never sees raw secrets. Rotate, revoke, and audit every credential from a single pane of glass.</div>
      <span class="f-tag">Auth0 Token Vault</span>
    </div>
    <div class="f-card teal fade-up fade-up-d5">
      <div class="f-icon">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
      </div>
      <div class="f-title">Dynamic Connectors</div>
      <div class="f-desc">Airbyte connectors created on-the-fly based on incident type. No pre-configuration needed. The agent builds its own data pipeline to investigate each unique failure.</div>
      <span class="f-tag">Airbyte Dynamic</span>
    </div>
  </div>
</section>

<!-- ======= STATS ======= -->
<section class="stats-section" id="stats">
  <div class="stats-grid">
    <div class="stat-item fade-up">
      <div class="stat-val">47<span class="accent">s</span></div>
      <div class="stat-label">Average Resolution</div>
    </div>
    <div class="stat-item fade-up fade-up-d1">
      <div class="stat-val">99.9<span class="accent">%</span></div>
      <div class="stat-label">Uptime SLA</div>
    </div>
    <div class="stat-item fade-up fade-up-d2">
      <div class="stat-val">0</div>
      <div class="stat-label">Human Interventions</div>
    </div>
    <div class="stat-item fade-up fade-up-d3">
      <div class="stat-val">8</div>
      <div class="stat-label">Integrated Tools</div>
    </div>
  </div>
</section>

<!-- ======= CTA ======= -->
<section class="cta-section">
  <div class="cta-card fade-up">
    <h2>Ready to Never Get Paged at 3 AM Again?</h2>
    <p>Let Page0 handle the full incident lifecycle &mdash; from detection to resolution &mdash; while you sleep.</p>
    <a href="/login" class="btn-primary">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
      Get Started with Auth0
    </a>
  </div>
</section>

<!-- ======= FOOTER ======= -->
<footer class="footer">
  <div class="footer-inner">
    <div class="footer-left">&copy; 2026 <strong>Page0</strong> &mdash; Deep Agents Hackathon</div>
    <ul class="footer-links">
      <li><a href="#features">Features</a></li>
      <li><a href="/dashboard">Dashboard</a></li>
      <li><a href="/login">Sign In</a></li>
    </ul>
  </div>
</footer>

<!-- ======= SCRIPTS ======= -->
<script>
(function(){
  /* ---- Theme Toggle ---- */
  const body = document.body;
  const toggle = document.getElementById('themeToggle');
  const icon = document.getElementById('themeIcon');

  // Check for saved preference, default to light
  const saved = localStorage.getItem('sc-theme');
  if(saved === 'dark'){
    body.classList.add('dark');
    icon.innerHTML = '&#9728;'; // sun
  }

  toggle.addEventListener('click', function(){
    body.classList.toggle('dark');
    const isDark = body.classList.contains('dark');
    localStorage.setItem('sc-theme', isDark ? 'dark' : 'light');
    icon.innerHTML = isDark ? '&#9728;' : '&#9790;'; // sun : moon
  });

  /* ---- Intersection Observer for fade-up ---- */
  const obs = new IntersectionObserver(function(entries){
    entries.forEach(function(entry){
      if(entry.isIntersecting){
        entry.target.style.animationPlayState = 'running';
        obs.unobserve(entry.target);
      }
    });
  }, {threshold: 0.1});

  document.querySelectorAll('.fade-up').forEach(function(el){
    el.style.animationPlayState = 'paused';
    obs.observe(el);
  });

  /* ---- Smooth scroll for anchor links ---- */
  document.querySelectorAll('a[href^="#"]').forEach(function(a){
    a.addEventListener('click', function(e){
      e.preventDefault();
      const target = document.querySelector(this.getAttribute('href'));
      if(target) target.scrollIntoView({behavior:'smooth', block:'start'});
    });
  });
})();
</script>

</body>
</html>"""


@router.get("/", response_class=HTMLResponse)
async def auth_landing():
    """Serve the landing page (homepage)."""
    return AUTH_LANDING_HTML


@router.get("/auth", response_class=HTMLResponse)
async def auth_landing_alias():
    """Alias: /auth also serves the landing page."""
    return AUTH_LANDING_HTML

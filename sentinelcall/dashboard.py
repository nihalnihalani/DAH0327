"""SentinelCall FastAPI Dashboard — production-grade incident command center.

Serves a single-page HTML dashboard with real-time SSE updates and exposes
JSON API endpoints for the agent, metrics, incidents, and Overmind trace.
"""

import asyncio
import json
import logging
import os
import time
from typing import Any

from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from sentinelcall.agent import SentinelCallAgent
from sentinelcall.webhook_server import router as bland_router
from sentinelcall.ghost_webhooks import router as ghost_router

logger = logging.getLogger(__name__)

app = FastAPI(title="SentinelCall", version="1.0.0")

# Mount webhook routers
app.include_router(bland_router)
if ghost_router is not None:
    app.include_router(ghost_router)
# Singleton agent
agent = SentinelCallAgent()

# ---------------------------------------------------------------------------
# HTML Dashboard
# ---------------------------------------------------------------------------

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SentinelCall</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Geist+Mono:wght@400;500;600&family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
/* ==========================================================================
   DESIGN TOKENS — Stitch: SentinelCall Final (Charcoal + Violet)
   ========================================================================== */
:root {
  /* Backgrounds — true black */
  --bg-0:       #000000;
  --bg-1:       #050505;
  --bg-2:       #0a0a0a;
  --bg-3:       #0f0f0f;
  --bg-4:       #171717;
  --bg-hover:   #1a1a1a;
  --bg-input:   rgba(255,255,255,0.03);

  /* Borders */
  --border:     rgba(255,255,255,0.07);
  --border-2:   rgba(255,255,255,0.12);
  --border-focus:rgba(139,92,246,0.5);

  /* Violet primary */
  --violet:     #8b5cf6;
  --violet-2:   #a78bfa;
  --violet-bg:  rgba(139,92,246,0.10);
  --violet-glow:rgba(139,92,246,0.06);

  /* Teal success */
  --teal:       #14b8a6;
  --teal-2:     #2dd4bf;
  --teal-bg:    rgba(20,184,166,0.10);

  /* Red danger */
  --red:        #ef4444;
  --red-2:      #f87171;
  --red-bg:     rgba(239,68,68,0.10);

  /* Orange warning */
  --orange:     #f97316;
  --orange-2:   #fb923c;
  --orange-bg:  rgba(249,115,22,0.10);

  /* Text */
  --text-0:     #fafafa;
  --text-1:     #a1a1aa;
  --text-2:     #71717a;
  --text-3:     #52525b;
  --text-4:     #3f3f46;

  /* Misc */
  --radius:     8px;
  --radius-lg:  12px;
  --ease:       cubic-bezier(0.16, 1, 0.3, 1);
}

/* === LIGHT MODE === */
body.light {
  --bg-0:       #ffffff;
  --bg-1:       #f8f9fa;
  --bg-2:       #f1f3f5;
  --bg-3:       #e9ecef;
  --bg-4:       #dee2e6;
  --bg-hover:   #e9ecef;
  --bg-input:   rgba(0,0,0,0.03);
  --border:     rgba(0,0,0,0.08);
  --border-2:   rgba(0,0,0,0.12);
  --border-focus:rgba(139,92,246,0.4);
  --violet-bg:  rgba(139,92,246,0.08);
  --violet-glow:rgba(139,92,246,0.05);
  --teal-bg:    rgba(20,184,166,0.08);
  --red-bg:     rgba(239,68,68,0.08);
  --orange-bg:  rgba(249,115,22,0.08);
  --text-0:     #1a1a2e;
  --text-1:     #4a4a5a;
  --text-2:     #6b7280;
  --text-3:     #9ca3af;
  --text-4:     #d1d5db;
}
body.light::after { opacity:0; }
body.light .header { background:rgba(255,255,255,0.85); }
body.light .pipe-progress-fill { box-shadow:none; }

/* === RESET === */
*,*::before,*::after{margin:0;padding:0;box-sizing:border-box;}

body{
  background:var(--bg-0);
  color:var(--text-0);
  font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  font-size:15px;
  line-height:1.6;
  min-height:100vh;
  -webkit-font-smoothing:antialiased;
}

/* Subtle noise texture */
body::after{
  content:'';position:fixed;inset:0;
  background:url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.015'/%3E%3C/svg%3E");
  pointer-events:none;z-index:0;opacity:0.4;
}

/* Scrollbar */
::-webkit-scrollbar{width:4px;}
::-webkit-scrollbar-track{background:transparent;}
::-webkit-scrollbar-thumb{background:var(--bg-4);border-radius:4px;}
*{scrollbar-width:thin;scrollbar-color:var(--bg-4) transparent;}

/* === HEADER === */
.header{
  position:sticky;top:0;z-index:100;
  background:rgba(0,0,0,0.85);
  backdrop-filter:blur(24px) saturate(180%);
  -webkit-backdrop-filter:blur(24px) saturate(180%);
  border-bottom:1px solid var(--border);
  padding:0 24px;height:56px;
  display:flex;justify-content:space-between;align-items:center;
}
.h-left{display:flex;align-items:center;gap:18px;}
.logo{
  font-size:20px;font-weight:700;letter-spacing:1px;color:var(--text-0);
}
.logo span{color:var(--violet);}
.h-sep{width:1px;height:20px;background:var(--border-2);}
.h-tag{font-size:13px;color:var(--text-3);font-weight:400;letter-spacing:0.3px;}
.h-right{display:flex;align-items:center;gap:16px;}

.pill{
  display:flex;align-items:center;gap:9px;
  background:var(--bg-2);border:1px solid var(--border);
  border-radius:999px;padding:7px 18px 7px 14px;
  font-size:13px;font-weight:600;letter-spacing:0.8px;text-transform:uppercase;
  transition:all .2s var(--ease);
}
.dot{
  width:9px;height:9px;border-radius:50%;flex-shrink:0;
  position:relative;
}
.dot::after{
  content:'';position:absolute;inset:-3px;border-radius:50%;
  animation:ring 2.5s ease-in-out infinite;opacity:0;
}
@keyframes ring{0%,100%{transform:scale(1);opacity:.5;}50%{transform:scale(2.2);opacity:0;}}
.dot.g{background:var(--teal);box-shadow:0 0 6px var(--teal-bg);}
.dot.g::after{border:1px solid var(--teal-bg);}
.dot.r{background:var(--red);box-shadow:0 0 6px var(--red-bg);animation:blink .9s infinite;}
.dot.r::after{border:1px solid var(--red-bg);animation:ring .8s ease-in-out infinite;}
.dot.y{background:var(--orange);box-shadow:0 0 6px var(--orange-bg);}
.dot.y::after{border:1px solid var(--orange-bg);}
@keyframes blink{0%,100%{opacity:1;}50%{opacity:.4;}}

/* === THEME TOGGLE === */
.theme-toggle{
  width:40px;height:22px;border-radius:12px;border:1px solid var(--border-2);
  background:var(--bg-3);cursor:pointer;position:relative;
  transition:all .3s var(--ease);padding:0;
}
.theme-toggle::after{
  content:'';position:absolute;top:2px;left:2px;
  width:16px;height:16px;border-radius:50%;
  background:var(--violet);transition:all .3s var(--ease);
  box-shadow:0 0 6px var(--violet-glow);
}
body.light .theme-toggle::after{transform:translateX(18px);background:var(--orange);}
.theme-icon{font-size:12px;position:absolute;top:50%;transform:translateY(-50%);}
.theme-icon.moon{left:5px;}
.theme-icon.sun{right:5px;}

.btn-trigger{
  background:var(--red);color:#fff;border:none;
  padding:10px 26px;border-radius:8px;
  font-family:inherit;font-size:13px;font-weight:600;
  letter-spacing:0.6px;text-transform:uppercase;
  cursor:pointer;transition:all .2s var(--ease);
}
.btn-trigger:hover{background:#dc2626;transform:translateY(-1px);box-shadow:0 4px 20px var(--red-bg);}
.btn-trigger:active{transform:translateY(0);}
.btn-trigger:disabled{opacity:.3;cursor:not-allowed;transform:none;box-shadow:none;}
.trig-status{font-size:12px;color:var(--text-3);}

/* === LAYOUT === */
.main{position:relative;z-index:5;padding:20px 24px 40px;max-width:100%;margin:0 auto;}

/* === STATS === */
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:16px;}
.s-card{
  background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius);
  padding:18px 20px;transition:all .2s var(--ease);position:relative;overflow:hidden;
}
.s-card:hover{border-color:var(--border-2);}
.s-card::before{
  content:'';position:absolute;top:0;left:20px;right:20px;height:1px;
  background:linear-gradient(90deg,transparent,var(--violet-bg),transparent);
}
.s-label{font-size:12px;font-weight:500;color:var(--text-3);letter-spacing:0.6px;text-transform:uppercase;margin-bottom:8px;}
.s-val{font-size:36px;font-weight:700;color:var(--text-0);line-height:1;letter-spacing:-0.5px;}
.s-unit{font-size:15px;font-weight:400;color:var(--text-3);margin-left:3px;}
.s-sub{font-size:12px;margin-top:8px;font-weight:500;}
.s-sub.ok{color:var(--teal);}
.s-sub.err{color:var(--red);}
.s-sub.n{color:var(--text-3);}

/* === CARD / PANEL === */
.card{
  background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius);
  padding:20px;transition:border-color .2s var(--ease);
}
.card:hover{border-color:var(--border-2);}
.card-h{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;}
.card-t{font-size:14px;font-weight:600;color:var(--text-1);letter-spacing:0.3px;}
.badge{
  font-size:11px;font-weight:600;letter-spacing:0.5px;text-transform:uppercase;
  padding:4px 12px;border-radius:999px;
  color:var(--violet-2);background:var(--violet-bg);
}

/* === PIPELINE (ORBITAL) — faithful to React radial-orbital-timeline === */
.pipe-wrap{
  background:var(--bg-0);border:1px solid var(--border);border-radius:var(--radius);
  padding:20px 24px 16px;margin-bottom:16px;transition:border-color .2s var(--ease);
  overflow:hidden;
}
.pipe-wrap:hover{border-color:var(--border-2);}
.pipe-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:0;}
.pipe-title{font-size:14px;font-weight:600;color:var(--text-1);letter-spacing:0.3px;}
.pipe-timer{
  font-family:'Geist Mono','JetBrains Mono',monospace;
  font-size:13px;color:var(--text-3);display:flex;align-items:center;gap:8px;
}
.pipe-timer .td{width:7px;height:7px;border-radius:50%;background:var(--teal);}
.pipe-timer.on .td{background:var(--violet);animation:blink 1s infinite;}

.orbit-container{
  position:relative;width:100%;height:560px;
  display:flex;align-items:center;justify-content:center;
  cursor:default;
}

/* Central core — matches React: w-16 gradient sphere + ping rings */
.orbit-core{
  position:absolute;z-index:10;display:flex;align-items:center;justify-content:center;
}
.core-sphere{
  width:64px;height:64px;border-radius:50%;
  background:linear-gradient(135deg,#8b5cf6,#3b82f6,#14b8a6);
  display:flex;align-items:center;justify-content:center;
  animation:core-pulse 2s cubic-bezier(0.4,0,0.6,1) infinite;
  z-index:3;position:relative;
}
.core-inner{
  width:32px;height:32px;border-radius:50%;
  background:rgba(255,255,255,0.8);
  backdrop-filter:blur(12px);
}
/* Ping rings — matches React animate-ping */
.core-ping1,.core-ping2{
  position:absolute;border-radius:50%;border:1px solid rgba(255,255,255,0.2);
  animation:ping-ring 1s cubic-bezier(0,0,0.2,1) infinite;
}
.core-ping1{width:80px;height:80px;}
.core-ping2{width:96px;height:96px;border-color:rgba(255,255,255,0.1);animation-delay:0.5s;}
@keyframes ping-ring{0%{transform:scale(1);opacity:0.7;}75%,100%{transform:scale(2);opacity:0;}}
@keyframes core-pulse{0%,100%{opacity:1;}50%{opacity:0.5;}}

/* Orbit ring — matches React w-96 = 384px circle */
.orbit-ring{
  position:absolute;border-radius:50%;border:1px solid rgba(255,255,255,0.1);
  pointer-events:none;
}

/* Orbital nodes */
.o-node{
  position:absolute;display:flex;flex-direction:column;align-items:center;
  cursor:pointer;transition:opacity .5s, z-index 0s;
  z-index:5;
  transform-origin:center center;
  will-change:left,top,opacity;
}
.o-node:hover{z-index:15;}

/* Energy aura glow — matches React radial-gradient aura */
.o-aura{
  position:absolute;border-radius:50%;
  background:radial-gradient(circle,rgba(255,255,255,0.2) 0%,rgba(255,255,255,0) 70%);
  pointer-events:none;transition:all .3s;
}
.o-aura.pulsing{animation:core-pulse 1s cubic-bezier(0.4,0,0.6,1) infinite;}

/* Node circle — matches React w-10 h-10 = 40px, scaled up to 48px */
.o-circle{
  width:52px;height:52px;border-radius:50%;
  border:2px solid rgba(255,255,255,0.4);
  background:var(--bg-0);color:var(--text-0);
  display:flex;align-items:center;justify-content:center;
  font-size:22px;transition:all .3s cubic-bezier(0.4,0,0.2,1);
  position:relative;z-index:2;
}

/* States matching React styles */
.o-node.pending .o-circle{opacity:0.4;border-color:rgba(255,255,255,0.4);background:rgba(0,0,0,0.4);}
.o-node.active .o-circle{
  background:white;color:black;border-color:white;
  box-shadow:0 0 30px rgba(255,255,255,0.4),0 0 60px rgba(139,92,246,0.2);
  width:62px;height:62px;font-size:26px;
  margin-left:-5px;margin-top:-5px;
  opacity:1;
  animation:active-glow 1.5s ease-in-out infinite;
}
@keyframes active-glow{
  0%,100%{box-shadow:0 0 30px rgba(255,255,255,0.4),0 0 60px rgba(139,92,246,0.2);}
  50%{box-shadow:0 0 40px rgba(255,255,255,0.6),0 0 80px rgba(139,92,246,0.35);}
}
.o-node.complete .o-circle{
  background:var(--bg-0);border-color:rgba(20,184,166,0.8);color:var(--teal);opacity:1;
  box-shadow:0 0 12px rgba(20,184,166,0.15);
}
.o-node.related .o-circle{
  background:rgba(255,255,255,0.5);color:black;border-color:white;
  animation:core-pulse 2s cubic-bezier(0.4,0,0.6,1) infinite;
}
.o-node.error .o-circle{
  background:var(--red-bg);border-color:var(--red);color:var(--red);
  box-shadow:0 0 16px rgba(239,68,68,0.15);animation:blink 1s infinite;opacity:1;
}

/* Label below node */
.o-label{
  font-size:11px;font-weight:600;color:rgba(255,255,255,0.7);
  text-align:center;white-space:nowrap;
  margin-top:10px;pointer-events:none;transition:all .3s;letter-spacing:0.5px;
}
.o-node.active .o-label{color:white;transform:scale(1.25);}
.o-node.complete .o-label{color:rgba(255,255,255,0.9);}

/* Expanded card — matches React Card with bg-black/90 backdrop-blur */
.o-card{
  position:absolute;top:80px;left:50%;transform:translateX(-50%);
  width:260px;
  background:rgba(0,0,0,0.9);
  backdrop-filter:blur(16px);
  border:1px solid rgba(255,255,255,0.3);
  border-radius:8px;padding:0;z-index:200;
  box-shadow:0 20px 60px rgba(0,0,0,0.5),0 0 20px rgba(255,255,255,0.1);
  animation:card-in .3s var(--ease);
  overflow:visible;
}
.o-card::before{
  content:'';position:absolute;top:-12px;left:50%;transform:translateX(-50%);
  width:1px;height:12px;background:rgba(255,255,255,0.5);
}
@keyframes card-in{from{opacity:0;transform:translateX(-50%) translateY(8px);}to{opacity:1;transform:translateX(-50%) translateY(0);}}
@keyframes dash-flow{from{stroke-dashoffset:12;}to{stroke-dashoffset:0;}}

.o-card-header{padding:16px 16px 8px;display:flex;flex-direction:column;gap:8px;}
.o-card-meta{display:flex;justify-content:space-between;align-items:center;}
.o-card-badge{
  font-family:'Geist Mono',monospace;font-size:10px;font-weight:600;
  padding:3px 8px;border-radius:9999px;letter-spacing:0.5px;
  display:inline-flex;align-items:center;
}
.o-card-badge.complete{color:white;background:black;border:1px solid white;}
.o-card-badge.active{color:black;background:white;border:1px solid black;}
.o-card-badge.pending{color:white;background:rgba(0,0,0,0.4);border:1px solid rgba(255,255,255,0.5);}
.o-card-badge.error{color:white;background:rgba(239,68,68,0.3);border:1px solid var(--red);}
.o-card-date{font-family:'Geist Mono',monospace;font-size:10px;color:rgba(255,255,255,0.5);}
.o-card-title{font-size:14px;font-weight:600;color:white;margin-top:4px;}

.o-card-body{padding:0 16px 16px;font-size:12px;color:rgba(255,255,255,0.8);line-height:1.5;}
.o-card-body p{margin-bottom:12px;}

/* Metric bar — step-specific SRE metric display */
.o-energy{
  padding-top:12px;margin-top:12px;border-top:1px solid rgba(255,255,255,0.1);
}
.o-energy-head{display:flex;justify-content:space-between;align-items:center;font-size:11px;margin-bottom:4px;}
.o-energy-label{display:flex;align-items:center;gap:4px;color:rgba(255,255,255,0.8);}
.o-energy-val{font-family:'Geist Mono',monospace;color:rgba(255,255,255,0.8);}
.o-energy-bar{height:4px;border-radius:9999px;background:rgba(255,255,255,0.1);overflow:hidden;}
.o-energy-fill{height:100%;border-radius:9999px;background:linear-gradient(90deg,#3b82f6,#8b5cf6);transition:width .5s;}

/* Connected nodes — matches React relatedIds buttons */
.o-connected{
  padding-top:12px;margin-top:12px;border-top:1px solid rgba(255,255,255,0.1);
}
.o-connected-head{display:flex;align-items:center;gap:4px;margin-bottom:8px;font-size:11px;color:rgba(255,255,255,0.7);text-transform:uppercase;letter-spacing:0.8px;font-weight:500;}
.o-conn-btn{
  display:inline-flex;align-items:center;gap:4px;
  padding:2px 8px;height:24px;
  font-size:11px;color:rgba(255,255,255,0.8);
  background:transparent;border:1px solid rgba(255,255,255,0.2);
  cursor:pointer;transition:all .2s;font-family:inherit;
}
.o-conn-btn:hover{background:rgba(255,255,255,0.1);color:white;}
.o-conn-arrow{font-size:10px;color:rgba(255,255,255,0.6);}

/* Orbit SVG connectors */
.orbit-svg{position:absolute;inset:0;z-index:2;pointer-events:none;}

/* === GRID === */
.g2{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px;}
.col{display:flex;flex-direction:column;gap:12px;}

/* === SERVICES === */
.svc-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:12px;}
.svc{
  background:var(--bg-input);border:1px solid var(--border);border-radius:8px;
  padding:16px 18px;transition:all .2s var(--ease);position:relative;
}
.svc::before{content:'';position:absolute;left:0;top:0;bottom:0;width:3px;border-radius:3px 0 0 3px;}
.svc.healthy::before{background:var(--teal);}
.svc.degraded::before{background:var(--orange);}
.svc.critical::before{background:var(--red);}
.svc.critical{border-color:rgba(239,68,68,0.12);}
.svc:hover{border-color:var(--border-2);background:var(--bg-hover);}
.svc-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;}
.svc-name{font-size:13px;font-weight:600;color:var(--text-0);}
.svc-tag{
  font-family:'Geist Mono',monospace;font-size:10px;font-weight:600;
  letter-spacing:0.5px;text-transform:uppercase;padding:3px 8px;border-radius:4px;
}
.svc-tag.healthy{color:var(--teal);background:var(--teal-bg);}
.svc-tag.degraded{color:var(--orange);background:var(--orange-bg);}
.svc-tag.critical{color:var(--red);background:var(--red-bg);}
.spark{height:24px;display:flex;align-items:flex-end;gap:2px;}
.spark-b{flex:1;min-width:3px;border-radius:2px 2px 0 0;transition:height .3s ease;}

/* === METRICS === */
.m-table{width:100%;border-collapse:separate;border-spacing:0;}
.m-table th{
  font-size:11px;font-weight:600;color:var(--text-4);text-transform:uppercase;
  letter-spacing:0.8px;text-align:left;padding:10px 14px;border-bottom:1px solid var(--border);
}
.m-table td{
  font-family:'Geist Mono',monospace;font-size:13px;
  padding:12px 14px;border-bottom:1px solid var(--border);transition:background .15s;
}
.m-table tr:last-child td{border-bottom:none;}
.m-table tr:hover td{background:rgba(139,92,246,0.02);}
.m-table td:first-child{font-family:'Inter',sans-serif;font-weight:500;font-size:13px;color:var(--text-0);}
.v-ok{color:var(--teal);}
.v-warn{color:var(--orange);}
.v-crit{color:var(--red);font-weight:600;}

/* === TIMELINE === */
.tl{max-height:360px;overflow-y:auto;}
.tl-e{
  display:flex;align-items:flex-start;gap:12px;
  padding:10px 0;border-bottom:1px solid var(--border);
  animation:tl-in .25s var(--ease);
}
.tl-e:last-child{border-bottom:none;}
@keyframes tl-in{from{opacity:0;transform:translateX(-4px);}to{opacity:1;transform:translateX(0);}}
.tl-d{width:8px;height:8px;border-radius:50%;margin-top:6px;flex-shrink:0;}
.tl-d.i{background:var(--violet);box-shadow:0 0 6px var(--violet-bg);}
.tl-d.s{background:var(--teal);box-shadow:0 0 6px var(--teal-bg);}
.tl-d.e{background:var(--red);box-shadow:0 0 6px var(--red-bg);}
.tl-t{font-family:'Geist Mono',monospace;font-size:12px;color:var(--text-4);min-width:68px;flex-shrink:0;}
.tl-m{font-size:13px;color:var(--text-1);line-height:1.5;}
.tl-m.step{color:var(--teal-2);}
.tl-m.error{color:var(--red-2);}

/* === INCIDENT === */
.inc{max-height:360px;overflow-y:auto;}
.inc-r{
  display:grid;grid-template-columns:120px 1fr;gap:8px;
  padding:10px 0;border-bottom:1px solid var(--border);font-size:13px;align-items:baseline;
}
.inc-r:last-child{border-bottom:none;}
.inc-l{font-size:11px;font-weight:600;color:var(--text-3);text-transform:uppercase;letter-spacing:0.6px;}
.inc-v{color:var(--text-0);}
.inc-v a{color:var(--violet-2);text-decoration:none;border-bottom:1px solid var(--violet-bg);transition:border-color .2s;}
.inc-v a:hover{border-color:var(--violet);}
.sev{
  display:inline-block;font-family:'Geist Mono',monospace;
  font-size:11px;font-weight:600;padding:3px 10px;border-radius:4px;letter-spacing:0.3px;
}
.sev.s1{color:var(--red);background:var(--red-bg);}
.sev.s2{color:var(--orange);background:var(--orange-bg);}
.empty{color:var(--text-4);font-size:13px;text-align:center;padding:36px 16px;line-height:1.6;}

/* === SPONSORS === */
.sp-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:10px;}
.sp{
  background:var(--bg-input);border:1px solid var(--border);border-radius:10px;
  padding:22px 12px 18px;text-align:center;transition:all .2s var(--ease);
}
.sp:hover{border-color:var(--border-2);background:var(--bg-hover);transform:translateY(-3px);box-shadow:0 6px 24px rgba(0,0,0,.4);}
.sp-icon{
  width:44px;height:44px;border-radius:10px;margin:0 auto 12px;
  display:flex;align-items:center;justify-content:center;
  font-size:20px;background:var(--violet-bg);border:1px solid rgba(139,92,246,0.1);
}
.sp-name{font-size:13px;font-weight:600;color:var(--text-0);margin-bottom:4px;}
.sp-feat{font-size:10px;font-weight:500;color:var(--text-3);line-height:1.4;}
.sp-dot{width:6px;height:6px;border-radius:50%;background:var(--teal);margin:10px auto 0;box-shadow:0 0 6px var(--teal-bg);}

/* === PIPELINE PROGRESS BAR === */
.pipe-progress{
  margin-top:20px;height:4px;border-radius:4px;background:var(--bg-4);overflow:hidden;
}
.pipe-progress-fill{
  height:100%;border-radius:4px;background:linear-gradient(90deg,var(--violet),var(--teal));
  width:0%;transition:width .5s var(--ease);
  box-shadow:0 0 12px var(--violet-glow);
}

/* === STEP NUMBER BADGE === */
.p-step-num{
  position:absolute;top:-6px;right:-6px;
  width:20px;height:20px;border-radius:50%;
  background:var(--bg-4);border:1.5px solid var(--border-2);
  font-family:'Geist Mono',monospace;font-size:9px;font-weight:700;
  color:var(--text-3);display:flex;align-items:center;justify-content:center;
  transition:all .4s var(--ease);z-index:3;
}
.p-node.active .p-step-num{background:var(--violet);border-color:var(--violet);color:#fff;}
.p-node.complete .p-step-num{background:var(--teal);border-color:var(--teal);color:#fff;}
.p-node.error .p-step-num{background:var(--red);border-color:var(--red);color:#fff;}

/* === COMPLETED CHECKMARK OVERLAY === */
.p-node.complete .p-circle::after{
  content:'\2713';position:absolute;inset:0;border-radius:50%;
  background:rgba(20,184,166,0.2);
  display:flex;align-items:center;justify-content:center;
  font-size:20px;color:var(--teal);font-weight:700;
}

/* === RESPONSIVE === */
@media(max-width:1100px){
  .g2{grid-template-columns:1fr;}
  .stats{grid-template-columns:repeat(2,1fr);}
  .sp-grid{grid-template-columns:repeat(4,1fr);}
  .header,.main{padding-left:16px;padding-right:16px;}
}
@media(max-width:640px){
  .stats{grid-template-columns:1fr;}
  .sp-grid{grid-template-columns:repeat(2,1fr);}
  .pipe-canvas{overflow-x:auto;min-width:700px;}
}
</style>
</head>
<body>

<div class="header">
  <div class="h-left">
    <a href="/" class="logo" style="text-decoration:none;color:inherit;">SENTINEL<span>CALL</span></a>
    <div class="h-sep"></div>
    <div class="h-tag">Autonomous Incident Response</div>
  </div>
  <div class="h-right">
    <button class="theme-toggle" id="themeToggle" onclick="toggleTheme()" title="Toggle light/dark mode"></button>
    <div class="pill">
      <span id="agentDot" class="dot g"></span>
      <span id="agentStatusText" style="color:var(--teal);">IDLE</span>
    </div>
    <span id="triggerStatus" class="trig-status"></span>
    <button id="triggerBtn" class="btn-trigger" onclick="triggerIncident()">Trigger Incident</button>
  </div>
</div>

<div class="main">

  <div class="stats">
    <div class="s-card">
      <div class="s-label">Total Incidents</div>
      <div class="s-val" id="statInc">0</div>
      <div class="s-sub n" id="statIncD">System nominal</div>
    </div>
    <div class="s-card">
      <div class="s-label">Avg Resolution</div>
      <div class="s-val" id="statRes">&mdash;<span class="s-unit">sec</span></div>
      <div class="s-sub ok">vs 45 min industry avg</div>
    </div>
    <div class="s-card">
      <div class="s-label">LLM Gateway</div>
      <div class="s-val" id="statGw" style="font-size:22px;">TrueFoundry</div>
      <div class="s-sub n" id="statGwM">Cost-optimized routing</div>
    </div>
    <div class="s-card">
      <div class="s-label">Active Services</div>
      <div class="s-val" id="statSvc">5<span class="s-unit">/&thinsp;5</span></div>
      <div class="s-sub ok" id="statSvcD">All healthy</div>
    </div>
  </div>

  <div class="pipe-wrap">
    <div class="pipe-top">
      <div class="pipe-title">Incident Response Pipeline</div>
      <div class="pipe-timer" id="pTimer"><div class="td"></div><span id="pTimerT">Ready</span></div>
    </div>
    <div class="orbit-container" id="orbitContainer">
      <svg class="orbit-svg" id="orbitSvg"></svg>
      <div class="orbit-core">
        <div class="core-ping2"></div>
        <div class="core-ping1"></div>
        <div class="core-sphere"><div class="core-inner"></div></div>
      </div>
    </div>
    <div class="pipe-progress"><div class="pipe-progress-fill" id="pProgress"></div></div>
  </div>

  <div class="g2">
    <div class="col">
      <div class="card">
        <div class="card-h"><div class="card-t">Service Status</div><div class="badge" id="svcBadge">Live</div></div>
        <div id="svcGrid" class="svc-grid"></div>
      </div>
      <div class="card">
        <div class="card-h"><div class="card-t">Infrastructure Metrics</div><div class="badge">Real-time</div></div>
        <table class="m-table">
          <thead><tr><th>Service</th><th>Err %</th><th>Latency</th><th>CPU</th><th>Mem</th><th>RPS</th></tr></thead>
          <tbody id="mBody"></tbody>
        </table>
      </div>
    </div>
    <div class="col">
      <div class="card">
        <div class="card-h"><div class="card-t">Incident Timeline</div><div class="badge" id="tlBadge">0 events</div></div>
        <div id="tl" class="tl">
          <div class="tl-e"><div class="tl-d i"></div><span class="tl-t">--:--:--</span><span class="tl-m">Awaiting events&hellip;</span></div>
        </div>
      </div>
      <div class="card">
        <div class="card-h"><div class="card-t">Latest Incident</div><div class="badge" id="incBadge">&mdash;</div></div>
        <div id="incDetail" class="inc">
          <div class="empty">No incidents yet.<br>Trigger one to see the full autonomous pipeline.</div>
        </div>
      </div>
    </div>
  </div>

  <div class="pipe-wrap">
    <div class="pipe-top">
      <div class="pipe-title">Sponsor Integrations</div>
      <div class="pipe-timer"><div class="td"></div><span>7 tools connected</span></div>
    </div>
    <div id="spGrid" class="sp-grid"></div>
  </div>

</div>

<script>
/* === THEME TOGGLE === */
function toggleTheme(){
  document.body.classList.toggle("light");
  localStorage.setItem("sc-theme",document.body.classList.contains("light")?"light":"dark");
}
(function(){const t=localStorage.getItem("sc-theme");if(t==="light")document.body.classList.add("light");})();

const STEPS=[
  {id:"detect",label:"Detect",icon:"\u{1F6A8}",sp:""},
  {id:"ingest",label:"Ingest",icon:"\u{1F4E1}",sp:"Airbyte"},
  {id:"analyze",label:"Analyze",icon:"\u{1F9E0}",sp:""},
  {id:"escalate",label:"Escalate LLM",icon:"\u26A1",sp:"TrueFoundry"},
  {id:"connectors",label:"Dyn Connectors",icon:"\u{1F50C}",sp:"Airbyte"},
  {id:"rootcause",label:"Root Cause",icon:"\u{1F50D}",sp:"Macroscope"},
  {id:"call",label:"Phone Call",icon:"\u{1F4DE}",sp:"Bland AI"},
  {id:"auth",label:"Auth CIBA",icon:"\u{1F512}",sp:"Auth0"},
  {id:"publish",label:"Publish",icon:"\u{1F4DD}",sp:"Ghost"},
  {id:"resolve",label:"Resolve",icon:"\u2705",sp:"Overmind"},
];
const SPONSORS=[
  {n:"Auth0",f:"CIBA + Token Vault",i:"\u{1F512}"},
  {n:"Airbyte",f:"Dynamic Connectors",i:"\u{1F4E1}"},
  {n:"Ghost",f:"Tiered Reports",i:"\u{1F4DD}"},
  {n:"Bland AI",f:"Pathway + Fn Calling",i:"\u{1F4DE}"},
  {n:"TrueFoundry",f:"Model Escalation",i:"\u26A1"},
  {n:"Macroscope",f:"PR Root Cause",i:"\u{1F50D}"},
  {n:"Overmind",f:"LLM Tracing",i:"\u{1F441}"},
];

let ps={},sparkD={},tlCount=0,pStart=null,pInt=null,curStep=0;
let orbitAngle=0,autoRotate=true,orbitRAF=null,expandedNode=null,activeNodeId=null;
const RADIUS=220;

/* Step metadata — metrics + descriptions + related nodes */
const STEP_META={
  detect:{desc:"Monitors all infrastructure metrics and detects anomalies in real-time using statistical analysis.",metric:{label:"Anomaly Confidence",value:"94%",pct:94},related:["ingest"],duration:"~2s"},
  ingest:{desc:"Airbyte dynamically ingests data from affected services with auto-configured connectors.",metric:{label:"Data Points Ingested",value:"12,847",pct:90},related:["detect","analyze"],duration:"~5s"},
  analyze:{desc:"LLM analyzes ingested data patterns and identifies root cause signals across services.",metric:{label:"Patterns Identified",value:"7 patterns",pct:85},related:["ingest","escalate"],duration:"~8s"},
  escalate:{desc:"TrueFoundry escalates to more capable models based on incident severity level.",metric:{label:"Model Tier",value:"GPT-4 Turbo",pct:75},related:["analyze","connectors"],duration:"~3s"},
  connectors:{desc:"Creates new Airbyte connectors dynamically specific to the incident type for deeper investigation.",metric:{label:"Active Connectors",value:"3 created",pct:70},related:["escalate","rootcause"],duration:"~6s"},
  rootcause:{desc:"Macroscope analyzes recent PRs via GitHub App and identifies the causal code change.",metric:{label:"PR Confidence",value:"89%",pct:89},related:["connectors","call"],duration:"~4s"},
  call:{desc:"Bland AI calls the on-call engineer with an interactive voice briefing and mid-call data queries.",metric:{label:"Call Duration",value:"2m 34s",pct:55},related:["rootcause","auth"],duration:"~15s"},
  auth:{desc:"Auth0 CIBA completes backchannel authorization via the engineer's voice approval on call.",metric:{label:"Auth Method",value:"CIBA Voice",pct:40},related:["call","publish"],duration:"~3s"},
  publish:{desc:"Ghost CMS publishes two tiered reports: executive summary and engineering deep-dive.",metric:{label:"Reports Published",value:"2 reports",pct:25},related:["auth","resolve"],duration:"~4s"},
  resolve:{desc:"Overmind traces the full agent decision path and generates optimization recommendations.",metric:{label:"Resolution Time",value:"47s",pct:100},related:["publish"],duration:"~2s"},
};

/* === ORBITAL PIPELINE (faithful to React radial-orbital-timeline) === */
function initPipe(){
  const c=document.getElementById("orbitContainer");
  c.querySelectorAll(".o-node").forEach(n=>n.remove());

  // Add orbit ring (384px like React w-96)
  let ring=c.querySelector(".orbit-ring");
  if(!ring){ring=document.createElement("div");ring.className="orbit-ring";c.appendChild(ring);}
  ring.style.width=ring.style.height=(RADIUS*2)+"px";

  STEPS.forEach((s,i)=>{
    ps[s.id]="pending";
    const meta=STEP_META[s.id]||{metric:{pct:50}};
    const auraSize=(meta.metric?meta.metric.pct:50)*0.5+48;

    const d=document.createElement("div");
    d.className="o-node pending";d.id="p-"+s.id;
    d.innerHTML=`
      <div class="o-aura" style="width:${auraSize}px;height:${auraSize}px;left:${-(auraSize-48)/2}px;top:${-(auraSize-48)/2}px;"></div>
      <div class="o-circle">${s.icon}</div>
      <div class="o-label">${s.label}</div>
    `;
    d.addEventListener("click",(e)=>{e.stopPropagation();toggleNode(s.id,i);});
    c.appendChild(d);
  });

  c.addEventListener("click",(e)=>{
    if(e.target===c||e.target.classList.contains("orbit-ring")||e.target.closest(".orbit-core")){
      dismissCard();activeNodeId=null;clearRelated();autoRotate=true;
    }
  });

  startOrbit();
}

function positionNodes(){
  const c=document.getElementById("orbitContainer");
  const cw=c.offsetWidth,ch=c.offsetHeight;
  const cx=cw/2,cy=ch/2;
  const svg=document.getElementById("orbitSvg");
  svg.setAttribute("viewBox",`0 0 ${cw} ${ch}`);
  svg.innerHTML="";

  const total=STEPS.length;
  const positions=[];

  STEPS.forEach((s,i)=>{
    const node=document.getElementById("p-"+s.id);
    if(!node)return;
    const angle=((i/total)*360+orbitAngle)%360;
    const rad=angle*Math.PI/180;
    const x=cx+RADIUS*Math.cos(rad);
    const y=cy+RADIUS*Math.sin(rad);

    // 3D depth — matches React opacity calc
    const depthFactor=(1+Math.sin(rad))/2;
    const opacity=Math.max(0.4,Math.min(1,0.4+0.6*depthFactor));
    const z=Math.round(100+50*Math.cos(rad));

    const isExpanded=expandedNode===s.id;
    node.style.left=(x-26)+"px";
    node.style.top=(y-26)+"px";
    node.style.zIndex=isExpanded?200:z;
    node.style.opacity=isExpanded?1:opacity;
    positions.push({x,y,id:s.id});
  });

  // Draw sequential flow lines connecting nodes in pipeline order
  for(let i=0;i<positions.length-1;i++){
    const a=positions[i],b=positions[i+1];
    const line=document.createElementNS("http://www.w3.org/2000/svg","line");
    line.setAttribute("x1",a.x);line.setAttribute("y1",a.y);
    line.setAttribute("x2",b.x);line.setAttribute("y2",b.y);

    const st1=ps[a.id],st2=ps[b.id];
    const isIncidentRunning=!autoRotate;

    if(st1==="complete"&&st2==="complete"){
      // Completed segment — bright teal
      line.setAttribute("stroke","rgba(20,184,166,0.6)");
      line.setAttribute("stroke-width","2.5");
      line.style.filter="drop-shadow(0 0 4px rgba(20,184,166,0.3))";
    } else if((st1==="complete"&&st2==="active")||(st1==="active"&&st2==="pending")){
      // Active edge — bright violet with glow
      line.setAttribute("stroke","rgba(139,92,246,0.7)");
      line.setAttribute("stroke-width","2.5");
      line.style.filter="drop-shadow(0 0 6px rgba(139,92,246,0.4))";
      // Add animated dash
      line.setAttribute("stroke-dasharray","8,4");
      line.style.animation="dash-flow 1s linear infinite";
    } else if(isIncidentRunning){
      // Pending segments during incident — dim but visible
      line.setAttribute("stroke","rgba(255,255,255,0.1)");
      line.setAttribute("stroke-width","1.5");
      line.setAttribute("stroke-dasharray","4,4");
    } else {
      // Idle state — subtle circle connectors
      line.setAttribute("stroke","rgba(255,255,255,0.06)");
      line.setAttribute("stroke-width","1");
    }
    svg.appendChild(line);
  }
  // Close the orbit ring line (last to first) only when idle
  if(autoRotate && positions.length>0){
    const a=positions[positions.length-1],b=positions[0];
    const line=document.createElementNS("http://www.w3.org/2000/svg","line");
    line.setAttribute("x1",a.x);line.setAttribute("y1",a.y);
    line.setAttribute("x2",b.x);line.setAttribute("y2",b.y);
    line.setAttribute("stroke","rgba(255,255,255,0.06)");
    line.setAttribute("stroke-width","1");
    svg.appendChild(line);
  }
}

function startOrbit(){
  function tick(){
    if(autoRotate)orbitAngle=(orbitAngle+0.3)%360;
    positionNodes();
    orbitRAF=requestAnimationFrame(tick);
  }
  if(orbitRAF)cancelAnimationFrame(orbitRAF);
  orbitRAF=requestAnimationFrame(tick);
}

function clearRelated(){
  document.querySelectorAll(".o-node.related").forEach(n=>{
    if(!n.classList.contains("complete")&&!n.classList.contains("active")&&!n.classList.contains("error"))
      n.className="o-node "+ps[n.id.replace("p-","")];
  });
  document.querySelectorAll(".o-aura.pulsing").forEach(a=>a.classList.remove("pulsing"));
}

function toggleNode(id,idx){
  if(expandedNode===id){
    dismissCard();activeNodeId=null;clearRelated();autoRotate=true;
    return;
  }
  dismissCard();clearRelated();
  expandedNode=id;activeNodeId=id;
  autoRotate=false;

  // Center node at top (270 deg) — matches React centerViewOnNode
  const targetAngle=(idx/STEPS.length)*360;
  orbitAngle=270-targetAngle;

  // Highlight related nodes with pulse — matches React pulseEffect
  const meta=STEP_META[id]||{related:[]};
  meta.related.forEach(relId=>{
    const relNode=document.getElementById("p-"+relId);
    if(relNode){
      relNode.classList.add("related");
      const aura=relNode.querySelector(".o-aura");
      if(aura)aura.classList.add("pulsing");
    }
  });

  // Build expanded card — matches React Card component
  const node=document.getElementById("p-"+id);
  const status=ps[id];
  const step=STEPS[idx];
  const metric=(STEP_META[id]||{metric:{label:"Metric",value:"N/A",pct:50}}).metric;
  const desc=(STEP_META[id]||{desc:""}).desc;
  const related=(STEP_META[id]||{related:[]}).related;
  const duration=(STEP_META[id]||{duration:"N/A"}).duration||"N/A";
  const statusLabel=status==="complete"?"COMPLETE":status==="active"?"IN PROGRESS":status==="error"?"ERROR":"PENDING";

  let connectedHtml="";
  if(related.length>0){
    const btns=related.map(relId=>{
      const relStep=STEPS.find(s=>s.id===relId);
      const relIdx=STEPS.findIndex(s=>s.id===relId);
      return `<button class="o-conn-btn" onclick="event.stopPropagation();toggleNode('${relId}',${relIdx})">${relStep?relStep.label:relId} <span class="o-conn-arrow">&rarr;</span></button>`;
    }).join("");
    connectedHtml=`
      <div class="o-connected">
        <div class="o-connected-head">\u{1F517} Connected Nodes</div>
        <div style="display:flex;flex-wrap:wrap;gap:4px;">${btns}</div>
      </div>`;
  }

  const card=document.createElement("div");
  card.className="o-card";card.id="ocard";
  card.innerHTML=`
    <div class="o-card-header">
      <div class="o-card-meta">
        <span class="o-card-badge ${status}">${statusLabel}</span>
        ${step.sp?`<span style="display:inline-flex;align-items:center;gap:4px;font-size:10px;padding:2px 8px;border-radius:4px;background:rgba(139,92,246,0.1);border:1px solid rgba(139,92,246,0.15);color:rgba(167,139,250,1);">${step.icon} ${step.sp}</span>`:''}
      </div>
      <div class="o-card-title">${step.label}</div>
    </div>
    <div class="o-card-body">
      <p>${desc}</p>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;padding:6px 10px;background:rgba(255,255,255,0.05);border-radius:4px;">
        <span style="font-size:10px;color:rgba(255,255,255,0.5);">Est. Duration</span>
        <span style="font-family:'Geist Mono',monospace;font-size:11px;color:rgba(255,255,255,0.8);">${duration}</span>
      </div>
      <div class="o-energy">
        <div class="o-energy-head">
          <span class="o-energy-label">\u{1F4CA} ${metric.label}</span>
          <span class="o-energy-val">${metric.value}</span>
        </div>
        <div class="o-energy-bar"><div class="o-energy-fill" style="width:${metric.pct}%"></div></div>
      </div>
      ${connectedHtml}
    </div>
  `;
  card.addEventListener("click",(e)=>e.stopPropagation());
  node.appendChild(card);
}

function dismissCard(){
  expandedNode=null;
  const old=document.getElementById("ocard");
  if(old)old.remove();
}

function updateProgress(){
  const completed=STEPS.filter(s=>ps[s.id]==="complete").length;
  const pct=Math.round((completed/STEPS.length)*100);
  document.getElementById("pProgress").style.width=pct+"%";
}

function setPS(id,st){
  ps[id]=st;
  const n=document.getElementById("p-"+id);
  if(!n)return;
  // Don't override "related" class if it's set
  if(!n.classList.contains("related"))n.className="o-node "+st;
  else n.className="o-node "+st;
  updateProgress();
}

function resetP(){
  dismissCard();clearRelated();activeNodeId=null;
  STEPS.forEach(s=>setPS(s.id,"pending"));pStart=Date.now();updT();
  if(pInt)clearInterval(pInt);pInt=setInterval(updT,100);
  document.getElementById("pTimer").className="pipe-timer on";
  autoRotate=false;
}
function stopT(){if(pInt)clearInterval(pInt);pInt=null;document.getElementById("pTimer").className="pipe-timer";}
function updT(){if(!pStart)return;document.getElementById("pTimerT").textContent=((Date.now()-pStart)/1000).toFixed(1)+"s elapsed";}

const SM={"anomaly_detection":"detect","data_ingestion":"ingest","airbyte_ingest":"ingest",
  "anomaly_analysis":"analyze","llm_analysis":"analyze","llm_escalation":"escalate",
  "truefoundry_escalation":"escalate","dynamic_connectors":"connectors","airbyte_dynamic":"connectors",
  "root_cause":"rootcause","macroscope_rca":"rootcause","phone_call":"call","bland_call":"call",
  "ciba_auth":"auth","auth0_ciba":"auth","publish_reports":"publish","ghost_publish":"publish",
  "resolution":"resolve","overmind_trace":"resolve"};
function mapS(n){return SM[n.toLowerCase().replace(/[\s-]+/g,"_")]||null;}

/* === SPONSORS === */
function initSp(){
  document.getElementById("spGrid").innerHTML=SPONSORS.map(t=>`
    <div class="sp"><div class="sp-icon">${t.i}</div><div class="sp-name">${t.n}</div><div class="sp-feat">${t.f}</div><div class="sp-dot"></div></div>
  `).join("");
}

/* === SERVICES === */
function renderSvc(services){
  const g=document.getElementById("svcGrid");
  g.innerHTML=Object.entries(services).map(([name,status])=>{
    if(!sparkD[name])sparkD[name]=Array.from({length:16},()=>10+Math.random()*20);
    else{sparkD[name].push(status==="critical"?70+Math.random()*30:status==="degraded"?40+Math.random()*20:5+Math.random()*18);if(sparkD[name].length>16)sparkD[name].shift();}
    const d=sparkD[name],mx=Math.max(...d,1);
    const col=status==="critical"?"var(--red)":status==="degraded"?"var(--orange)":"var(--teal)";
    const bars=d.map((v,i)=>`<div class="spark-b" style="height:${(v/mx)*100}%;background:${col};opacity:${(0.25+(i/d.length)*0.75).toFixed(2)}"></div>`).join("");
    return `<div class="svc ${status}"><div class="svc-top"><div class="svc-name">${name}</div><span class="svc-tag ${status}">${status}</span></div><div class="spark">${bars}</div></div>`;
  }).join("");
  const e=Object.entries(services),h=e.filter(([,s])=>s==="healthy").length;
  document.getElementById("statSvc").innerHTML=`${h}<span class="s-unit">/\u2009${e.length}</span>`;
  const sd=document.getElementById("statSvcD");
  if(h===e.length){sd.textContent="All healthy";sd.className="s-sub ok";}
  else{sd.textContent=(e.length-h)+" degraded/critical";sd.className="s-sub err";}
}

/* === TIMELINE === */
function addTL(msg,cls){
  const t=document.getElementById("tl"),now=new Date().toLocaleTimeString("en-US",{hour12:false});
  const dc=cls==="step"?"s":cls==="error"?"e":"i";
  const d=document.createElement("div");d.className="tl-e";
  d.innerHTML=`<div class="tl-d ${dc}"></div><span class="tl-t">${now}</span><span class="tl-m ${cls||''}">${msg}</span>`;
  t.prepend(d);while(t.children.length>50)t.removeChild(t.lastChild);
  tlCount++;document.getElementById("tlBadge").textContent=tlCount+" events";
}

/* === INCIDENT === */
function renderInc(inc){
  const d=document.getElementById("incDetail"),sc=inc.severity==="SEV-1"?"s1":"s2";
  const rw=(l,v)=>`<div class="inc-r"><div class="inc-l">${l}</div><div class="inc-v">${v}</div></div>`;
  let h="";
  h+=rw("Incident ID",inc.incident_id||"N/A");
  h+=rw("Service",inc.service||"N/A");
  h+=rw("Severity",`<span class="sev ${sc}">${inc.severity||"N/A"}</span>`);
  h+=rw("Status",inc.status||"N/A");
  h+=rw("Duration",inc.total_duration_seconds?`<strong>${inc.total_duration_seconds}s</strong> <span style="color:var(--text-3)">(vs 45 min avg)</span>`:"In progress\u2026");
  if(inc.model_used)h+=rw("LLM Model",inc.model_used);
  if(inc.causal_pr)h+=rw("Causal PR",`<a href="#">#${inc.causal_pr.pr_number}</a> ${inc.causal_pr.pr_title} <span class="sev s2">${inc.causal_pr.confidence}</span>`);
  if(inc.call_id)h+=rw("Bland Call",inc.call_id);
  if(inc.reports){h+=rw("Exec Report",`<a href="${inc.reports.executive_url}">${inc.reports.executive_url}</a>`);h+=rw("Eng Report",`<a href="${inc.reports.engineering_url}">${inc.reports.engineering_url}</a>`);}
  if(inc.anomaly_count!==undefined)h+=rw("Anomalies",inc.anomaly_count+" detected");
  d.innerHTML=h;
  document.getElementById("statInc").textContent=inc.incident_id?"1":"0";
  if(inc.total_duration_seconds)document.getElementById("statRes").innerHTML=inc.total_duration_seconds+'<span class="s-unit">sec</span>';
  document.getElementById("incBadge").textContent=inc.severity||"\u2014";
}

/* === METRICS === */
function renderM(metrics){
  document.getElementById("mBody").innerHTML=Object.entries(metrics).map(([svc,m])=>{
    const ec=m.error_rate>10?"v-crit":m.error_rate>3?"v-warn":"v-ok";
    const lc=m.latency_ms>3000?"v-crit":m.latency_ms>1500?"v-warn":"v-ok";
    const cc=m.cpu>90?"v-crit":m.cpu>80?"v-warn":"v-ok";
    const mc=m.memory>93?"v-crit":m.memory>80?"v-warn":"v-ok";
    return `<tr><td>${svc}</td><td class="${ec}">${m.error_rate?.toFixed(1)??"-"}%</td><td class="${lc}">${m.latency_ms?.toFixed(0)??"-"}ms</td><td class="${cc}">${m.cpu?.toFixed(0)??"-"}%</td><td class="${mc}">${m.memory?.toFixed(0)??"-"}%</td><td>${m.requests_per_sec?.toFixed(0)??"-"}</td></tr>`;
  }).join("");
}

/* === AGENT STATUS === */
function setAS(status){
  const t=document.getElementById("agentStatusText"),d=document.getElementById("agentDot");
  t.textContent=status.toUpperCase();
  if(status==="idle"){d.className="dot g";t.style.color="var(--teal)";}
  else if(status==="responding"){d.className="dot r";t.style.color="var(--red)";}
  else{d.className="dot y";t.style.color="var(--orange)";}
}

/* === TRIGGER === */
async function triggerIncident(){
  const btn=document.getElementById("triggerBtn"),st=document.getElementById("triggerStatus");
  btn.disabled=true;st.textContent="Triggering\u2026";
  addTL("Incident triggered by operator","step");setAS("responding");
  resetP();curStep=0;setPS(STEPS[0].id,"active");
  try{await fetch("/api/trigger-incident",{method:"POST"});st.textContent="Pipeline running\u2026";}
  catch(e){st.textContent="Error: "+e.message;btn.disabled=false;setAS("idle");stopT();}
}

/* === SSE === */
function connectSSE(){
  const es=new EventSource("/api/events");
  es.onmessage=function(e){
    try{
      const p=JSON.parse(e.data),ev=p.event,d=p.data;
      if(ev==="status_update"){if(d.services)renderSvc(d.services);if(d.agent_status)setAS(d.agent_status);}
      else if(ev==="metrics_update"){renderM(d);}
      else if(ev==="step_complete"){
        const sn=d.step;addTL("Step: "+sn+(d.model?" ["+d.model+"]":""),"step");
        const pid=mapS(sn);
        if(pid){setPS(pid,"complete");const idx=STEPS.findIndex(s=>s.id===pid);if(idx>=0&&idx+1<STEPS.length)setPS(STEPS[idx+1].id,"active");}
        else{if(curStep<STEPS.length){setPS(STEPS[curStep].id,"complete");curStep++;if(curStep<STEPS.length)setPS(STEPS[curStep].id,"active");}}
      }
      else if(ev==="incident_start"){addTL("INCIDENT "+d.incident_id+" on "+d.service,"error");setPS("detect","active");}
      else if(ev==="incident_resolved"){
        addTL("RESOLVED in "+d.duration_seconds+"s","step");
        STEPS.forEach(s=>setPS(s.id,"complete"));stopT();
        document.getElementById("pTimerT").textContent="Completed in "+d.duration_seconds+"s";
        document.getElementById("triggerBtn").disabled=false;
        document.getElementById("triggerStatus").textContent="Resolved";
        setAS("idle");autoRotate=true;refreshData();
      }
      else if(ev==="incident_error"){
        addTL("ERROR: "+d.error,"error");
        const a=STEPS.find(s=>ps[s.id]==="active");if(a)setPS(a.id,"error");
        stopT();document.getElementById("triggerBtn").disabled=false;setAS("idle");
      }
    }catch(err){}
  };
  es.onerror=function(){setTimeout(connectSSE,3000);};
}

/* === REFRESH === */
async function refreshData(){
  try{
    const[sr,mr,ir]=await Promise.all([fetch("/api/status"),fetch("/api/metrics"),fetch("/api/incidents")]);
    const status=await sr.json(),metrics=await mr.json(),incidents=await ir.json();
    if(status.services)renderSvc(status.services);
    if(status.agent_status)setAS(status.agent_status);
    if(status.total_incidents!==undefined)document.getElementById("statInc").textContent=status.total_incidents;
    renderM(metrics);
    if(incidents.length>0)renderInc(incidents[incidents.length-1]);
  }catch(e){}
}

window.addEventListener("resize",()=>positionNodes());
initPipe();initSp();connectSSE();refreshData();setInterval(refreshData,5000);
</script>
</body>
</html>"""


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Serve the main dashboard."""
    return DASHBOARD_HTML


# ---------------------------------------------------------------------------
# JSON API endpoints
# ---------------------------------------------------------------------------

@app.get("/api/status")
async def api_status():
    """Return current agent and service status."""
    return agent.get_status()


@app.get("/api/metrics")
async def api_metrics():
    """Return current infrastructure metrics."""
    return agent.infra.get_metrics()


@app.get("/api/incidents")
async def api_incidents():
    """Return incident history."""
    return agent.get_incident_history()


@app.post("/api/trigger-incident")
async def api_trigger_incident(background_tasks: BackgroundTasks):
    """Trigger a demo incident — runs the full pipeline in the background."""
    if agent.current_status != "idle":
        return JSONResponse(
            {"error": "Agent is already responding to an incident."},
            status_code=409,
        )
    background_tasks.add_task(_run_pipeline)
    return {"status": "triggered", "message": "Incident response pipeline started."}


@app.get("/api/agent-trace")
async def api_agent_trace():
    """Return Overmind decision trace."""
    return {
        "trace": agent.tracer.get_decision_trace(),
        "optimization": agent.tracer.get_optimization_report(),
    }


@app.get("/api/events")
async def api_events():
    """SSE endpoint for real-time dashboard updates."""
    queue = agent.subscribe()

    async def event_generator():
        try:
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield {"data": json.dumps(payload)}
                except asyncio.TimeoutError:
                    status = agent.get_status()
                    metrics = agent.infra.get_metrics()
                    yield {"data": json.dumps({
                        "event": "status_update",
                        "data": status,
                        "timestamp": time.time(),
                    })}
                    yield {"data": json.dumps({
                        "event": "metrics_update",
                        "data": metrics,
                        "timestamp": time.time(),
                    })}
        except asyncio.CancelledError:
            pass
        finally:
            agent.unsubscribe(queue)

    return EventSourceResponse(event_generator())


# ---------------------------------------------------------------------------
# Background task runner
# ---------------------------------------------------------------------------

async def _run_pipeline():
    """Execute the incident response pipeline."""
    await agent.run_incident_response()


# ---------------------------------------------------------------------------
# Serve React landing page (static export) — must be LAST so API routes win
# ---------------------------------------------------------------------------

frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "out")
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

"""SentinelCall FastAPI Dashboard — professional dark-themed incident control center.

Serves a single-page HTML dashboard with real-time SSE updates and exposes
JSON API endpoints for the agent, metrics, incidents, and Overmind trace.
"""

import asyncio
import json
import logging
import time
from typing import Any

from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
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
<title>SentinelCall — Autonomous Incident Response</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Inter:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root {
    --bg-deep: #04060e;
    --bg-base: #0a0e1a;
    --bg-surface: #0f1629;
    --bg-elevated: #151d33;
    --bg-card: rgba(15,22,41,0.7);
    --border: rgba(0,212,255,0.12);
    --border-hover: rgba(0,212,255,0.3);
    --cyan: #00d4ff;
    --cyan-dim: #00d4ff44;
    --cyan-glow: #00d4ff33;
    --green: #69f0ae;
    --green-dim: #69f0ae44;
    --green-glow: #69f0ae22;
    --red: #ff1744;
    --red-dim: #ff174444;
    --red-glow: #ff174422;
    --yellow: #ffd600;
    --yellow-dim: #ffd60044;
    --text-primary: #e8eaf6;
    --text-secondary: #8892b0;
    --text-dim: #4a5568;
  }

  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    background: var(--bg-deep);
    color: var(--text-primary);
    font-family: 'Inter', -apple-system, sans-serif;
    font-size: 14px;
    line-height: 1.6;
    min-height: 100vh;
    overflow-x: hidden;
  }

  /* Subtle grid background */
  body::before {
    content: '';
    position: fixed;
    inset: 0;
    background-image:
      linear-gradient(rgba(0,212,255,0.03) 1px, transparent 1px),
      linear-gradient(90deg, rgba(0,212,255,0.03) 1px, transparent 1px);
    background-size: 60px 60px;
    pointer-events: none;
    z-index: 0;
  }

  /* Radial glow from top */
  body::after {
    content: '';
    position: fixed;
    top: -200px;
    left: 50%;
    transform: translateX(-50%);
    width: 1200px;
    height: 600px;
    background: radial-gradient(ellipse, rgba(0,212,255,0.06) 0%, transparent 70%);
    pointer-events: none;
    z-index: 0;
  }

  /* ===== HEADER ===== */
  .header {
    position: relative;
    z-index: 10;
    background: linear-gradient(180deg, rgba(10,14,26,0.95) 0%, rgba(4,6,14,0.9) 100%);
    backdrop-filter: blur(20px);
    border-bottom: 1px solid var(--border);
    padding: 16px 40px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .header-left { display: flex; align-items: center; gap: 20px; }
  .logo {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 26px;
    font-weight: 700;
    letter-spacing: 3px;
    color: var(--cyan);
    text-shadow: 0 0 30px var(--cyan-glow);
  }
  .logo span { color: var(--green); }
  .logo-sub {
    font-size: 11px;
    color: var(--text-dim);
    letter-spacing: 2px;
    text-transform: uppercase;
    border-left: 1px solid var(--border);
    padding-left: 20px;
  }
  .header-right { display: flex; align-items: center; gap: 24px; }
  .agent-badge {
    display: flex;
    align-items: center;
    gap: 10px;
    background: rgba(0,212,255,0.06);
    border: 1px solid var(--border);
    border-radius: 100px;
    padding: 8px 20px;
  }
  .status-dot {
    width: 10px; height: 10px;
    border-radius: 50%;
    display: inline-block;
    position: relative;
  }
  .status-dot::after {
    content: '';
    position: absolute;
    inset: -3px;
    border-radius: 50%;
    animation: ripple 2s infinite;
  }
  .status-dot.green { background: var(--green); box-shadow: 0 0 12px var(--green); }
  .status-dot.green::after { border: 1px solid var(--green-dim); }
  .status-dot.red { background: var(--red); box-shadow: 0 0 12px var(--red); animation: pulse-fast 0.8s infinite; }
  .status-dot.red::after { border: 1px solid var(--red-dim); animation: ripple-fast 0.8s infinite; }
  .status-dot.yellow { background: var(--yellow); box-shadow: 0 0 12px var(--yellow); }
  .status-dot.yellow::after { border: 1px solid var(--yellow-dim); }
  .agent-label {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 2px;
    text-transform: uppercase;
  }

  @keyframes ripple {
    0% { transform: scale(1); opacity: 1; }
    100% { transform: scale(2.5); opacity: 0; }
  }
  @keyframes ripple-fast {
    0% { transform: scale(1); opacity: 1; }
    100% { transform: scale(3); opacity: 0; }
  }
  @keyframes pulse-fast { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }

  .trigger-btn {
    background: linear-gradient(135deg, #ff1744, #d50000);
    color: #fff;
    border: none;
    padding: 10px 28px;
    border-radius: 8px;
    font-family: 'Space Grotesk', sans-serif;
    font-size: 13px;
    font-weight: 700;
    cursor: pointer;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    position: relative;
    overflow: hidden;
  }
  .trigger-btn::before {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(135deg, transparent 30%, rgba(255,255,255,0.15) 50%, transparent 70%);
    transform: translateX(-100%);
    transition: transform 0.6s;
  }
  .trigger-btn:hover::before { transform: translateX(100%); }
  .trigger-btn:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 32px rgba(255,23,68,0.4), 0 0 60px rgba(255,23,68,0.15);
  }
  .trigger-btn:disabled { opacity: 0.4; cursor: not-allowed; transform: none; box-shadow: none; }
  .trigger-btn:disabled::before { display: none; }
  .trigger-status { font-size: 12px; color: var(--text-dim); }

  /* ===== MAIN CONTAINER ===== */
  .main { position: relative; z-index: 5; padding: 24px 40px 40px; }

  /* ===== PIPELINE VISUALIZATION ===== */
  .pipeline-section {
    margin-bottom: 28px;
    background: var(--bg-card);
    backdrop-filter: blur(12px);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 28px 32px;
    position: relative;
    overflow: hidden;
  }
  .pipeline-section::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 1px;
    background: linear-gradient(90deg, transparent, var(--cyan), transparent);
    opacity: 0.5;
  }
  .section-title {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 11px;
    font-weight: 600;
    color: var(--cyan);
    letter-spacing: 3px;
    text-transform: uppercase;
    margin-bottom: 24px;
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .section-title::before {
    content: '';
    width: 4px; height: 4px;
    background: var(--cyan);
    border-radius: 50%;
    box-shadow: 0 0 8px var(--cyan);
  }

  .pipeline-canvas {
    position: relative;
    width: 100%;
    height: 140px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 10px;
  }

  .pipeline-node {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
    position: relative;
    z-index: 2;
    flex: 0 0 auto;
  }
  .node-circle {
    width: 48px; height: 48px;
    border-radius: 50%;
    border: 2px solid var(--border);
    background: var(--bg-surface);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 16px;
    transition: all 0.5s cubic-bezier(0.4, 0, 0.2, 1);
    position: relative;
  }
  .node-circle::after {
    content: '';
    position: absolute;
    inset: -4px;
    border-radius: 50%;
    border: 1px solid transparent;
    transition: all 0.5s;
  }
  .pipeline-node.active .node-circle {
    border-color: var(--cyan);
    background: rgba(0,212,255,0.1);
    box-shadow: 0 0 20px var(--cyan-glow), 0 0 40px rgba(0,212,255,0.1);
  }
  .pipeline-node.active .node-circle::after {
    border-color: var(--cyan-dim);
    animation: ripple 1.5s infinite;
  }
  .pipeline-node.complete .node-circle {
    border-color: var(--green);
    background: rgba(105,240,174,0.1);
    box-shadow: 0 0 20px var(--green-glow);
  }
  .pipeline-node.error .node-circle {
    border-color: var(--red);
    background: rgba(255,23,68,0.1);
    box-shadow: 0 0 20px var(--red-glow);
    animation: pulse-fast 0.8s infinite;
  }
  .node-label {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 10px;
    font-weight: 600;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 1px;
    text-align: center;
    max-width: 80px;
    transition: color 0.5s;
  }
  .pipeline-node.active .node-label { color: var(--cyan); }
  .pipeline-node.complete .node-label { color: var(--green); }
  .node-sponsor {
    font-family: 'Inter', sans-serif;
    font-size: 9px;
    color: var(--text-dim);
    text-align: center;
    max-width: 80px;
  }

  /* Pipeline connections drawn via SVG overlay */
  .pipeline-svg {
    position: absolute;
    top: 0; left: 0;
    width: 100%;
    height: 100%;
    z-index: 1;
    pointer-events: none;
  }
  .pipeline-line {
    stroke: var(--border);
    stroke-width: 2;
    fill: none;
    transition: stroke 0.5s;
  }
  .pipeline-line.active { stroke: var(--cyan); filter: drop-shadow(0 0 4px var(--cyan-glow)); }
  .pipeline-line.complete { stroke: var(--green); filter: drop-shadow(0 0 4px var(--green-glow)); }

  /* Flowing particle on active lines */
  .particle {
    fill: var(--cyan);
    filter: drop-shadow(0 0 6px var(--cyan));
  }

  /* ===== GRID LAYOUT ===== */
  .grid-2col {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
    margin-bottom: 20px;
  }
  .grid-full { grid-column: 1 / -1; }

  /* ===== PANELS ===== */
  .panel {
    background: var(--bg-card);
    backdrop-filter: blur(12px);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 24px;
    position: relative;
    overflow: hidden;
    transition: border-color 0.3s, box-shadow 0.3s;
  }
  .panel:hover {
    border-color: var(--border-hover);
    box-shadow: 0 4px 30px rgba(0,0,0,0.3);
  }
  .panel::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 1px;
    background: linear-gradient(90deg, transparent, var(--cyan-dim), transparent);
  }
  .panel-title {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 11px;
    font-weight: 600;
    color: var(--cyan);
    letter-spacing: 3px;
    text-transform: uppercase;
    margin-bottom: 20px;
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .panel-title::before {
    content: '';
    width: 4px; height: 4px;
    background: var(--cyan);
    border-radius: 50%;
    box-shadow: 0 0 8px var(--cyan);
  }

  /* ===== SERVICE CARDS ===== */
  .service-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 12px;
  }
  .service-card {
    background: rgba(4,6,14,0.6);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 16px;
    transition: all 0.3s;
    position: relative;
    overflow: hidden;
  }
  .service-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0;
    width: 3px; height: 100%;
    border-radius: 3px 0 0 3px;
    transition: all 0.3s;
  }
  .service-card.healthy::before { background: var(--green); box-shadow: 0 0 8px var(--green-dim); }
  .service-card.degraded::before { background: var(--yellow); box-shadow: 0 0 8px var(--yellow-dim); }
  .service-card.critical::before { background: var(--red); box-shadow: 0 0 8px var(--red-dim); }
  .service-card.critical { border-color: var(--red-dim); animation: card-alert 2s infinite; }
  @keyframes card-alert {
    0%,100% { box-shadow: 0 0 0 transparent; }
    50% { box-shadow: 0 0 20px var(--red-glow); }
  }
  .service-card:hover { transform: translateY(-2px); border-color: var(--border-hover); }
  .svc-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px; }
  .svc-name {
    font-family: 'Space Grotesk', sans-serif;
    font-weight: 600;
    font-size: 13px;
    color: var(--text-primary);
  }
  .svc-badge {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1px;
    text-transform: uppercase;
    padding: 2px 8px;
    border-radius: 4px;
  }
  .svc-badge.healthy { color: var(--green); background: var(--green-dim); }
  .svc-badge.degraded { color: var(--yellow); background: var(--yellow-dim); }
  .svc-badge.critical { color: var(--red); background: var(--red-dim); }
  .svc-sparkline {
    height: 24px;
    display: flex;
    align-items: flex-end;
    gap: 2px;
    margin-top: 4px;
  }
  .spark-bar {
    flex: 1;
    min-width: 3px;
    border-radius: 2px 2px 0 0;
    transition: height 0.3s;
    opacity: 0.7;
  }

  /* ===== TIMELINE ===== */
  .timeline {
    max-height: 340px;
    overflow-y: auto;
    scrollbar-width: thin;
    scrollbar-color: var(--bg-elevated) transparent;
  }
  .timeline::-webkit-scrollbar { width: 4px; }
  .timeline::-webkit-scrollbar-track { background: transparent; }
  .timeline::-webkit-scrollbar-thumb { background: var(--bg-elevated); border-radius: 4px; }
  .tl-entry {
    padding: 10px 0;
    border-bottom: 1px solid rgba(30,41,59,0.5);
    display: flex;
    gap: 14px;
    font-size: 13px;
    align-items: flex-start;
    animation: fadeSlideIn 0.3s ease-out;
  }
  @keyframes fadeSlideIn {
    from { opacity: 0; transform: translateY(-8px); }
    to { opacity: 1; transform: translateY(0); }
  }
  .tl-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    margin-top: 5px;
    flex-shrink: 0;
  }
  .tl-dot.info { background: var(--cyan); box-shadow: 0 0 6px var(--cyan-dim); }
  .tl-dot.step { background: var(--green); box-shadow: 0 0 6px var(--green-dim); }
  .tl-dot.error { background: var(--red); box-shadow: 0 0 6px var(--red-dim); }
  .tl-time {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--text-dim);
    min-width: 70px;
    flex-shrink: 0;
  }
  .tl-msg { color: var(--text-secondary); flex: 1; }
  .tl-msg.step { color: var(--green); }
  .tl-msg.error { color: var(--red); }

  /* ===== INCIDENT DETAIL ===== */
  .incident-detail {
    max-height: 340px;
    overflow-y: auto;
    scrollbar-width: thin;
    scrollbar-color: var(--bg-elevated) transparent;
  }
  .inc-row {
    display: grid;
    grid-template-columns: 120px 1fr;
    gap: 8px;
    padding: 8px 0;
    border-bottom: 1px solid rgba(30,41,59,0.3);
    font-size: 13px;
  }
  .inc-label {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 11px;
    font-weight: 600;
    color: var(--cyan);
    letter-spacing: 1px;
    text-transform: uppercase;
  }
  .inc-value { color: var(--text-primary); }
  .inc-value a { color: var(--cyan); text-decoration: none; border-bottom: 1px solid var(--cyan-dim); }
  .inc-value a:hover { border-bottom-color: var(--cyan); }
  .severity-badge {
    display: inline-block;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    font-weight: 600;
    padding: 2px 10px;
    border-radius: 4px;
    letter-spacing: 1px;
  }
  .severity-badge.sev1 { color: var(--red); background: var(--red-dim); }
  .severity-badge.sev2 { color: var(--yellow); background: var(--yellow-dim); }

  /* ===== METRICS TABLE ===== */
  .metrics-table {
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
  }
  .metrics-table th {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 10px;
    font-weight: 600;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 1.5px;
    text-align: left;
    padding: 8px 10px;
    border-bottom: 1px solid var(--border);
  }
  .metrics-table td {
    padding: 10px 10px;
    border-bottom: 1px solid rgba(30,41,59,0.3);
    transition: background 0.2s;
  }
  .metrics-table tr:hover td { background: rgba(0,212,255,0.03); }
  .metrics-table td:first-child {
    font-family: 'Space Grotesk', sans-serif;
    font-weight: 500;
    color: var(--text-primary);
  }
  .val-ok { color: var(--green); }
  .val-warn { color: var(--yellow); }
  .val-crit { color: var(--red); font-weight: 600; }

  /* ===== SPONSOR TOOL CARDS ===== */
  .sponsor-grid {
    display: grid;
    grid-template-columns: repeat(7, 1fr);
    gap: 12px;
  }
  @media (max-width: 1200px) { .sponsor-grid { grid-template-columns: repeat(4, 1fr); } }
  .sponsor-card {
    background: rgba(4,6,14,0.6);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 20px 12px;
    text-align: center;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    position: relative;
    overflow: hidden;
  }
  .sponsor-card::after {
    content: '';
    position: absolute;
    bottom: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, transparent, var(--cyan), transparent);
    opacity: 0;
    transition: opacity 0.3s;
  }
  .sponsor-card:hover { transform: translateY(-4px); border-color: var(--border-hover); box-shadow: 0 8px 30px rgba(0,0,0,0.4); }
  .sponsor-card:hover::after { opacity: 1; }
  .sponsor-icon {
    width: 40px; height: 40px;
    border-radius: 10px;
    margin: 0 auto 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 18px;
    background: rgba(0,212,255,0.08);
    border: 1px solid var(--cyan-dim);
  }
  .sponsor-name {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 12px;
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: 4px;
  }
  .sponsor-feature {
    font-size: 10px;
    color: var(--cyan);
    letter-spacing: 0.5px;
  }
  .sponsor-status-dot {
    width: 6px; height: 6px;
    border-radius: 50%;
    background: var(--green);
    box-shadow: 0 0 6px var(--green);
    margin: 8px auto 0;
  }

  /* ===== STATS ROW ===== */
  .stats-row {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    margin-bottom: 20px;
  }
  .stat-card {
    background: var(--bg-card);
    backdrop-filter: blur(12px);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px 24px;
    transition: all 0.3s;
  }
  .stat-card:hover { border-color: var(--border-hover); }
  .stat-label {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 10px;
    font-weight: 600;
    color: var(--text-dim);
    letter-spacing: 2px;
    text-transform: uppercase;
    margin-bottom: 8px;
  }
  .stat-value {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 28px;
    font-weight: 700;
    color: var(--text-primary);
    line-height: 1;
  }
  .stat-value .stat-unit {
    font-size: 14px;
    color: var(--text-dim);
    font-weight: 400;
    margin-left: 4px;
  }
  .stat-delta {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    margin-top: 6px;
  }
  .stat-delta.good { color: var(--green); }
  .stat-delta.bad { color: var(--red); }

  /* ===== PLACEHOLDER ===== */
  .placeholder-text {
    color: var(--text-dim);
    font-size: 13px;
    text-align: center;
    padding: 40px 20px;
  }

  /* ===== RESPONSIVE ===== */
  @media (max-width: 900px) {
    .grid-2col { grid-template-columns: 1fr; }
    .stats-row { grid-template-columns: repeat(2, 1fr); }
    .sponsor-grid { grid-template-columns: repeat(3, 1fr); }
    .header { padding: 16px 20px; }
    .main { padding: 16px 20px; }
    .pipeline-canvas { overflow-x: auto; min-width: 800px; }
  }
</style>
</head>
<body>

<!-- ===== HEADER ===== -->
<div class="header">
  <div class="header-left">
    <div class="logo">SENTINEL<span>CALL</span></div>
    <div class="logo-sub">Autonomous Incident Response</div>
  </div>
  <div class="header-right">
    <div class="agent-badge">
      <span id="agentDot" class="status-dot green"></span>
      <span id="agentStatusText" class="agent-label" style="color:var(--green);">IDLE</span>
    </div>
    <span id="triggerStatus" class="trigger-status"></span>
    <button id="triggerBtn" class="trigger-btn" onclick="triggerIncident()">Trigger Incident</button>
  </div>
</div>

<div class="main">

  <!-- ===== STATS ROW ===== -->
  <div class="stats-row">
    <div class="stat-card">
      <div class="stat-label">Total Incidents</div>
      <div class="stat-value" id="statIncidents">0</div>
      <div class="stat-delta good" id="statIncidentsDelta">System nominal</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Avg Resolution</div>
      <div class="stat-value" id="statResolution">--<span class="stat-unit">sec</span></div>
      <div class="stat-delta good">vs 45min industry avg</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">LLM Gateway</div>
      <div class="stat-value" id="statGateway" style="font-size:18px;">TrueFoundry</div>
      <div class="stat-delta good" id="statGatewayMode">Cost-optimized mode</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Active Services</div>
      <div class="stat-value" id="statServices">5<span class="stat-unit">/ 5</span></div>
      <div class="stat-delta good" id="statServicesStatus">All healthy</div>
    </div>
  </div>

  <!-- ===== PIPELINE VISUALIZATION ===== -->
  <div class="pipeline-section">
    <div class="section-title">Incident Response Pipeline</div>
    <div class="pipeline-canvas" id="pipelineCanvas">
      <svg class="pipeline-svg" id="pipelineSvg"></svg>
    </div>
  </div>

  <!-- ===== TWO COLUMN LAYOUT ===== -->
  <div class="grid-2col">

    <!-- LEFT: Services + Metrics -->
    <div style="display:flex;flex-direction:column;gap:20px;">
      <div class="panel">
        <div class="panel-title">Service Status</div>
        <div id="serviceGrid" class="service-grid"></div>
      </div>
      <div class="panel">
        <div class="panel-title">Infrastructure Metrics</div>
        <table class="metrics-table">
          <thead><tr><th>Service</th><th>Err %</th><th>Latency</th><th>CPU</th><th>Mem</th><th>RPS</th></tr></thead>
          <tbody id="metricsBody"></tbody>
        </table>
      </div>
    </div>

    <!-- RIGHT: Timeline + Incident -->
    <div style="display:flex;flex-direction:column;gap:20px;">
      <div class="panel">
        <div class="panel-title">Incident Timeline</div>
        <div id="timeline" class="timeline">
          <div class="tl-entry">
            <div class="tl-dot info"></div>
            <span class="tl-time">--:--:--</span>
            <span class="tl-msg">Awaiting events...</span>
          </div>
        </div>
      </div>
      <div class="panel">
        <div class="panel-title">Latest Incident</div>
        <div id="incidentDetail" class="incident-detail">
          <div class="placeholder-text">No incidents yet. Trigger one to see the full autonomous pipeline in action.</div>
        </div>
      </div>
    </div>
  </div>

  <!-- ===== SPONSOR INTEGRATIONS ===== -->
  <div class="pipeline-section">
    <div class="section-title">Sponsor Integrations</div>
    <div id="sponsorGrid" class="sponsor-grid"></div>
  </div>

</div>

<script>
/* ===== PIPELINE CONFIG ===== */
const PIPELINE_STEPS = [
  { id: "detect",    label: "Detect",         icon: "\u{1F6A8}", sponsor: "" },
  { id: "ingest",    label: "Ingest",         icon: "\u{1F4E1}", sponsor: "Airbyte" },
  { id: "analyze",   label: "Analyze",        icon: "\u{1F9E0}", sponsor: "" },
  { id: "escalate",  label: "Escalate LLM",   icon: "\u26A1",    sponsor: "TrueFoundry" },
  { id: "connectors",label: "Dyn Connectors", icon: "\u{1F50C}", sponsor: "Airbyte" },
  { id: "rootcause", label: "Root Cause",     icon: "\u{1F50D}", sponsor: "Macroscope" },
  { id: "call",      label: "Phone Call",     icon: "\u{1F4DE}", sponsor: "Bland AI" },
  { id: "auth",      label: "Auth CIBA",      icon: "\u{1F512}", sponsor: "Auth0" },
  { id: "publish",   label: "Publish",        icon: "\u{1F4DD}", sponsor: "Ghost" },
  { id: "resolve",   label: "Resolve",        icon: "\u2705",    sponsor: "Overmind" },
];

const SPONSOR_TOOLS = [
  { name: "Auth0",        feature: "CIBA + Token Vault",       icon: "\u{1F512}" },
  { name: "Airbyte",      feature: "Dynamic Connectors",       icon: "\u{1F4E1}" },
  { name: "Ghost",        feature: "Tiered Reports",           icon: "\u{1F4DD}" },
  { name: "Bland AI",     feature: "Pathway + Fn Calling",     icon: "\u{1F4DE}" },
  { name: "TrueFoundry",  feature: "Model Escalation",         icon: "\u26A1"    },
  { name: "Macroscope",   feature: "PR Root Cause",            icon: "\u{1F50D}" },
  { name: "Overmind",     feature: "LLM Tracing",              icon: "\u{1F441}" },
];

let pipelineState = {};  // id -> "pending" | "active" | "complete" | "error"
let sparklineData = {};  // serviceName -> array of latency values

/* ===== INIT PIPELINE ===== */
function initPipeline() {
  const canvas = document.getElementById("pipelineCanvas");
  // Remove existing nodes (keep SVG)
  canvas.querySelectorAll(".pipeline-node").forEach(n => n.remove());

  PIPELINE_STEPS.forEach((step, i) => {
    pipelineState[step.id] = "pending";
    const node = document.createElement("div");
    node.className = "pipeline-node";
    node.id = "pipe-" + step.id;
    node.innerHTML = `
      <div class="node-circle">${step.icon}</div>
      <div class="node-label">${step.label}</div>
      ${step.sponsor ? '<div class="node-sponsor">' + step.sponsor + '</div>' : '<div class="node-sponsor">&nbsp;</div>'}
    `;
    canvas.appendChild(node);
  });

  // Draw connections after layout
  requestAnimationFrame(() => requestAnimationFrame(drawPipelineLines));
}

function drawPipelineLines() {
  const svg = document.getElementById("pipelineSvg");
  const canvas = document.getElementById("pipelineCanvas");
  const rect = canvas.getBoundingClientRect();
  svg.setAttribute("viewBox", `0 0 ${rect.width} ${rect.height}`);
  svg.innerHTML = "";

  const nodes = canvas.querySelectorAll(".pipeline-node");
  for (let i = 0; i < nodes.length - 1; i++) {
    const a = nodes[i].querySelector(".node-circle");
    const b = nodes[i + 1].querySelector(".node-circle");
    const aRect = a.getBoundingClientRect();
    const bRect = b.getBoundingClientRect();

    const x1 = aRect.right - rect.left;
    const y1 = aRect.top + aRect.height / 2 - rect.top;
    const x2 = bRect.left - rect.left;
    const y2 = bRect.top + bRect.height / 2 - rect.top;

    const lineId = "line-" + i;
    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("x1", x1);
    line.setAttribute("y1", y1);
    line.setAttribute("x2", x2);
    line.setAttribute("y2", y2);
    line.setAttribute("class", "pipeline-line");
    line.setAttribute("id", lineId);
    svg.appendChild(line);

    // Particle
    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("r", "3");
    circle.setAttribute("class", "particle");
    circle.setAttribute("id", "particle-" + i);
    circle.style.opacity = "0";
    svg.appendChild(circle);

    // Animate particle
    const animate = document.createElementNS("http://www.w3.org/2000/svg", "animateMotion");
    animate.setAttribute("dur", (1.5 + Math.random() * 0.5) + "s");
    animate.setAttribute("repeatCount", "indefinite");
    animate.setAttribute("path", `M${x1},${y1} L${x2},${y2}`);
    circle.appendChild(animate);
  }
}

function setPipelineStep(stepId, state) {
  pipelineState[stepId] = state;
  const node = document.getElementById("pipe-" + stepId);
  if (!node) return;
  node.className = "pipeline-node " + state;

  // Update lines and particles
  const stepIndex = PIPELINE_STEPS.findIndex(s => s.id === stepId);
  if (stepIndex > 0) {
    const line = document.getElementById("line-" + (stepIndex - 1));
    const particle = document.getElementById("particle-" + (stepIndex - 1));
    if (line) line.setAttribute("class", "pipeline-line " + (state === "complete" ? "complete" : state === "active" ? "active" : ""));
    if (particle) particle.style.opacity = state === "active" ? "1" : state === "complete" ? "0" : "0";
  }
  if (state === "active" && stepIndex < PIPELINE_STEPS.length - 1) {
    const line = document.getElementById("line-" + stepIndex);
    const particle = document.getElementById("particle-" + stepIndex);
    if (line) line.setAttribute("class", "pipeline-line active");
    if (particle) particle.style.opacity = "1";
  }
}

function resetPipeline() {
  PIPELINE_STEPS.forEach(s => setPipelineStep(s.id, "pending"));
}

/* ===== STEP NAME -> PIPELINE NODE MAPPING ===== */
const STEP_MAP = {
  "anomaly_detection": "detect",
  "data_ingestion": "ingest",
  "airbyte_ingest": "ingest",
  "anomaly_analysis": "analyze",
  "llm_analysis": "analyze",
  "llm_escalation": "escalate",
  "truefoundry_escalation": "escalate",
  "dynamic_connectors": "connectors",
  "airbyte_dynamic": "connectors",
  "root_cause": "rootcause",
  "macroscope_rca": "rootcause",
  "phone_call": "call",
  "bland_call": "call",
  "ciba_auth": "auth",
  "auth0_ciba": "auth",
  "publish_reports": "publish",
  "ghost_publish": "publish",
  "resolution": "resolve",
  "overmind_trace": "resolve",
};

function mapStepToPipeline(stepName) {
  const lower = stepName.toLowerCase().replace(/[\s-]+/g, "_");
  return STEP_MAP[lower] || null;
}

/* ===== SPONSOR GRID ===== */
function initSponsorGrid() {
  const grid = document.getElementById("sponsorGrid");
  grid.innerHTML = SPONSOR_TOOLS.map(t => `
    <div class="sponsor-card">
      <div class="sponsor-icon">${t.icon}</div>
      <div class="sponsor-name">${t.name}</div>
      <div class="sponsor-feature">${t.feature}</div>
      <div class="sponsor-status-dot"></div>
    </div>
  `).join("");
}

/* ===== SERVICE RENDERING ===== */
function renderServices(services) {
  const grid = document.getElementById("serviceGrid");
  grid.innerHTML = Object.entries(services).map(([name, status]) => {
    // Generate or update sparkline data
    if (!sparklineData[name]) sparklineData[name] = Array.from({length: 12}, () => 20 + Math.random() * 30);
    else {
      sparklineData[name].push(status === "critical" ? 80 + Math.random() * 20 : status === "degraded" ? 50 + Math.random() * 20 : 10 + Math.random() * 25);
      if (sparklineData[name].length > 12) sparklineData[name].shift();
    }
    const data = sparklineData[name];
    const max = Math.max(...data, 1);
    const barColor = status === "critical" ? "var(--red)" : status === "degraded" ? "var(--yellow)" : "var(--green)";
    const bars = data.map(v => `<div class="spark-bar" style="height:${(v/max)*100}%;background:${barColor}"></div>`).join("");

    return `
      <div class="service-card ${status}">
        <div class="svc-header">
          <div class="svc-name">${name}</div>
          <span class="svc-badge ${status}">${status}</span>
        </div>
        <div class="svc-sparkline">${bars}</div>
      </div>
    `;
  }).join("");

  // Update stats
  const entries = Object.entries(services);
  const healthy = entries.filter(([,s]) => s === "healthy").length;
  document.getElementById("statServices").innerHTML = `${healthy}<span class="stat-unit">/ ${entries.length}</span>`;
  const sd = document.getElementById("statServicesStatus");
  if (healthy === entries.length) { sd.textContent = "All healthy"; sd.className = "stat-delta good"; }
  else { sd.textContent = (entries.length - healthy) + " degraded/critical"; sd.className = "stat-delta bad"; }
}

/* ===== TIMELINE ===== */
function addTimeline(msg, cls) {
  const tl = document.getElementById("timeline");
  const now = new Date().toLocaleTimeString("en-US", {hour12: false});
  const dotCls = cls === "step" ? "step" : cls === "error" ? "error" : "info";
  const entry = document.createElement("div");
  entry.className = "tl-entry";
  entry.innerHTML = `
    <div class="tl-dot ${dotCls}"></div>
    <span class="tl-time">${now}</span>
    <span class="tl-msg ${cls || ''}">${msg}</span>
  `;
  tl.prepend(entry);
  // Keep max 50 entries
  while (tl.children.length > 50) tl.removeChild(tl.lastChild);
}

/* ===== INCIDENT DETAIL ===== */
function renderIncident(inc) {
  const d = document.getElementById("incidentDetail");
  const sevClass = inc.severity === "SEV-1" ? "sev1" : "sev2";
  let html = "";

  const row = (label, value) => `<div class="inc-row"><div class="inc-label">${label}</div><div class="inc-value">${value}</div></div>`;

  html += row("Incident ID", inc.incident_id || "N/A");
  html += row("Service", inc.service || "N/A");
  html += row("Severity", `<span class="severity-badge ${sevClass}">${inc.severity || "N/A"}</span>`);
  html += row("Status", inc.status || "N/A");
  html += row("Duration", inc.total_duration_seconds ? `<strong>${inc.total_duration_seconds}s</strong> (vs 45min industry avg)` : "In progress...");
  if (inc.model_used) html += row("LLM Model", inc.model_used);
  if (inc.causal_pr) html += row("Causal PR", `<a href="#">#${inc.causal_pr.pr_number}</a> ${inc.causal_pr.pr_title} <span class="severity-badge sev2">${inc.causal_pr.confidence}</span>`);
  if (inc.call_id) html += row("Bland Call", inc.call_id);
  if (inc.reports) {
    html += row("Exec Report", `<a href="${inc.reports.executive_url}">${inc.reports.executive_url}</a>`);
    html += row("Eng Report", `<a href="${inc.reports.engineering_url}">${inc.reports.engineering_url}</a>`);
  }
  if (inc.anomaly_count !== undefined) html += row("Anomalies", inc.anomaly_count + " detected");

  d.innerHTML = html;

  // Update stats
  document.getElementById("statIncidents").textContent = inc.incident_id ? "1" : "0";
  if (inc.total_duration_seconds) {
    document.getElementById("statResolution").innerHTML = inc.total_duration_seconds + '<span class="stat-unit">sec</span>';
  }
}

/* ===== METRICS ===== */
function renderMetrics(metrics) {
  const tbody = document.getElementById("metricsBody");
  tbody.innerHTML = Object.entries(metrics).map(([svc, m]) => {
    const errCls = m.error_rate > 10 ? "val-crit" : m.error_rate > 3 ? "val-warn" : "val-ok";
    const latCls = m.latency_ms > 3000 ? "val-crit" : m.latency_ms > 1500 ? "val-warn" : "val-ok";
    const cpuCls = m.cpu > 90 ? "val-crit" : m.cpu > 80 ? "val-warn" : "val-ok";
    const memCls = m.memory > 93 ? "val-crit" : m.memory > 80 ? "val-warn" : "val-ok";
    return `<tr>
      <td>${svc}</td>
      <td class="${errCls}">${m.error_rate?.toFixed(1) ?? "-"}%</td>
      <td class="${latCls}">${m.latency_ms?.toFixed(0) ?? "-"}ms</td>
      <td class="${cpuCls}">${m.cpu?.toFixed(0) ?? "-"}%</td>
      <td class="${memCls}">${m.memory?.toFixed(0) ?? "-"}%</td>
      <td>${m.requests_per_sec?.toFixed(0) ?? "-"}</td>
    </tr>`;
  }).join("");
}

/* ===== AGENT STATUS ===== */
function setAgentStatus(status) {
  const text = document.getElementById("agentStatusText");
  const dot = document.getElementById("agentDot");
  text.textContent = status.toUpperCase();
  if (status === "idle") {
    dot.className = "status-dot green";
    text.style.color = "var(--green)";
  } else if (status === "responding") {
    dot.className = "status-dot red";
    text.style.color = "var(--red)";
  } else {
    dot.className = "status-dot yellow";
    text.style.color = "var(--yellow)";
  }
}

/* ===== TRIGGER ===== */
let currentPipelineStep = 0;
async function triggerIncident() {
  const btn = document.getElementById("triggerBtn");
  const st = document.getElementById("triggerStatus");
  btn.disabled = true;
  st.textContent = "Triggering pipeline...";
  addTimeline("Incident triggered by operator", "step");
  setAgentStatus("responding");
  resetPipeline();
  currentPipelineStep = 0;
  setPipelineStep(PIPELINE_STEPS[0].id, "active");
  try {
    const resp = await fetch("/api/trigger-incident", {method: "POST"});
    const data = await resp.json();
    st.textContent = "Pipeline running...";
  } catch (e) {
    st.textContent = "Error: " + e.message;
    btn.disabled = false;
    setAgentStatus("idle");
  }
}

/* ===== SSE ===== */
function connectSSE() {
  const es = new EventSource("/api/events");
  es.onmessage = function(e) {
    try {
      const payload = JSON.parse(e.data);
      const ev = payload.event;
      const d = payload.data;
      if (ev === "status_update") {
        if (d.services) renderServices(d.services);
        if (d.agent_status) setAgentStatus(d.agent_status);
      } else if (ev === "metrics_update") {
        renderMetrics(d);
      } else if (ev === "step_complete") {
        const stepName = d.step;
        addTimeline("Step: " + stepName + (d.model ? " [" + d.model + "]" : ""), "step");

        // Advance pipeline
        const pipeId = mapStepToPipeline(stepName);
        if (pipeId) {
          setPipelineStep(pipeId, "complete");
          const idx = PIPELINE_STEPS.findIndex(s => s.id === pipeId);
          if (idx >= 0 && idx + 1 < PIPELINE_STEPS.length) {
            setPipelineStep(PIPELINE_STEPS[idx + 1].id, "active");
          }
        } else {
          // Fallback: advance sequentially
          if (currentPipelineStep < PIPELINE_STEPS.length) {
            setPipelineStep(PIPELINE_STEPS[currentPipelineStep].id, "complete");
            currentPipelineStep++;
            if (currentPipelineStep < PIPELINE_STEPS.length) {
              setPipelineStep(PIPELINE_STEPS[currentPipelineStep].id, "active");
            }
          }
        }
      } else if (ev === "incident_start") {
        addTimeline("INCIDENT " + d.incident_id + " on " + d.service, "error");
        setPipelineStep("detect", "active");
      } else if (ev === "incident_resolved") {
        addTimeline("RESOLVED in " + d.duration_seconds + "s", "step");
        // Complete all remaining steps
        PIPELINE_STEPS.forEach(s => setPipelineStep(s.id, "complete"));
        document.getElementById("triggerBtn").disabled = false;
        document.getElementById("triggerStatus").textContent = "Resolved";
        setAgentStatus("idle");
        refreshData();
      } else if (ev === "incident_error") {
        addTimeline("ERROR: " + d.error, "error");
        // Mark current step as error
        const activeStep = PIPELINE_STEPS.find(s => pipelineState[s.id] === "active");
        if (activeStep) setPipelineStep(activeStep.id, "error");
        document.getElementById("triggerBtn").disabled = false;
        setAgentStatus("idle");
      }
    } catch(err) {}
  };
  es.onerror = function() { setTimeout(connectSSE, 3000); };
}

/* ===== DATA REFRESH ===== */
async function refreshData() {
  try {
    const [statusResp, metricsResp, incResp] = await Promise.all([
      fetch("/api/status"), fetch("/api/metrics"), fetch("/api/incidents")
    ]);
    const status = await statusResp.json();
    const metrics = await metricsResp.json();
    const incidents = await incResp.json();
    if (status.services) renderServices(status.services);
    if (status.agent_status) setAgentStatus(status.agent_status);
    if (status.total_incidents !== undefined) document.getElementById("statIncidents").textContent = status.total_incidents;
    renderMetrics(metrics);
    if (incidents.length > 0) renderIncident(incidents[incidents.length - 1]);
  } catch(e) {}
}

/* ===== WINDOW RESIZE ===== */
window.addEventListener("resize", () => { requestAnimationFrame(drawPipelineLines); });

/* ===== INIT ===== */
initPipeline();
initSponsorGrid();
connectSSE();
refreshData();
setInterval(refreshData, 5000);
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
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
                    # Send a heartbeat with current status + metrics
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

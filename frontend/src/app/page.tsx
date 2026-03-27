"use client"

import dynamic from "next/dynamic"
import {
  Phone,
  Shield,
  FileText,
  Zap,
  Database,
  GitPullRequest,
  Eye,
  ChevronDown,
  ArrowRight,
  Code,
  Clock,
  Server,
  UserX,
  Wrench,
} from "lucide-react"

const RainingLetters = dynamic(
  () => import("@/components/ui/modern-animated-hero-section"),
  { ssr: false }
)

const tools = [
  {
    name: "Bland AI",
    icon: Phone,
    description: "Interactive two-way voice diagnosis with mid-call function calling",
    color: "#8b5cf6",
  },
  {
    name: "Auth0",
    icon: Shield,
    description: "CIBA backchannel auth via phone approval + Token Vault for secrets",
    color: "#14b8a6",
  },
  {
    name: "Ghost CMS",
    icon: FileText,
    description: "Tiered incident reports — executive summary + engineering deep-dive",
    color: "#8b5cf6",
  },
  {
    name: "TrueFoundry",
    icon: Zap,
    description: "Dynamic model escalation by severity with built-in guardrails",
    color: "#14b8a6",
  },
  {
    name: "Airbyte",
    icon: Database,
    description: "Dynamic connector creation per incident type — not pre-configured",
    color: "#8b5cf6",
  },
  {
    name: "Macroscope",
    icon: GitPullRequest,
    description: "PR-linked root cause identification via GitHub App analysis",
    color: "#14b8a6",
  },
  {
    name: "Overmind",
    icon: Eye,
    description: "Full LLM call tracing + live optimization recommendations",
    color: "#8b5cf6",
  },
]

const stats = [
  { label: "Resolution Time", value: "47s", icon: Clock, note: "vs. 45 min industry avg" },
  { label: "Uptime Target", value: "99.9%", icon: Server, note: "autonomous monitoring" },
  { label: "Human Interventions", value: "0", icon: UserX, note: "fully autonomous" },
  { label: "Integrated Tools", value: "8", icon: Wrench, note: "creative sponsor usage" },
]

export default function Home() {
  return (
    <div className="bg-black text-white min-h-screen">
      {/* Hero Section */}
      <section className="relative h-screen">
        <RainingLetters />

        {/* Scroll indicator */}
        <div className="absolute bottom-8 left-1/2 -translate-x-1/2 z-30 flex flex-col items-center gap-2 animate-bounce">
          <span className="text-gray-400 text-sm tracking-widest uppercase">Scroll</span>
          <ChevronDown className="w-6 h-6 text-gray-400" />
        </div>
      </section>

      {/* Tagline */}
      <section className="py-20 px-6 text-center">
        <h2 className="text-4xl md:text-5xl font-bold mb-6">
          <span className="text-white">Incidents resolved in </span>
          <span className="text-[#8b5cf6]">47 seconds</span>
          <span className="text-white">.</span>
        </h2>
        <p className="text-gray-400 text-lg md:text-xl max-w-2xl mx-auto leading-relaxed">
          SentinelCall is an autonomous SRE agent that monitors infrastructure, detects anomalies,
          diagnoses root cause, calls the on-call engineer via AI phone call, and publishes
          tiered incident reports — all without human intervention.
        </p>
      </section>

      {/* Feature Cards */}
      <section className="py-20 px-6 max-w-6xl mx-auto">
        <h3 className="text-2xl font-bold text-center mb-4 text-gray-300 tracking-widest uppercase">
          Integrated Tools
        </h3>
        <p className="text-gray-500 text-center mb-12 max-w-lg mx-auto">
          Every tool uses a creative, non-obvious feature — no checkbox integrations.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {tools.map((tool) => {
            const Icon = tool.icon
            return (
              <div
                key={tool.name}
                className="group relative rounded-xl border border-gray-800 bg-gray-950 p-6 transition-all duration-300 hover:border-gray-600 hover:bg-gray-900"
              >
                <div
                  className="mb-4 inline-flex items-center justify-center rounded-lg p-2.5"
                  style={{ backgroundColor: `${tool.color}15` }}
                >
                  <Icon className="w-6 h-6" style={{ color: tool.color }} />
                </div>
                <h4 className="text-lg font-semibold text-white mb-2">{tool.name}</h4>
                <p className="text-gray-400 text-sm leading-relaxed">{tool.description}</p>
                <div
                  className="absolute inset-x-0 bottom-0 h-px opacity-0 group-hover:opacity-100 transition-opacity duration-300"
                  style={{
                    background: `linear-gradient(90deg, transparent, ${tool.color}, transparent)`,
                  }}
                />
              </div>
            )
          })}
        </div>
      </section>

      {/* Stats Section */}
      <section className="py-20 px-6 border-t border-gray-800">
        <div className="max-w-5xl mx-auto grid grid-cols-2 md:grid-cols-4 gap-8">
          {stats.map((stat) => {
            const Icon = stat.icon
            return (
              <div key={stat.label} className="text-center">
                <Icon className="w-8 h-8 mx-auto mb-3 text-[#8b5cf6]" />
                <div className="text-4xl md:text-5xl font-bold text-white mb-1">{stat.value}</div>
                <div className="text-sm font-medium text-gray-300 mb-1">{stat.label}</div>
                <div className="text-xs text-gray-500">{stat.note}</div>
              </div>
            )
          })}
        </div>
      </section>

      {/* How It Works */}
      <section className="py-20 px-6 border-t border-gray-800">
        <div className="max-w-3xl mx-auto">
          <h3 className="text-2xl font-bold text-center mb-12 text-gray-300 tracking-widest uppercase">
            How It Works
          </h3>
          <div className="space-y-6">
            {[
              "Dashboard shows all services green",
              "Incident triggers — dashboard turns red",
              "Agent detects anomaly via Airbyte, escalates LLM via TrueFoundry",
              "Dynamic Airbyte connectors created to investigate",
              "Macroscope identifies the causal PR",
              "Bland AI calls on-call engineer with interactive briefing",
              "Engineer approves remediation — Auth0 CIBA completes",
              "Ghost publishes tiered incident reports",
              "Overmind shows full agent decision trace",
              "Resolution in 47 seconds",
            ].map((step, i) => (
              <div key={i} className="flex items-start gap-4">
                <div className="flex-shrink-0 w-8 h-8 rounded-full bg-[#8b5cf6]/20 text-[#8b5cf6] flex items-center justify-center text-sm font-bold">
                  {i + 1}
                </div>
                <p className="text-gray-300 pt-1">{step}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-20 px-6 border-t border-gray-800">
        <div className="max-w-2xl mx-auto text-center">
          <h3 className="text-3xl font-bold mb-4 text-white">See it in action</h3>
          <p className="text-gray-400 mb-8">
            Trigger a simulated incident and watch SentinelCall resolve it autonomously.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <a
              href="/dashboard"
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-[#8b5cf6] px-8 py-3 text-white font-semibold transition-colors hover:bg-[#7c3aed]"
            >
              <ArrowRight className="w-4 h-4" />
              Go to Dashboard
            </a>
            <a
              href="https://github.com/nihalnihalani/DAH0327"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center justify-center gap-2 rounded-lg border border-gray-700 px-8 py-3 text-gray-300 font-semibold transition-colors hover:bg-gray-900 hover:border-gray-500"
            >
              <Code className="w-4 h-4" />
              View Source
            </a>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-8 px-6 border-t border-gray-800 text-center">
        <p className="text-gray-500 text-sm">
          <span className="text-[#8b5cf6] font-semibold">SentinelCall</span>
          {" — "}Deep Agents Hackathon 2026
        </p>
      </footer>
    </div>
  )
}

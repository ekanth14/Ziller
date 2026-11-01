import React, { useState } from 'react';
import { motion } from 'framer-motion';
import {
  Terminal,
  CheckCircle2,
  Copy,
  Check,
  Cpu,
  ShieldCheck,
  Layers,
  ArrowRight,
  ExternalLink,
  Code2,
  Sparkles,
  BookOpen,
} from 'lucide-react';
import zillersEmblem from '../assets/emblem.png';

interface CodeSnippet {
  id: string;
  title: string;
  description: string;
  os: 'windows' | 'posix';
  code: string;
}

export const SetupGuide: React.FC<{ isStandalone?: boolean }> = ({ isStandalone = false }) => {
  const [copiedIndex, setCopiedIndex] = useState<string | null>(null);
  const [activeOS, setActiveOS] = useState<'windows' | 'posix'>('windows');

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedIndex(id);
    setTimeout(() => setCopiedIndex(null), 2200);
  };

  const steps = [
    {
      num: '01',
      title: 'Clone Repository from GitHub',
      desc: 'Clone the official ZILLERS repository under your local workspace.',
      windowsCmd: `git clone https://github.com/ekanth14/Ziller.git\ncd Ziller`,
      posixCmd: `git clone https://github.com/ekanth14/Ziller.git\ncd Ziller`,
    },
    {
      num: '02',
      title: 'Create & Activate Python 3.12+ Virtual Environment',
      desc: 'Isolate dependencies using Python 3.12 or newer. The core backend uses pure standard library with zero external runtime dependencies.',
      windowsCmd: `python -m venv venv\n.\\venv\\Scripts\\Activate.ps1\npip install -r requirements.txt`,
      posixCmd: `python3 -m venv venv\nsource venv/bin/activate\npip install -r requirements.txt`,
    },
    {
      num: '03',
      title: 'Build Frontend & Showcase Bundle (Optional)',
      desc: 'Compile the high-performance Vite + Tailwind showcase bundle. Pre-compiled static assets are already included in the repository.',
      windowsCmd: `npm --prefix landing install\nnpm --prefix landing run build`,
      posixCmd: `cd landing && npm install && npm run build && cd ..`,
    },
    {
      num: '04',
      title: 'Configure Optional Local Laya AI Copilot (Ollama)',
      desc: 'If running local Tier 2 deliberative AI reasoning, launch Ollama with Gemma 4 or lightweight model weights. If unavailable, the engine gracefully falls closed without crashing.',
      windowsCmd: `ollama run gemma:2b\n# Laya evaluator connects automatically to http://localhost:11434`,
      posixCmd: `ollama run gemma:2b\n# Laya evaluator connects automatically to http://localhost:11434`,
    },
    {
      num: '05',
      title: 'Launch the Institutional Trading Terminal',
      desc: 'Start the asynchronous multi-threaded WebSocket server and dashboard server on port 8900.',
      windowsCmd: `$env:ADMIN_INITIAL_PASSWORD="YourSecurePassword2026!"; python -m cryptoscope.dashboard --port 8900`,
      posixCmd: `export ADMIN_INITIAL_PASSWORD="YourSecurePassword2026!" && python3 -m cryptoscope.dashboard --port 8900`,
    },
    {
      num: '06',
      title: 'Execute Automated Verification & Test Suite',
      desc: 'Run the full institutional test suite covering 111+ tests for 5-Gate governor safeguards, scrypt auth, and microstructure calculations.',
      windowsCmd: `pytest -v`,
      posixCmd: `pytest -v`,
    },
  ];

  return (
    <section
      id="setup"
      className={`relative w-full bg-[#050505] text-[#F4F4F5] ${
        isStandalone ? 'pt-28 pb-24 px-4 sm:px-6 md:px-8' : 'py-28 px-4 sm:px-6 md:px-8 border-t border-[#38383C]'
      }`}
    >
      {/* Background illumination */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[800px] h-[350px] bg-white/[0.02] blur-3xl rounded-full" />
      </div>

      <div className="relative max-w-5xl mx-auto">
        {/* Header */}
        <div className="text-center max-w-3xl mx-auto mb-16 space-y-4">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-[#4D4D51] bg-[#151515] text-[11px] font-mono tracking-wider uppercase text-[#D8D8DC]">
            <BookOpen className="w-3.5 h-3.5 text-[#F4F4F5]" />
            <span>Developer Documentation · Setup Guide</span>
          </div>

          <h2 className="text-3xl sm:text-5xl md:text-6xl font-semibold tracking-[-0.03em] text-metallic leading-tight">
            Installation and setup.
          </h2>

          <p className="text-sm sm:text-base text-[#A2A2A8] font-light leading-relaxed">
            Get ZILLERS running locally in minutes. Follow this step-by-step engineering guide to configure
            market data ingestion, local Laya AI multi-agent deliberation, and the tactical trading terminal.
          </p>

          {/* OS Switcher */}
          <div className="pt-4 flex justify-center">
            <div className="inline-flex items-center gap-1 p-1 rounded-xl bg-[#151515] border border-[#38383C]">
              <button
                type="button"
                onClick={() => setActiveOS('windows')}
                className={`px-4 py-1.5 rounded-lg text-xs font-mono transition-all ${
                  activeOS === 'windows'
                    ? 'bg-[#222224] text-white font-semibold border border-[#4D4D51] shadow'
                    : 'text-[#A2A2A8] hover:text-white'
                }`}
              >
                Windows (PowerShell)
              </button>
              <button
                type="button"
                onClick={() => setActiveOS('posix')}
                className={`px-4 py-1.5 rounded-lg text-xs font-mono transition-all ${
                  activeOS === 'posix'
                    ? 'bg-[#222224] text-white font-semibold border border-[#4D4D51] shadow'
                    : 'text-[#A2A2A8] hover:text-white'
                }`}
              >
                Linux / macOS (Bash)
              </button>
            </div>
          </div>
        </div>

        {/* Prerequisites Banner */}
        <div className="mb-12 p-6 rounded-2xl border border-[#38383C] bg-[#090909] grid grid-cols-1 md:grid-cols-3 gap-6 font-mono text-xs">
          <div className="space-y-1">
            <span className="text-[#A2A2A8] text-[10px] uppercase">PREREQUISITE 01</span>
            <div className="text-sm font-bold text-white">Python 3.12+</div>
            <p className="text-[#A2A2A8] text-[11px] font-sans">
              Pure stdlib backend. Built-in SQLite, scrypt hashing, and asyncio feeds.
            </p>
          </div>
          <div className="space-y-1">
            <span className="text-[#A2A2A8] text-[10px] uppercase">PREREQUISITE 02</span>
            <div className="text-sm font-bold text-white">Node.js 18+ (Optional)</div>
            <p className="text-[#A2A2A8] text-[11px] font-sans">
              Required only if modifying or recompiling the Vite + Tailwind showcase.
            </p>
          </div>
          <div className="space-y-1">
            <span className="text-[#A2A2A8] text-[10px] uppercase">PREREQUISITE 03</span>
            <div className="text-sm font-bold text-white">Ollama (Optional)</div>
            <p className="text-[#A2A2A8] text-[11px] font-sans">
              Required for local Tier 2 Laya AI deliberation. Falls closed safely if offline.
            </p>
          </div>
        </div>

        {/* Step-by-Step Instructions */}
        <div className="space-y-6">
          {steps.map((step) => {
            const cmd = activeOS === 'windows' ? step.windowsCmd : step.posixCmd;
            const isCopied = copiedIndex === step.num;

            return (
              <motion.div
                key={step.num}
                initial={{ opacity: 0, y: 15 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: '-40px' }}
                transition={{ duration: 0.4 }}
                className="rounded-2xl border border-[#38383C] bg-[#090909] p-5 sm:p-6 space-y-4 hover:border-[#4D4D51] transition-colors"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-mono font-bold text-[#A2A2A8] px-2 py-0.5 rounded bg-[#151515] border border-[#38383C]">
                        STEP {step.num}
                      </span>
                      <h3 className="text-base sm:text-lg font-semibold text-white tracking-tight">
                        {step.title}
                      </h3>
                    </div>
                    <p className="text-xs sm:text-sm text-[#A2A2A8] font-light leading-relaxed">
                      {step.desc}
                    </p>
                  </div>
                </div>

                {/* Code Terminal Box */}
                <div className="relative rounded-xl border border-[#222224] bg-[#050505] overflow-hidden group">
                  <div className="flex items-center justify-between px-3.5 py-2 border-b border-[#222224] bg-[#111319] text-[11px] font-mono text-[#A2A2A8]">
                    <div className="flex items-center gap-2">
                      <Terminal className="w-3.5 h-3.5 text-[#D8D8DC]" />
                      <span>{activeOS === 'windows' ? 'PowerShell' : 'Terminal / Bash'}</span>
                    </div>

                    <button
                      type="button"
                      onClick={() => copyToClipboard(cmd, step.num)}
                      className="inline-flex items-center gap-1.5 text-xs text-[#A2A2A8] hover:text-white px-2 py-0.5 rounded hover:bg-[#222224] transition-colors"
                    >
                      {isCopied ? (
                        <>
                          <Check className="w-3.5 h-3.5 text-emerald-400" />
                          <span className="text-emerald-400 text-[10px]">Copied</span>
                        </>
                      ) : (
                        <>
                          <Copy className="w-3.5 h-3.5" />
                          <span className="text-[10px]">Copy</span>
                        </>
                      )}
                    </button>
                  </div>

                  <pre className="p-4 text-xs font-mono text-[#F4F4F5] overflow-x-auto whitespace-pre leading-relaxed">
                    <code>{cmd}</code>
                  </pre>
                </div>
              </motion.div>
            );
          })}
        </div>

        {/* Operational Guidelines & Safety Callout */}
        <div className="mt-12 p-6 rounded-3xl border border-[#4D4D51] bg-[#151515] space-y-4">
          <div className="flex items-center gap-2 text-xs font-mono uppercase tracking-wider text-white">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            <span>Deterministic Safety & 5-Gate Governance</span>
          </div>

          <p className="text-xs text-[#A2A2A8] leading-relaxed">
            By default, ZILLERS starts in **Paper Trading Mode** with simulated execution and zero risk to real capital.
            The **5-Gate Risk Governor** prevents live execution until your strategies have been forward-tested across 28+ calendar days,
            completed 100+ simulated trades, and verified statistical significance under Deflated Sharpe Ratio (DSR &ge; 0.95).
          </p>

          <div className="pt-2 flex flex-wrap items-center gap-4 text-xs font-mono">
            <a
              href="/"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-full bg-[#F4F4F5] text-[#050505] font-semibold hover:bg-white transition-all shadow"
            >
              <span>Launch Live Terminal Enclave</span>
              <ExternalLink className="w-3.5 h-3.5" />
            </a>

            <a
              href="#collaborate"
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-full border border-[#4D4D51] bg-[#151515] text-[#D8D8DC] hover:text-white hover:border-white transition-all"
            >
              <span>Submit Research Collaboration</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </a>
          </div>
        </div>
      </div>
    </section>
  );
};

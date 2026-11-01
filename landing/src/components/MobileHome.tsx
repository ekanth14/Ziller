import React, { useState } from 'react';
import {
  Monitor,
  Copy,
  Check,
  ExternalLink,
  Shield,
  Zap,
  Brain,
  BarChart3,
  Database,
  Terminal,
  Send,
  Lock,
  ArrowRight,
  ChevronDown,
  HelpCircle,
  CheckCircle2,
  AlertCircle
} from 'lucide-react';
import zillersEmblem from '../assets/emblem.png';

interface MobileHomeProps {
  onSwitchToDesktop?: () => void;
}

export const MobileHome: React.FC<MobileHomeProps> = ({ onSwitchToDesktop }) => {
  const [copiedLink, setCopiedLink] = useState(false);
  const [copiedCode, setCopiedCode] = useState(false);
  const [openFaq, setOpenFaq] = useState<number | null>(null);

  // Collab form state
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [github, setGithub] = useState('');
  const [track, setTrack] = useState('Quantitative Strategy Research');
  const [message, setMessage] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitSuccess, setSubmitSuccess] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const handleCopyLink = () => {
    navigator.clipboard.writeText('https://zillers.zienorganisation.online/').then(() => {
      setCopiedLink(true);
      setTimeout(() => setCopiedLink(false), 2500);
    });
  };

  const setupCommands = `git clone https://github.com/ekanth14/Ziller.git
cd Ziller
python -m venv .venv
source .venv/bin/activate
pip install -e .
python -m cryptoscope.dashboard --port 8900`;

  const handleCopyCode = () => {
    navigator.clipboard.writeText(setupCommands).then(() => {
      setCopiedCode(true);
      setTimeout(() => setCopiedCode(false), 2500);
    });
  };

  const handleSubmitProposal = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!fullName.trim() || !email.trim() || !github.trim() || !message.trim()) {
      setSubmitError('Please fill in all required fields (Name, Email, GitHub, Message).');
      return;
    }

    setIsSubmitting(true);
    setSubmitError(null);

    try {
      const res = await fetch('/api/collaborate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: fullName.trim(),
          email: email.trim(),
          github: github.trim(),
          track,
          message: message.trim(),
        }),
      });

      const data = await res.json();
      if (res.ok && (data.collab_id || data.success)) {
        setSubmitSuccess(data.collab_id || 'REGISTERED');
        setFullName('');
        setEmail('');
        setGithub('');
        setMessage('');
      } else {
        setSubmitError(data.error || 'Failed to submit proposal. Please try again.');
      }
    } catch (err: any) {
      setSubmitError(err?.message || 'Network error submitting proposal.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const coreModules = [
    {
      num: '01',
      title: 'Quantitative Strategy Research',
      icon: BarChart3,
      metric: 'DSR 0.98',
      desc: 'Statistical validation using Deflated Sharpe Ratio (DSR) to control for data-snooping bias across multiple trial iterations.',
    },
    {
      num: '02',
      title: 'Real-Time Crypto Market Overview',
      icon: Database,
      metric: '100+ Pairs',
      desc: 'Multi-exchange tick ingest and order-book depth streaming from Binance, Coinbase, and Kraken simultaneously.',
    },
    {
      num: '03',
      title: 'Algorithmic Execution Engine',
      icon: Zap,
      metric: '< 20 ms',
      desc: 'Deterministic execution pipeline tracking Smart Money Concepts (SMC), Fair Value Gaps (FVG), and VWAP mean reversion.',
    },
    {
      num: '04',
      title: 'Laya AI Deliberative Committee',
      icon: Brain,
      metric: 'Local LLM',
      desc: 'Multi-agent local LLM deliberation committee evaluating trade proposals with strict JSON schema compliance before risk submission.',
    },
    {
      num: '05',
      title: '5-Gate Risk Governance',
      icon: Shield,
      metric: 'Zero-Breach',
      desc: 'Mathematical position limits, max account drawdown tripwires, and hardkill execution switches enforcing capital protection.',
    },
  ];

  const mobileFaqs = [
    {
      q: 'What is ZILLERS?',
      a: 'ZILLERS is a quantitative crypto trading platform engineered by Ekanth B S under Zien Organisation. It provides sub-20ms deterministic execution, SMC/FVG strategies, and local Laya AI risk deliberation.',
    },
    {
      q: 'Who built ZILLERS?',
      a: 'ZILLERS was conceived, engineered, and built by Ekanth B S under parent company Zien Organisation (ziennexus.app).',
    },
    {
      q: 'Is ZILLERS free?',
      a: 'Yes, 100% free and open-source with a $0.00 subscription cost. The code is available at github.com/ekanth14/Ziller.',
    },
    {
      q: 'What is Laya AI?',
      a: 'Laya AI is an offline local multi-agent LLM committee that validates trade setups with strict JSON schema compliance before risk submission.',
    },
  ];

  return (
    <div className="min-h-screen bg-[#050505] text-[#F4F4F5] selection:bg-[#38383C] selection:text-white font-sans pb-16">
      {/* 1. INSTITUTIONAL DESKTOP NOTICE CALLOUT (TOP BANNER) */}
      <div className="bg-[#111113] border-b border-[#38383C] px-4 py-3 sticky top-0 z-50 backdrop-blur-md bg-opacity-95">
        <div className="flex items-start gap-3">
          <div className="p-1.5 rounded-lg bg-[#1F1F23] border border-[#4D4D51] text-amber-300 mt-0.5 shrink-0">
            <Monitor className="w-4 h-4" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-mono uppercase tracking-wider text-amber-300 font-semibold">
                Recommended Display
              </span>
              <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-[#222226] text-[#A2A2A8]">
                PC / Laptop
              </span>
            </div>
            <p className="text-[12px] text-[#D8D8DC] leading-snug mt-1">
              For the full interactive quantitative trading terminal, live charts, and detailed workspace diagrams, open{' '}
              <strong className="text-white font-semibold">ZILLERS on a laptop or desktop PC</strong>.
            </p>
            <div className="flex items-center gap-2 mt-2">
              <button
                type="button"
                onClick={handleCopyLink}
                className="inline-flex items-center gap-1.5 text-[11px] font-mono px-2.5 py-1 rounded-md bg-[#222226] border border-[#4D4D51] text-[#F4F4F5] hover:bg-[#2C2C32] transition-colors"
              >
                {copiedLink ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3 text-[#A2A2A8]" />}
                <span>{copiedLink ? 'Link Copied!' : 'Copy Site URL'}</span>
              </button>
              {onSwitchToDesktop && (
                <button
                  type="button"
                  onClick={onSwitchToDesktop}
                  className="text-[11px] font-mono text-[#A2A2A8] hover:text-white transition-colors underline-offset-2 hover:underline"
                >
                  View Desktop Layout
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* 2. MOBILE HERO & BRAND */}
      <header className="px-5 pt-8 pb-6 border-b border-[#1E1E22]">
        <div className="flex items-center gap-3 mb-4">
          <img
            src={zillersEmblem}
            alt="ZILLERS"
            className="w-9 h-9 object-contain rounded-xl border border-[#38383C] bg-[#121214] p-1"
            onError={(e) => {
              (e.target as HTMLElement).style.display = 'none';
            }}
          />
          <div>
            <div className="text-[10px] font-mono tracking-widest text-[#A2A2A8] uppercase">
              Quantitative Systems
            </div>
            <h1 className="text-xl font-bold tracking-tight text-white uppercase font-mono">
              ZILLERS
            </h1>
          </div>
        </div>

        <p className="text-sm text-[#A2A2A8] leading-relaxed">
          Precision-engineered quantitative crypto execution, deterministic algorithmic rulebooks, and local deliberative AI.
        </p>

        {/* Feature Pills */}
        <div className="flex flex-wrap gap-2 mt-4">
          <span className="text-[10px] font-mono px-2.5 py-1 rounded-full bg-[#18181B] border border-[#38383C] text-[#E4E4E7]">
            0.00% Free
          </span>
          <span className="text-[10px] font-mono px-2.5 py-1 rounded-full bg-[#18181B] border border-[#38383C] text-[#E4E4E7]">
            Open Source
          </span>
          <span className="text-[10px] font-mono px-2.5 py-1 rounded-full bg-[#18181B] border border-[#38383C] text-[#E4E4E7]">
            Sub-20ms SOR
          </span>
          <span className="text-[10px] font-mono px-2.5 py-1 rounded-full bg-[#18181B] border border-[#38383C] text-[#E4E4E7]">
            Local Laya AI
          </span>
        </div>

        <div className="flex gap-2.5 mt-5">
          <a
            href="#mobile-collaborate"
            className="flex-1 text-center py-2.5 px-3 rounded-xl bg-white text-black text-xs font-semibold hover:bg-[#E4E4E7] transition-colors"
          >
            Collaborate
          </a>
          <a
            href="#mobile-faq"
            className="flex-1 text-center py-2.5 px-3 rounded-xl bg-[#18181B] border border-[#38383C] text-xs font-mono text-[#D8D8DC] hover:text-white transition-colors"
          >
            FAQs
          </a>
        </div>
      </header>

      {/* 3. ABOUT ZILLERS & PROVENANCE (STRICTLY NO UNDERLINES) */}
      <section className="px-5 py-7 border-b border-[#1E1E22]">
        <div className="text-[10px] font-mono text-[#A2A2A8] uppercase tracking-wider mb-2">
          Venture Provenance · About
        </div>
        <h2 className="text-lg font-bold text-white mb-3 tracking-tight">
          Beyond Conventional Trading.
        </h2>
        <p className="text-xs text-[#A2A2A8] leading-relaxed mb-4">
          ZILLERS is a quantitative financial technology venture under{' '}
          <a
            href="https://ziennexus.app/"
            target="_blank"
            rel="noopener noreferrer"
            className="font-bold text-white hover:text-[#D8D8DC] transition-colors"
            title="Visit Zien Organisation (ziennexus.app)"
          >
            Zien Organisation
          </a>
          , focused on developing accessible trading research, algorithmic automation, and intelligent cryptocurrency market analysis.
        </p>

        {/* Lead Engineer Card */}
        <div className="p-3.5 rounded-xl bg-[#121214] border border-[#38383C]">
          <div className="text-[10px] font-mono uppercase tracking-wider text-[#A2A2A8] mb-1">
            Lead Quantitative Systems Engineer
          </div>
          <div className="flex items-center justify-between">
            <span className="text-xs text-[#D8D8DC]">
              Conceived, engineered, and built by{' '}
              <a
                href="https://github.com/ekanth14"
                target="_blank"
                rel="noopener noreferrer"
                className="font-bold text-white hover:text-[#D8D8DC] transition-colors inline-block"
              >
                Ekanth B S
              </a>
            </span>
            <a
              href="https://github.com/ekanth14"
              target="_blank"
              rel="noopener noreferrer"
              className="p-1 text-[#A2A2A8] hover:text-white"
            >
              <ExternalLink className="w-3.5 h-3.5" />
            </a>
          </div>
        </div>
      </section>

      {/* 4. CORE TECHNICAL CAPABILITIES (CLEAN, NO HEAVY PICTOGRAPHY) */}
      <section className="px-5 py-7 border-b border-[#1E1E22]">
        <div className="text-[10px] font-mono text-[#A2A2A8] uppercase tracking-wider mb-2">
          Architecture Highlights
        </div>
        <h2 className="text-lg font-bold text-white mb-4 tracking-tight">
          Deterministic Quantitative Engines
        </h2>

        <div className="space-y-3">
          {coreModules.map((m) => {
            const Icon = m.icon;
            return (
              <div
                key={m.num}
                className="p-3.5 rounded-xl bg-[#0D0D0E] border border-[#27272A] hover:border-[#38383C] transition-colors"
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <div className="p-1 rounded-md bg-[#18181B] text-[#D8D8DC]">
                      <Icon className="w-3.5 h-3.5" />
                    </div>
                    <span className="text-xs font-semibold text-white">{m.title}</span>
                  </div>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#18181B] border border-[#38383C] text-emerald-400">
                    {m.metric}
                  </span>
                </div>
                <p className="text-[11px] text-[#A2A2A8] leading-relaxed">
                  {m.desc}
                </p>
              </div>
            );
          })}
        </div>
      </section>

      {/* 5. QUICK SETUP GUIDE (TERMINAL SNIPPET) */}
      <section id="mobile-setup" className="px-5 py-7 border-b border-[#1E1E22]">
        <div className="text-[10px] font-mono text-[#A2A2A8] uppercase tracking-wider mb-2">
          Getting Started · Installation
        </div>
        <h2 className="text-lg font-bold text-white mb-2 tracking-tight">
          Run ZILLERS Locally
        </h2>
        <p className="text-xs text-[#A2A2A8] mb-4">
          Clone the open-source repository and launch the deterministic trading server in seconds.
        </p>

        <div className="rounded-xl bg-[#0A0A0C] border border-[#27272A] overflow-hidden">
          <div className="flex items-center justify-between px-3 py-2 bg-[#121214] border-b border-[#27272A]">
            <span className="text-[10px] font-mono text-[#A2A2A8]">terminal / bash</span>
            <button
              type="button"
              onClick={handleCopyCode}
              className="inline-flex items-center gap-1 text-[10px] font-mono text-[#A2A2A8] hover:text-white"
            >
              {copiedCode ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
              <span>{copiedCode ? 'Copied' : 'Copy'}</span>
            </button>
          </div>
          <pre className="p-3 text-[11px] font-mono text-[#D8D8DC] overflow-x-auto leading-relaxed">
            <code>{setupCommands}</code>
          </pre>
        </div>

        <div className="mt-3 text-[11px] text-[#A2A2A8] font-mono">
          Repo: <a href="https://github.com/ekanth14/Ziller" target="_blank" rel="noopener noreferrer" className="text-white font-bold hover:text-[#D8D8DC]">github.com/ekanth14/Ziller</a>
        </div>
      </section>

      {/* 6. AEO MOBILE FAQ ACCORDION (ANSWER ENGINE OPTIMIZATION) */}
      <section id="mobile-faq" className="px-5 py-7 border-b border-[#1E1E22]">
        <div className="text-[10px] font-mono text-[#A2A2A8] uppercase tracking-wider mb-2 flex items-center gap-1.5">
          <HelpCircle className="w-3 h-3 text-amber-300" />
          <span>Knowledge Base · FAQ</span>
        </div>
        <h2 className="text-lg font-bold text-white mb-3 tracking-tight">
          Frequently Asked Questions
        </h2>

        <div className="space-y-2.5">
          {mobileFaqs.map((faq, i) => {
            const isOpen = openFaq === i;
            return (
              <div key={i} className="rounded-xl bg-[#0D0D0E] border border-[#27272A] overflow-hidden">
                <button
                  type="button"
                  onClick={() => setOpenFaq(isOpen ? null : i)}
                  className="w-full p-3.5 text-left flex items-center justify-between gap-3"
                >
                  <span className="text-xs font-semibold text-white">{faq.q}</span>
                  <ChevronDown className={`w-3.5 h-3.5 text-[#A2A2A8] transition-transform ${isOpen ? 'rotate-180 text-white' : ''}`} />
                </button>
                {isOpen && (
                  <div className="px-3.5 pb-3.5 text-[11px] text-[#A2A2A8] leading-relaxed border-t border-[#18181B] pt-2.5">
                    {faq.a}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      {/* 7. COLLABORATE & PROPOSALS DESK */}
      <section id="mobile-collaborate" className="px-5 py-7 border-b border-[#1E1E22]">
        <div className="text-[10px] font-mono text-[#A2A2A8] uppercase tracking-wider mb-2">
          Research Intakes · Partnerships
        </div>
        <h2 className="text-lg font-bold text-white mb-2 tracking-tight">
          Collaborate with ZILLERS
        </h2>
        <p className="text-xs text-[#A2A2A8] mb-4 leading-relaxed">
          Submit algorithmic research or trading infrastructure proposals directly to the engineering team.
        </p>

        {submitSuccess ? (
          <div className="p-4 rounded-xl bg-emerald-950/30 border border-emerald-800/50 text-emerald-300">
            <div className="flex items-center gap-2 mb-1.5">
              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              <span className="text-xs font-semibold">Proposal Successfully Registered</span>
            </div>
            <p className="text-[11px] text-emerald-400/90 leading-relaxed font-mono">
              Reference ID: {submitSuccess}. The ZILLERS research group will review your submission and reach out via email.
            </p>
            <button
              type="button"
              onClick={() => setSubmitSuccess(null)}
              className="mt-3 text-xs font-mono text-white underline underline-offset-2"
            >
              Submit another proposal
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmitProposal} className="space-y-3">
            {submitError && (
              <div className="p-2.5 rounded-lg bg-rose-950/40 border border-rose-800/50 text-rose-300 text-xs flex items-center gap-2">
                <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                <span>{submitError}</span>
              </div>
            )}

            <div>
              <label className="block text-[10px] font-mono uppercase text-[#A2A2A8] mb-1">
                Full Name / Moniker *
              </label>
              <input
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Dr. Jane Doe / Quant14"
                className="w-full px-3 py-2 rounded-lg bg-[#121214] border border-[#27272A] text-xs text-white placeholder-[#555] focus:outline-none focus:border-[#4D4D51]"
                required
              />
            </div>

            <div>
              <label className="block text-[10px] font-mono uppercase text-[#A2A2A8] mb-1">
                Email Address *
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="researcher@institution.edu"
                className="w-full px-3 py-2 rounded-lg bg-[#121214] border border-[#27272A] text-xs text-white placeholder-[#555] focus:outline-none focus:border-[#4D4D51]"
                required
              />
            </div>

            <div>
              <label className="block text-[10px] font-mono uppercase text-[#A2A2A8] mb-1">
                GitHub Profile URL *
              </label>
              <input
                type="text"
                value={github}
                onChange={(e) => setGithub(e.target.value)}
                placeholder="https://github.com/your-username"
                className="w-full px-3 py-2 rounded-lg bg-[#121214] border border-[#27272A] text-xs text-white placeholder-[#555] focus:outline-none focus:border-[#4D4D51]"
                required
              />
            </div>

            <div>
              <label className="block text-[10px] font-mono uppercase text-[#A2A2A8] mb-1">
                Focus Track
              </label>
              <select
                value={track}
                onChange={(e) => setTrack(e.target.value)}
                className="w-full px-3 py-2 rounded-lg bg-[#121214] border border-[#27272A] text-xs text-white focus:outline-none focus:border-[#4D4D51]"
              >
                <option value="Quantitative Strategy Research">Quantitative Strategy Research</option>
                <option value="Laya AI & Multi-Agent Deliberation">Laya AI & Deliberation Architecture</option>
                <option value="Execution & Low-Latency SOR">Execution Infrastructure & SOR</option>
                <option value="Risk Engineering & 5-Gate Governance">Risk Governance & Safeguards</option>
                <option value="Institutional Frontend & Data Viz">Institutional UI & Visualization</option>
              </select>
            </div>

            <div>
              <label className="block text-[10px] font-mono uppercase text-[#A2A2A8] mb-1">
                Proposal & Statement *
              </label>
              <textarea
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                rows={3}
                placeholder="Summarize your quantitative focus or architectural suggestion..."
                className="w-full px-3 py-2 rounded-lg bg-[#121214] border border-[#27272A] text-xs text-white placeholder-[#555] focus:outline-none focus:border-[#4D4D51]"
                required
              />
            </div>

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full py-2.5 rounded-xl bg-white text-black text-xs font-semibold hover:bg-[#E4E4E7] transition-all flex items-center justify-center gap-1.5 disabled:opacity-50"
            >
              <Send className="w-3.5 h-3.5" />
              <span>{isSubmitting ? 'Registering Proposal...' : 'Transmit Collaboration Proposal'}</span>
            </button>
          </form>
        )}

        {/* Passcode Protected Desk Entry */}
        <div className="mt-5 p-3.5 rounded-xl bg-[#121214] border border-[#27272A]">
          <div className="flex items-center gap-2 mb-1.5">
            <Lock className="w-3.5 h-3.5 text-amber-300" />
            <span className="text-xs font-semibold text-white">Operator Proposals Desk</span>
          </div>
          <p className="text-[11px] text-[#A2A2A8] leading-relaxed mb-3">
            Review submitted proposals and export datasets. Protected by institutional passcode.
          </p>
          <a
            href="/collaborations"
            className="inline-flex items-center gap-1.5 text-xs font-mono text-amber-300 hover:text-amber-200 transition-colors"
          >
            <span>Open Submissions Desk (Ekanthbs@4514)</span>
            <ArrowRight className="w-3 h-3" />
          </a>
        </div>
      </section>

      {/* 8. SECONDARY PC/LAPTOP RECOMMENDATION & FOOTER */}
      <footer className="px-5 pt-8">
        <div className="p-4 rounded-2xl bg-[#0F0F12] border border-[#38383C] text-center mb-6">
          <Monitor className="w-5 h-5 text-amber-300 mx-auto mb-2" />
          <h3 className="text-xs font-bold text-white uppercase font-mono tracking-wider mb-1">
            Experience Full Quantitative Terminal
          </h3>
          <p className="text-[11px] text-[#A2A2A8] leading-relaxed mb-3">
            Interactive multi-exchange order books, live charts, and full research models require a desktop or laptop display.
          </p>
          <button
            type="button"
            onClick={handleCopyLink}
            className="inline-flex items-center gap-1.5 text-xs font-mono px-3 py-1.5 rounded-lg bg-white text-black font-semibold hover:bg-[#E4E4E7] transition-colors"
          >
            {copiedLink ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5 text-black" />}
            <span>{copiedLink ? 'Link Copied' : 'Copy Link for Desktop'}</span>
          </button>
        </div>

        {onSwitchToDesktop && (
          <div className="text-center mb-6">
            <button
              type="button"
              onClick={onSwitchToDesktop}
              className="text-xs font-mono text-[#A2A2A8] hover:text-white transition-colors py-1.5 px-3 rounded-lg border border-[#27272A]"
            >
              Switch to Full Desktop View
            </button>
          </div>
        )}

        {/* Machine-Readable Specs */}
        <div className="text-center pb-4 text-[10px] font-mono text-[#777] flex items-center justify-center gap-3">
          <a href="/llms.txt" target="_blank" rel="noopener noreferrer" className="text-amber-400 hover:text-amber-300">
            llms.txt (GEO)
          </a>
          <span>·</span>
          <a href="/sitemap.xml" target="_blank" rel="noopener noreferrer" className="hover:text-white">
            sitemap.xml
          </a>
          <span>·</span>
          <a href="/robots.txt" target="_blank" rel="noopener noreferrer" className="hover:text-white">
            robots.txt
          </a>
        </div>

        <div className="text-[10px] font-mono text-[#777] leading-relaxed space-y-2 border-t border-[#1E1E22] pt-6">
          <p>
            Regulatory Disclaimer: ZILLERS is a quantitative financial technology research venture under{' '}
            <a
              href="https://ziennexus.app/"
              target="_blank"
              rel="noopener noreferrer"
              className="font-bold text-white hover:text-[#D8D8DC] transition-colors"
            >
              Zien Organisation
            </a>
            . Models, metrics, and software are for research and educational purposes only.
          </p>
          <p className="pt-2 text-[#999]">
            © 2026 ZILLERS. Built by{' '}
            <a
              href="https://github.com/ekanth14"
              target="_blank"
              rel="noopener noreferrer"
              className="font-bold text-white hover:text-[#D8D8DC] transition-colors"
            >
              Ekanth B S
            </a>
            . All rights reserved.
          </p>
        </div>
      </footer>
    </div>
  );
};

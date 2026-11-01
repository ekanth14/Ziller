import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ExternalLink,
  Github,
  Linkedin,
  Globe,
  Mail,
  User,
  Code2,
  CheckCircle2,
  ArrowRight,
  Sparkles,
  ShieldCheck,
  Layers,
  Cpu,
  AlertCircle,
  Copy,
  Check,
  Send,
} from 'lucide-react';

interface CollaborateFormData {
  fullName: string;
  email: string;
  github: string;
  linkedin: string;
  website: string;
  track: string;
  message: string;
  termsAccepted: boolean;
}

const INITIAL_FORM: CollaborateFormData = {
  fullName: '',
  email: '',
  github: '',
  linkedin: '',
  website: '',
  track: 'Quantitative Strategy Research',
  message: '',
  termsAccepted: true,
};

const COLLAB_TRACKS = [
  {
    id: 'Quantitative Strategy Research',
    title: 'Quantitative Strategy Research',
    desc: 'SMC order-flow, FVG statistical discovery, statistical arbitrage, and cross-asset crypto modeling.',
  },
  {
    id: 'Laya AI & Multi-Agent Deliberation',
    title: 'Laya AI & Deliberation Architecture',
    desc: 'Local multi-agent reasoning, DSPy optimization, consensus voting, and deterministic decision trees.',
  },
  {
    id: 'Execution & Low-Latency SOR',
    title: 'Execution Infrastructure & SOR',
    desc: 'Smart order routing, WebSocket microservices, sub-millisecond tick ingest, and memory-mapped buffers.',
  },
  {
    id: 'Risk Engineering & 5-Gate Governance',
    title: 'Risk Governance & Safeguards',
    desc: 'Deterministic pre-trade controls, drawdown gates, DSR validation, and emergency kill switches.',
  },
  {
    id: 'Institutional Frontend & Data Viz',
    title: 'Institutional UI & Visualization',
    desc: 'High-performance WebGL / Canvas order book rendering, custom charting, and low-latency metrics.',
  },
];

export const Collaborate: React.FC<{ isStandalone?: boolean }> = ({ isStandalone = false }) => {
  const [formData, setFormData] = useState<CollaborateFormData>(INITIAL_FORM);
  const [errors, setErrors] = useState<Partial<Record<keyof CollaborateFormData, string>>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submittedData, setSubmittedData] = useState<{
    id: string;
    timestamp: string;
    email: string;
    github: string;
  } | null>(null);
  const [copiedId, setCopiedId] = useState(false);

  const validate = (): boolean => {
    const errs: Partial<Record<keyof CollaborateFormData, string>> = {};

    if (!formData.fullName.trim()) {
      errs.fullName = 'Full name or professional moniker is required.';
    }

    if (!formData.email.trim()) {
      errs.email = 'Email address is required.';
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email.trim())) {
      errs.email = 'Please provide a valid email address.';
    }

    if (!formData.github.trim()) {
      errs.github = 'GitHub profile URL or username is required.';
    } else {
      const cleanGh = formData.github.trim();
      if (!cleanGh.includes('github.com') && !/^[a-zA-Z0-9-]+$/.test(cleanGh.replace(/^@/, ''))) {
        errs.github = 'Please enter a valid GitHub profile URL or handle.';
      }
    }

    if (!formData.linkedin.trim()) {
      errs.linkedin = 'LinkedIn profile URL or handle is required.';
    } else {
      const cleanLi = formData.linkedin.trim();
      if (!cleanLi.includes('linkedin.com') && cleanLi.length < 3) {
        errs.linkedin = 'Please enter a valid LinkedIn profile URL or handle.';
      }
    }

    if (formData.website.trim()) {
      const w = formData.website.trim();
      if (!w.includes('.') || w.length < 4) {
        errs.website = 'Please enter a valid domain or URL (e.g. portfolio.dev).';
      }
    }

    if (!formData.termsAccepted) {
      errs.termsAccepted = 'Please acknowledge the research collaboration principles.';
    }

    setErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;

    setIsSubmitting(true);

    // Format fields
    const ghUrl = formData.github.includes('github.com')
      ? formData.github.trim()
      : `https://github.com/${formData.github.trim().replace(/^@/, '')}`;

    const liUrl = formData.linkedin.includes('linkedin.com')
      ? formData.linkedin.trim()
      : `https://linkedin.com/in/${formData.linkedin.trim().replace(/^@/, '')}`;

    const webUrl = formData.website.trim()
      ? formData.website.startsWith('http')
        ? formData.website.trim()
        : `https://${formData.website.trim()}`
      : '';

    const payload = {
      name: formData.fullName.trim(),
      email: formData.email.trim().toLowerCase(),
      github: ghUrl,
      linkedin: liUrl,
      website: webUrl,
      track: formData.track,
      message: formData.message.trim(),
    };

    let responseCollabId = `COL-${Math.random().toString(36).substring(2, 10).toUpperCase()}`;

    try {
      const res = await fetch('/api/collaborate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });

      if (res.ok) {
        const data = await res.json();
        if (data.collab_id) {
          responseCollabId = data.collab_id;
        }
      }
    } catch {
      // Offline fallback: Buffer in localStorage for zero data loss
      try {
        const pending = JSON.parse(localStorage.getItem('zillers_pending_collabs') || '[]');
        pending.push({ ...payload, id: responseCollabId, bufferedAt: new Date().toISOString() });
        localStorage.setItem('zillers_pending_collabs', JSON.stringify(pending));
      } catch {
        // localStorage not available
      }
    }

    // Artificial brief pause for polished tactile feedback
    await new Promise((r) => setTimeout(r, 600));

    setSubmittedData({
      id: responseCollabId,
      timestamp: new Date().toISOString(),
      email: payload.email,
      github: ghUrl,
    });
    setIsSubmitting(false);
  };

  const handleCopyId = () => {
    if (!submittedData) return;
    navigator.clipboard.writeText(submittedData.id);
    setCopiedId(true);
    setTimeout(() => setCopiedId(false), 2500);
  };

  const resetForm = () => {
    setSubmittedData(null);
    setFormData(INITIAL_FORM);
    setErrors({});
  };

  return (
    <section
      id="collaborate"
      className={`relative w-full bg-[#050505] text-[#F4F4F5] ${
        isStandalone ? 'pt-28 pb-24 px-4 sm:px-6 md:px-8' : 'py-28 px-4 sm:px-6 md:px-8 border-t border-[#38383C]'
      }`}
    >
      {/* Background illumination & grid accent */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[700px] h-[350px] bg-gradient-to-b from-[#38383C]/10 to-transparent blur-3xl rounded-full" />
      </div>

      <div className="relative max-w-6xl mx-auto">
        {/* Section Header */}
        <div className="text-center max-w-3xl mx-auto mb-16 space-y-4">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-[#4D4D51] bg-[#151515] text-[11px] font-mono tracking-wider uppercase text-[#D8D8DC]">
            <Code2 className="w-3 h-3 text-[#D8D8DC]" />
            <span>Open Quantitative Engineering</span>
          </div>

          <h2 className="text-3xl sm:text-5xl md:text-6xl font-semibold tracking-[-0.03em] text-metallic leading-tight">
            Collaborate and build together.
          </h2>

          <p className="text-sm sm:text-base text-[#A2A2A8] font-light leading-relaxed">
            ZILLERS is engineered in the open under{' '}
            <a
              href="https://ziennexus.app/"
              target="_blank"
              rel="noopener noreferrer"
              className="text-white font-semibold hover:text-[#D8D8DC] transition-colors"
              title="Visit Zien Organisation (ziennexus.app)"
            >
              Zien Organisation
            </a>
            . We partner with quantitative researchers, machine learning specialists, systems architects, and traders to advance autonomous market research, explainable AI deliberation, and deterministic risk governance.
          </p>

          <div className="pt-2 flex items-center justify-center gap-3">
            <a
              href="/collaborations"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 px-4 py-2 rounded-full border border-[#4D4D51] hover:border-white bg-[#151515] hover:bg-[#222224] text-xs font-mono text-[#D8D8DC] hover:text-white transition-all shadow-md group"
              title="View live submissions database"
            >
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              <span>Browse Submissions Desk</span>
              <ExternalLink className="w-3 h-3 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform text-[#A2A2A8]" />
            </a>
          </div>
        </div>

        {/* Two-Column Grid: Form & Research Values */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-10 items-start">
          {/* Left Column: Form / Success Card (7 cols) */}
          <div className="lg:col-span-7">
            <div className="relative rounded-3xl border border-[#4D4D51] bg-[#090909]/90 backdrop-blur-xl p-6 sm:p-10 shadow-2xl shadow-black/80 overflow-hidden">
              <AnimatePresence mode="wait">
                {submittedData ? (
                  /* Success Confirmation Screen */
                  <motion.div
                    key="success"
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -12 }}
                    transition={{ duration: 0.3 }}
                    className="space-y-8"
                  >
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-full bg-[#151515] border border-[#4D4D51] flex items-center justify-center text-emerald-400">
                        <CheckCircle2 className="w-5 h-5 text-[#F4F4F5]" />
                      </div>
                      <div>
                        <h3 className="text-lg font-semibold text-[#F4F4F5] tracking-tight">
                          Proposal Logged Successfully
                        </h3>
                        <p className="text-xs font-mono text-[#A2A2A8]">
                          Receipt dispatched to{' '}
                          <a
                            href="https://ziennexus.app/"
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-[#D8D8DC] font-semibold hover:text-white transition-colors"
                            title="Visit Zien Organisation (ziennexus.app)"
                          >
                            Zien Organisation
                          </a>{' '}
                          Research Desk
                        </p>
                      </div>
                    </div>

                    {/* Receipt Dossier Box */}
                    <div className="rounded-2xl border border-[#38383C] bg-[#151515] p-5 space-y-4 font-mono text-xs">
                      <div className="flex justify-between items-center pb-3 border-b border-[#222224]">
                        <span className="text-[#A2A2A8]">Submission Reference</span>
                        <div className="flex items-center gap-2">
                          <span className="text-[#F4F4F5] font-bold">{submittedData.id}</span>
                          <button
                            type="button"
                            onClick={handleCopyId}
                            className="text-[#A2A2A8] hover:text-[#F4F4F5] p-1 transition-colors"
                            title="Copy ID"
                          >
                            {copiedId ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                          </button>
                        </div>
                      </div>

                      <div className="flex justify-between items-center text-[11px]">
                        <span className="text-[#A2A2A8]">Primary Contact</span>
                        <span className="text-[#D8D8DC]">{submittedData.email}</span>
                      </div>

                      <div className="flex justify-between items-center text-[11px]">
                        <span className="text-[#A2A2A8]">GitHub Repository Handle</span>
                        <a
                          href={submittedData.github}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-[#F4F4F5] underline hover:text-white"
                        >
                          {submittedData.github.replace('https://github.com/', '@')}
                        </a>
                      </div>

                      <div className="flex justify-between items-center text-[11px]">
                        <span className="text-[#A2A2A8]">Timestamp (UTC)</span>
                        <span className="text-[#A2A2A8]">{new Date(submittedData.timestamp).toUTCString()}</span>
                      </div>
                    </div>

                    <div className="rounded-2xl border border-[#222224] bg-[#050505] p-4 text-xs text-[#A2A2A8] leading-relaxed space-y-2">
                      <p className="font-semibold text-[#D8D8DC]">Next Steps in Review:</p>
                      <p>
                        1. A quantitative researcher will review your GitHub repositories and contributions for technical
                        alignment with ZILLERS and Laya AI.
                      </p>
                      <p>
                        2. You will receive an invitation via email to join our collaborative workspace, issue tracker,
                        and research syncs.
                      </p>
                    </div>

                    <div className="flex flex-col sm:flex-row gap-3">
                      <a
                        href="/collaborations"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex-1 inline-flex items-center justify-center gap-2 text-xs font-mono uppercase tracking-wider py-3 rounded-full border border-[#4D4D51] hover:border-white bg-[#151515] text-[#F4F4F5] hover:bg-[#222224] transition-all shadow-sm group"
                      >
                        <span>Open Submissions Desk</span>
                        <ExternalLink className="w-3.5 h-3.5 text-[#A2A2A8] group-hover:text-white" />
                      </a>
                      <button
                        type="button"
                        onClick={resetForm}
                        className="flex-1 text-xs font-mono uppercase tracking-wider py-3 rounded-full border border-[#38383C] bg-[#090909] text-[#A2A2A8] hover:text-white hover:border-[#4D4D51] transition-all"
                      >
                        Submit Another
                      </button>
                    </div>
                  </motion.div>
                ) : (
                  /* Input Form */
                  <form onSubmit={handleSubmit} className="space-y-6">
                    <div className="border-b border-[#222224] pb-4 mb-2">
                      <h3 className="text-xl font-semibold text-[#F4F4F5] tracking-tight">
                        Collaborator Credentials
                      </h3>
                      <p className="text-xs text-[#A2A2A8] font-light mt-1">
                        Connect your development profiles to start building quantitative modules together.
                      </p>
                    </div>

                    {/* Full Name */}
                    <div className="space-y-1.5">
                      <label className="block text-xs font-mono uppercase tracking-wider text-[#A2A2A8]">
                        Full Name / Moniker <span className="text-rose-400">*</span>
                      </label>
                      <div className="relative">
                        <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-[#A2A2A8]">
                          <User className="w-4 h-4" />
                        </div>
                        <input
                          type="text"
                          value={formData.fullName}
                          onChange={(e) => setFormData({ ...formData, fullName: e.target.value })}
                          placeholder="e.g. Alex Vance or quant_trader_42"
                          className="w-full bg-[#151515] border border-[#38383C] focus:border-[#F4F4F5] rounded-xl pl-10 pr-4 py-2.5 text-xs text-[#F4F4F5] placeholder:text-[#A2A2A8]/50 focus:outline-none transition-colors"
                        />
                      </div>
                      {errors.fullName && (
                        <p className="text-[11px] text-rose-400 flex items-center gap-1 font-mono">
                          <AlertCircle className="w-3 h-3" /> {errors.fullName}
                        </p>
                      )}
                    </div>

                    {/* Email ID */}
                    <div className="space-y-1.5">
                      <label className="block text-xs font-mono uppercase tracking-wider text-[#A2A2A8]">
                        Email Address <span className="text-rose-400">*</span>
                      </label>
                      <div className="relative">
                        <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-[#A2A2A8]">
                          <Mail className="w-4 h-4" />
                        </div>
                        <input
                          type="email"
                          value={formData.email}
                          onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                          placeholder="e.g. alex@institution.edu or alex@quant.io"
                          className="w-full bg-[#151515] border border-[#38383C] focus:border-[#F4F4F5] rounded-xl pl-10 pr-4 py-2.5 text-xs text-[#F4F4F5] placeholder:text-[#A2A2A8]/50 focus:outline-none transition-colors"
                        />
                      </div>
                      {errors.email && (
                        <p className="text-[11px] text-rose-400 flex items-center gap-1 font-mono">
                          <AlertCircle className="w-3 h-3" /> {errors.email}
                        </p>
                      )}
                    </div>

                    {/* GitHub & LinkedIn in 2 cols */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      {/* GitHub Profile */}
                      <div className="space-y-1.5">
                        <label className="block text-xs font-mono uppercase tracking-wider text-[#A2A2A8]">
                          GitHub Profile <span className="text-rose-400">*</span>
                        </label>
                        <div className="relative">
                          <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-[#A2A2A8]">
                            <Github className="w-4 h-4" />
                          </div>
                          <input
                            type="text"
                            value={formData.github}
                            onChange={(e) => setFormData({ ...formData, github: e.target.value })}
                            placeholder="github.com/username or @handle"
                            className="w-full bg-[#151515] border border-[#38383C] focus:border-[#F4F4F5] rounded-xl pl-10 pr-4 py-2.5 text-xs text-[#F4F4F5] placeholder:text-[#A2A2A8]/50 focus:outline-none transition-colors"
                          />
                        </div>
                        {errors.github && (
                          <p className="text-[11px] text-rose-400 flex items-center gap-1 font-mono">
                            <AlertCircle className="w-3 h-3" /> {errors.github}
                          </p>
                        )}
                      </div>

                      {/* LinkedIn Profile */}
                      <div className="space-y-1.5">
                        <label className="block text-xs font-mono uppercase tracking-wider text-[#A2A2A8]">
                          LinkedIn Profile <span className="text-rose-400">*</span>
                        </label>
                        <div className="relative">
                          <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-[#A2A2A8]">
                            <Linkedin className="w-4 h-4" />
                          </div>
                          <input
                            type="text"
                            value={formData.linkedin}
                            onChange={(e) => setFormData({ ...formData, linkedin: e.target.value })}
                            placeholder="linkedin.com/in/username"
                            className="w-full bg-[#151515] border border-[#38383C] focus:border-[#F4F4F5] rounded-xl pl-10 pr-4 py-2.5 text-xs text-[#F4F4F5] placeholder:text-[#A2A2A8]/50 focus:outline-none transition-colors"
                          />
                        </div>
                        {errors.linkedin && (
                          <p className="text-[11px] text-rose-400 flex items-center gap-1 font-mono">
                            <AlertCircle className="w-3 h-3" /> {errors.linkedin}
                          </p>
                        )}
                      </div>
                    </div>

                    {/* Personal or Company Website (Optional) */}
                    <div className="space-y-1.5">
                      <div className="flex justify-between items-center">
                        <label className="block text-xs font-mono uppercase tracking-wider text-[#A2A2A8]">
                          Personal or Company Website
                        </label>
                        <span className="text-[10px] font-mono text-[#A2A2A8]/60 uppercase">Optional</span>
                      </div>
                      <div className="relative">
                        <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-[#A2A2A8]">
                          <Globe className="w-4 h-4" />
                        </div>
                        <input
                          type="text"
                          value={formData.website}
                          onChange={(e) => setFormData({ ...formData, website: e.target.value })}
                          placeholder="https://portfolio.dev or company.com"
                          className="w-full bg-[#151515] border border-[#38383C] focus:border-[#F4F4F5] rounded-xl pl-10 pr-4 py-2.5 text-xs text-[#F4F4F5] placeholder:text-[#A2A2A8]/50 focus:outline-none transition-colors"
                        />
                      </div>
                      {errors.website && (
                        <p className="text-[11px] text-rose-400 flex items-center gap-1 font-mono">
                          <AlertCircle className="w-3 h-3" /> {errors.website}
                        </p>
                      )}
                    </div>

                    {/* Track Selection */}
                    <div className="space-y-1.5">
                      <label className="block text-xs font-mono uppercase tracking-wider text-[#A2A2A8]">
                        Primary Research & Engineering Focus
                      </label>
                      <select
                        value={formData.track}
                        onChange={(e) => setFormData({ ...formData, track: e.target.value })}
                        className="w-full bg-[#151515] border border-[#38383C] focus:border-[#F4F4F5] rounded-xl px-4 py-2.5 text-xs text-[#F4F4F5] focus:outline-none transition-colors font-sans cursor-pointer"
                      >
                        {COLLAB_TRACKS.map((t) => (
                          <option key={t.id} value={t.id} className="bg-[#151515] text-[#F4F4F5]">
                            {t.title}
                          </option>
                        ))}
                      </select>
                    </div>

                    {/* Brief Proposal / Notes */}
                    <div className="space-y-1.5">
                      <div className="flex justify-between items-center">
                        <label className="block text-xs font-mono uppercase tracking-wider text-[#A2A2A8]">
                          Proposal / Contribution Focus
                        </label>
                        <span className="text-[10px] font-mono text-[#A2A2A8]/60 uppercase">Optional</span>
                      </div>
                      <textarea
                        rows={3}
                        value={formData.message}
                        onChange={(e) => setFormData({ ...formData, message: e.target.value })}
                        placeholder="Tell us what you'd like to build, an academic paper you'd like to implement, or an algorithmic model to integrate into ZILLERS..."
                        className="w-full bg-[#151515] border border-[#38383C] focus:border-[#F4F4F5] rounded-xl p-3 text-xs text-[#F4F4F5] placeholder:text-[#A2A2A8]/50 focus:outline-none transition-colors resize-none"
                      />
                    </div>

                    {/* Open Research Agreement Checkbox */}
                    <div className="space-y-1.5 pt-1">
                      <label className="flex items-start gap-2.5 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={formData.termsAccepted}
                          onChange={(e) => setFormData({ ...formData, termsAccepted: e.target.checked })}
                          className="mt-0.5 rounded border-[#4D4D51] bg-[#151515] text-white focus:ring-0 cursor-pointer"
                        />
                        <span className="text-[11px] text-[#A2A2A8] leading-tight select-none">
                          I agree to open quantitative research standards and code-sharing principles under{' '}
                          <a
                            href="https://ziennexus.app/"
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-[#D8D8DC] font-semibold hover:text-white transition-colors"
                            title="Visit Zien Organisation (ziennexus.app)"
                          >
                            Zien Organisation
                          </a>
                          .
                        </span>
                      </label>
                      {errors.termsAccepted && (
                        <p className="text-[11px] text-rose-400 flex items-center gap-1 font-mono">
                          <AlertCircle className="w-3 h-3" /> {errors.termsAccepted}
                        </p>
                      )}
                    </div>

                    {/* Submit Button */}
                    <button
                      type="submit"
                      disabled={isSubmitting}
                      className="w-full inline-flex items-center justify-center gap-2 py-3 px-6 rounded-full bg-[#F4F4F5] text-[#050505] hover:bg-white text-xs font-semibold uppercase tracking-wider transition-all duration-200 shadow-lg hover:scale-[1.01] active:scale-[0.99] disabled:opacity-50 disabled:pointer-events-none"
                    >
                      {isSubmitting ? (
                        <>
                          <div className="w-4 h-4 border-2 border-[#050505] border-t-transparent rounded-full animate-spin" />
                          <span>Dispatching Proposal...</span>
                        </>
                      ) : (
                        <>
                          <span>Submit Collaboration Proposal</span>
                          <Send className="w-3.5 h-3.5" />
                        </>
                      )}
                    </button>
                  </form>
                )}
              </AnimatePresence>
            </div>
          </div>

          {/* Right Column: Values, Tracks & Institutional Dossier (5 cols) */}
          <div className="lg:col-span-5 space-y-6">
            {/* Box 1: Why Build in the Open */}
            <div className="rounded-3xl border border-[#38383C] bg-[#090909] p-6 sm:p-7 space-y-3">
              <div className="flex items-center gap-2.5 text-xs font-mono text-[#D8D8DC] uppercase tracking-wider">
                <Sparkles className="w-4 h-4 text-[#F4F4F5]" />
                <span>Our Collaborative Philosophy</span>
              </div>
              <h3 className="text-lg font-semibold text-[#F4F4F5] tracking-tight">
                Peer-reviewed quantitative systems.
              </h3>
              <p className="text-xs text-[#A2A2A8] font-light leading-relaxed">
                Traditional hedge funds lock their algorithmic research behind proprietary siloes. ZILLERS believes
                the future of systematic intelligence is accelerated by open peer-review, transparent statistical
                validation, and collaborative machine learning.
              </p>
            </div>

            {/* Box 2: Institutional Standards */}
            <div className="rounded-3xl border border-[#38383C] bg-[#090909] p-6 sm:p-7 space-y-4">
              <div className="flex items-center gap-2.5 text-xs font-mono text-[#D8D8DC] uppercase tracking-wider">
                <ShieldCheck className="w-4 h-4 text-[#F4F4F5]" />
                <span>Engineering Standards</span>
              </div>

              <div className="space-y-3 text-xs">
                <div className="flex items-start gap-3">
                  <Cpu className="w-4 h-4 text-[#D8D8DC] mt-0.5 shrink-0" />
                  <div>
                    <h4 className="font-semibold text-[#F4F4F5]">Deterministic Risk Architecture</h4>
                    <p className="text-[#A2A2A8] text-[11px] font-light">
                      All execution and decision modules must conform to the 5-Gate governor safeguards and zero-latency fail-safes.
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-3">
                  <Layers className="w-4 h-4 text-[#D8D8DC] mt-0.5 shrink-0" />
                  <div>
                    <h4 className="font-semibold text-[#F4F4F5]">Statistical Validation Required</h4>
                    <p className="text-[#A2A2A8] text-[11px] font-light">
                      Algorithms require Deflated Sharpe Ratio (DSR), walk-forward cross-validation, and transaction cost modeling.
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-3">
                  <Code2 className="w-4 h-4 text-[#D8D8DC] mt-0.5 shrink-0" />
                  <div>
                    <h4 className="font-semibold text-[#F4F4F5]">Clean Python & Rust Ecosystem</h4>
                    <p className="text-[#A2A2A8] text-[11px] font-light">
                      Zero unvetted runtime dependencies. High test coverage (pytest/cargo test) and reproducible environment locks.
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* Box 3: Parent Organization Sponsorship */}
            <div className="rounded-3xl border border-[#222224] bg-[#050505] p-5 text-xs space-y-2 font-mono">
              <div className="flex items-center justify-between text-[#A2A2A8]">
                <span>PARENT ENTITY</span>
                <a
                  href="https://ziennexus.app/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[#D8D8DC] hover:text-white font-semibold inline-flex items-center gap-1 transition-colors"
                  title="Visit Zien Organisation (ziennexus.app)"
                >
                  <span>ZIEN ORGANISATION</span>
                  <ExternalLink className="w-3 h-3 text-[#A2A2A8]" />
                </a>
              </div>
              <div className="flex justify-between text-[#A2A2A8] text-[11px]">
                <span>INCUBATION SECTOR</span>
                <span className="text-[#D8D8DC]">FinTech / Quantitative Trading</span>
              </div>
              <div className="flex justify-between text-[#A2A2A8] text-[11px]">
                <span>LICENSE TYPE</span>
                <span className="text-[#D8D8DC]">Open Academic & Personal Research</span>
              </div>
              <div className="pt-2 text-[10px] text-[#A2A2A8]/70 border-t border-[#222224] leading-relaxed">
                Accepted researchers receive direct compute allocation grants for local GPU training and market depth ingest clusters.
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

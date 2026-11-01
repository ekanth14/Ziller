import React from 'react';
import { motion } from 'framer-motion';
import { BarChart2, Cpu, ShieldAlert, Workflow } from 'lucide-react';

export const CoreCapabilities: React.FC = () => {
  const capabilities = [
    {
      num: '01',
      title: 'Quantitative Research',
      icon: BarChart2,
      desc: 'Systematic strategy development, market analysis, statistical validation, and backtesting. Employs cross-sectional data modeling and Deflated Sharpe Ratio calculation to avoid overfitting to historical noise.',
      techNote: 'METHODOLOGY: WALK-FORWARD VALIDATION',
    },
    {
      num: '02',
      title: 'Algorithmic Automation',
      icon: Workflow,
      desc: 'Rule-based trading software designed around structured execution logic and repeatable processes. Enforces point-in-time candle validation, exchange clock drift clamping, and state persistence.',
      techNote: 'EXECUTION: DETERMINISTIC TIER 1 RULES',
    },
    {
      num: '03',
      title: 'Laya AI Deliberation',
      icon: Cpu,
      desc: 'A proposed local multi-agent reasoning architecture supporting market research and explainable decision analysis. Synthesizes macro trends, multi-timeframe order flow, and risk constraints before consensus.',
      techNote: 'ARCHITECTURE: LOCAL AGENT COMMITTEE (PROPOSED)',
    },
    {
      num: '04',
      title: 'Risk Governance',
      icon: ShieldAlert,
      desc: 'A risk-first software approach featuring a planned 5-Gate Trading Governor, exposure controls, and emergency safeguards. Includes Indian tax modeling (Section 115BBH/194S) and master dual-action kill switch.',
      techNote: 'GOVERNANCE: 5-GATE VALIDATION SYSTEM',
    },
  ];

  return (
    <section id="technology" className="relative py-28 px-4 md:px-8 max-w-7xl mx-auto border-t border-[#38383C]/40">
      {/* Header */}
      <div className="flex flex-col items-center text-center max-w-3xl mx-auto mb-20">
        <span className="font-mono text-[10px] md:text-xs tracking-[0.25em] text-[#A2A2A8] uppercase mb-3">
          Core Capabilities
        </span>
        <h2 className="text-3xl sm:text-5xl font-semibold tracking-tight text-metallic">
          Technology built around intelligence.
        </h2>
        <p className="mt-4 text-sm md:text-base text-[#A2A2A8] leading-relaxed">
          Four foundational pillars engineered to transform quantitative research into disciplined, repeatable execution.
        </p>
      </div>

      {/* 2x2 Minimalist Card Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {capabilities.map((cap, idx) => {
          const Icon = cap.icon;
          return (
            <motion.div
              key={cap.title}
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: '-60px' }}
              transition={{ duration: 0.6, delay: idx * 0.1 }}
              className="p-8 md:p-10 rounded-3xl border border-[#38383C] bg-[#151515] flex flex-col justify-between glow-card relative overflow-hidden group"
            >
              <div>
                <div className="flex items-center justify-between mb-8">
                  <div className="w-12 h-12 rounded-2xl bg-[#222224] border border-[#4D4D51] flex items-center justify-center text-[#D8D8DC] group-hover:scale-105 transition-transform">
                    <Icon className="w-6 h-6" />
                  </div>
                  <span className="font-mono text-2xl font-light text-[#38383C] group-hover:text-[#4D4D51] transition-colors">
                    {cap.num}
                  </span>
                </div>

                <h3 className="text-xl md:text-2xl font-semibold text-[#F4F4F5] tracking-tight mb-3">
                  {cap.title}
                </h3>
                <p className="text-sm text-[#A2A2A8] leading-relaxed font-normal">
                  {cap.desc}
                </p>
              </div>

              <div className="mt-8 pt-4 border-t border-[#38383C] flex items-center justify-between font-mono text-[10px] text-[#A2A2A8]">
                <span>{cap.techNote}</span>
                <span className="text-[#D8D8DC] font-semibold">ZILLERS V4.2</span>
              </div>
            </motion.div>
          );
        })}
      </div>
    </section>
  );
};

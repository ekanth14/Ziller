import React from 'react';
import { motion } from 'framer-motion';
import { ArrowDown, Radio, Activity, Cpu, ShieldCheck, Zap } from 'lucide-react';

export const ArchitecturePipeline: React.FC = () => {
  const steps = [
    {
      num: 'STAGE 01',
      title: 'Real-Time Market Data Stream',
      icon: Radio,
      badge: 'MULTI-EXCHANGE L3',
      description:
        'Continuous concurrent ticker ingestion from Binance, Coinbase, and Kraken. Normalizes high-frequency bid/ask books and feeds 5m closed bars with strict anti-leakage clock synchronization.',
      specs: ['Binance Data-Stream Vision Fallback', 'Coinbase Level 3 Depth', 'Kraken Public WebSocket', 'Tick Freshness < 5s'],
    },
    {
      num: 'STAGE 02',
      title: 'Quantitative Strategy Engine',
      icon: Activity,
      badge: 'TIER 1 FAST RULES (<20ms)',
      description:
        'Deterministic algorithmic rule validation running instantly on candle close. Scans for Smart Money Concepts (SMC) order blocks, Fair Value Gaps (FVG), and VWAP standard deviation bands.',
      specs: ['SMC Order Blocks', 'Fair Value Gaps (FVG)', 'VWAP Mean Reversion', 'Sub-20ms Evaluation'],
    },
    {
      num: 'STAGE 03',
      title: 'Laya AI Deliberative Reasoning',
      icon: Cpu,
      badge: 'TIER 2 LOCAL LLM COMMITTEE',
      description:
        'Proposed local multi-agent reasoning committee (powered by Ollama/Gemma). Assesses macro regime, order flow bias, and risk parameters with strict schema validation before consensus.',
      specs: ['Structured JSON Contract', 'Zero Cloud API Reliance', 'Multi-Agent Thesis Synthesis', 'Audit Log Trail'],
    },
    {
      num: 'STAGE 04',
      title: '5-Gate Risk Governor',
      icon: ShieldCheck,
      badge: 'FAIL-CLOSED GATING',
      description:
        'Institutional safety layer preventing unauthorized order submission. Demands 28+ forward paper days, 100+ recorded simulated trades, Section 115BBH/194S tax deductions, and Deflated Sharpe Ratio > 0.95.',
      specs: ['28+ Paper Days Requirement', '100+ Trade Execution Gate', '30% VDA Tax / 1% TDS Model', 'DSR Overfitting Guard'],
    },
    {
      num: 'STAGE 05',
      title: 'Execution Infrastructure',
      icon: Zap,
      badge: 'SANDBOXED DISPATCH',
      description:
        'Smart Order Router (SOR) and exchange adapter. Strictly defaults to sandboxed paper trading with persistent state, protective stop syncing, partial fills, and dual-action emergency kill switch.',
      specs: ['Paper Mode Default', 'Protective Stops & Fills', 'Master Kill Switch (HALT/FLATTEN)', 'Withdrawal Disabled Check'],
    },
  ];

  return (
    <section className="relative py-28 px-4 md:px-8 max-w-7xl mx-auto border-t border-[#38383C]/40">
      {/* Header */}
      <div className="flex flex-col items-center text-center max-w-3xl mx-auto mb-20">
        <span className="font-mono text-[10px] md:text-xs tracking-[0.25em] text-[#A2A2A8] uppercase mb-3">
          End-to-End Pipeline
        </span>
        <h2 className="text-3xl sm:text-5xl font-semibold tracking-tight text-metallic">
          A system designed to think systematically.
        </h2>
        <p className="mt-4 text-sm md:text-base text-[#A2A2A8] leading-relaxed">
          The proposed pipeline traces the journey of a price tick from raw exchange depth to validated execution.
        </p>
      </div>

      {/* Vertical Pipeline Flow with Thin Silver Lines and Dark Modules */}
      <div className="max-w-4xl mx-auto relative">
        {/* Continuous Central Thin Silver Spine Line */}
        <div className="absolute left-6 md:left-1/2 top-4 bottom-4 w-[1px] bg-gradient-to-b from-transparent via-[#4D4D51] to-transparent -translate-x-1/2 pointer-events-none hidden md:block" />

        <div className="space-y-10 relative">
          {steps.map((step, idx) => {
            const Icon = step.icon;
            const isEven = idx % 2 === 0;
            return (
              <motion.div
                key={step.title}
                initial={{ opacity: 0, y: 35 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: '-60px' }}
                transition={{ duration: 0.6, delay: idx * 0.1 }}
                className={`relative flex flex-col md:flex-row items-center gap-6 ${
                  isEven ? 'md:flex-row-reverse' : ''
                }`}
              >
                {/* Content Card */}
                <div className="w-full md:w-[calc(50%-32px)] p-6 md:p-8 rounded-3xl border border-[#38383C] bg-[#151515] glow-card relative">
                  <div className="flex items-center justify-between gap-2 mb-3">
                    <span className="font-mono text-[10px] text-[#A2A2A8] tracking-widest">{step.num}</span>
                    <span className="px-2.5 py-0.5 rounded-full text-[9px] font-mono font-medium tracking-wider bg-[#222224] text-[#D8D8DC] border border-[#4D4D51]">
                      {step.badge}
                    </span>
                  </div>

                  <h3 className="text-lg md:text-xl font-semibold text-[#F4F4F5] tracking-tight mb-2">
                    {step.title}
                  </h3>
                  <p className="text-xs md:text-sm text-[#A2A2A8] leading-relaxed mb-4">
                    {step.description}
                  </p>

                  <div className="pt-3 border-t border-[#38383C] grid grid-cols-2 gap-2 text-[10px] font-mono text-[#D8D8DC]">
                    {step.specs.map((spec) => (
                      <div key={spec} className="flex items-center gap-1.5 truncate">
                        <span className="w-1 h-1 rounded-full bg-[#D8D8DC]" />
                        <span className="truncate">{spec}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Central Connecting Node Indicator */}
                <div className="relative z-10 w-12 h-12 rounded-full border border-[#4D4D51] bg-[#151515] flex items-center justify-center text-[#D8D8DC] shadow-xl shrink-0 hidden md:flex">
                  <Icon className="w-5 h-5" />
                </div>

                {/* Empty Half on Desktop for Alternating Layout */}
                <div className="w-full md:w-[calc(50%-32px)] hidden md:block" />
              </motion.div>
            );
          })}
        </div>
      </div>

      <div className="mt-14 text-center">
        <span className="font-mono text-[10px] text-[#A2A2A8]/60 tracking-wider uppercase">
          * Illustrative Engineering Flow // Pure Architecture Demonstration
        </span>
      </div>
    </section>
  );
};

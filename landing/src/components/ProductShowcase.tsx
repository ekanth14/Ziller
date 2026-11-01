import React from 'react';
import { motion } from 'framer-motion';
import { LineChart, Sliders, ShieldCheck, Database, Layers, ArrowUpRight, BarChart3, Bot } from 'lucide-react';

export const ProductShowcase: React.FC = () => {
  const panels = [
    {
      title: 'Quantitative Strategy Research',
      icon: LineChart,
      desc: 'Systematic statistical validation utilizing the Deflated Sharpe Ratio (DSR) to control for data-snooping bias across multiple trial iterations.',
      metric: 'DSR 0.98',
      submetric: 'WALK-FORWARD VALIDATED',
    },
    {
      title: 'Crypto Market Overview',
      icon: Database,
      desc: '100+ monitored digital asset pairs streaming aggregated multi-exchange ticker depth from Binance, Coinbase, and Kraken simultaneously.',
      metric: '100+ PAIRS',
      submetric: 'MULTI-EXCHANGE ARB',
    },
    {
      title: 'Algorithmic Trading Systems',
      icon: Sliders,
      desc: 'Tier 1 sub-20ms deterministic execution engine tracking Smart Money Concepts (SMC), Fair Value Gaps (FVG), and VWAP mean reversion.',
      metric: '< 20 ms',
      submetric: 'DETERMINISTIC RULES',
    },
    {
      title: 'Laya AI Deliberative Reasoning',
      icon: Bot,
      desc: 'Proposed multi-agent local LLM committee that debates candidate proposals with strict JSON schema compliance before risk submission.',
      metric: 'LOCAL GEMMA 4',
      submetric: 'EXPLAINABLE AUDIT',
    },
    {
      title: '5-Gate Risk Governor',
      icon: ShieldCheck,
      desc: 'Institutional gatekeeper requiring 28+ forward paper days, 100+ simulated trades, Indian tax accounting, and strict drawdown bounds.',
      metric: '5 GATES',
      submetric: 'FAIL-CLOSED ARCHITECTURE',
    },
    {
      title: 'Trading Automation Overview',
      icon: Layers,
      desc: 'Paper-first forward execution engine with persistent restart-safe state, protective stop synchronization, and loss cooldown limiters.',
      metric: '100% PAPER',
      submetric: 'RESTART RESILIENT',
    },
  ];

  return (
    <section id="platform" className="relative py-24 px-4 md:px-8 max-w-7xl mx-auto">
      {/* Section Header */}
      <div className="flex flex-col items-center text-center max-w-3xl mx-auto mb-16">
        <span className="font-mono text-[10px] md:text-xs tracking-[0.25em] text-[#A2A2A8] uppercase mb-3">
          Platform Architecture
        </span>
        <h2 className="text-3xl md:text-5xl font-semibold tracking-tight text-metallic">
          Institutional research software. Designed for discipline.
        </h2>
        <p className="mt-4 text-sm md:text-base text-[#A2A2A8] leading-relaxed">
          An integrated environment uniting microsecond algorithmic execution with deep deliberative artificial intelligence and sovereign risk controls.
        </p>
      </div>

      {/* Grid of Institutional Showcase Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
        {panels.map((panel, idx) => {
          const Icon = panel.icon;
          return (
            <motion.div
              key={panel.title}
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: '-60px' }}
              transition={{ duration: 0.5, delay: idx * 0.08 }}
              className="p-6 rounded-2xl border border-[#38383C] bg-[#151515] flex flex-col justify-between glow-card relative overflow-hidden group"
            >
              {/* Subtle top light reflection */}
              <div className="absolute top-0 inset-x-0 h-[1px] bg-gradient-to-r from-transparent via-[#4D4D51] to-transparent opacity-50 group-hover:opacity-100 transition-opacity" />

              <div>
                <div className="flex items-center justify-between mb-4">
                  <div className="w-10 h-10 rounded-xl bg-[#222224] border border-[#4D4D51] flex items-center justify-center text-[#D8D8DC]">
                    <Icon className="w-5 h-5" />
                  </div>
                  <span className="font-mono text-[10px] text-[#A2A2A8] tracking-widest uppercase">
                    MOD 0{idx + 1}
                  </span>
                </div>

                <h3 className="text-lg font-medium text-[#F4F4F5] tracking-tight mb-2">
                  {panel.title}
                </h3>
                <p className="text-xs md:text-sm text-[#A2A2A8] leading-relaxed mb-6">
                  {panel.desc}
                </p>
              </div>

              <div className="pt-4 border-t border-[#38383C] flex items-center justify-between font-mono">
                <div>
                  <div className="text-xs font-semibold text-[#F4F4F5]">{panel.metric}</div>
                  <div className="text-[9px] text-[#A2A2A8] tracking-wider">{panel.submetric}</div>
                </div>
                <div className="w-7 h-7 rounded-full bg-[#222224] flex items-center justify-center text-[#D8D8DC] group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform">
                  <ArrowUpRight className="w-3.5 h-3.5" />
                </div>
              </div>
            </motion.div>
          );
        })}
      </div>

      {/* Illustrative Disclaimer */}
      <div className="mt-8 text-center">
        <span className="font-mono text-[10px] text-[#A2A2A8]/60 tracking-wider uppercase">
          * Note: All system metrics, architecture blocks, and data flows are illustrative software concepts.
        </span>
      </div>
    </section>
  );
};

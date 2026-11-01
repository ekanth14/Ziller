import React from 'react';
import { motion } from 'framer-motion';
import { ShieldCheck, AlertTriangle, Scale, CheckCircle2 } from 'lucide-react';

export const RiskPhilosophy: React.FC = () => {
  return (
    <section id="vision" className="relative py-28 px-4 md:px-8 max-w-7xl mx-auto border-t border-[#38383C]/40">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="text-center mb-16">
          <span className="font-mono text-[10px] md:text-xs tracking-[0.25em] text-[#A2A2A8] uppercase mb-3 block">
            Institutional Principles
          </span>
          <h2 className="text-3xl sm:text-5xl font-semibold tracking-tight text-metallic">
            Built on discipline, not prediction.
          </h2>
          <p className="mt-4 text-sm md:text-base text-[#A2A2A8] leading-relaxed max-w-2xl mx-auto">
            Sustainable quantitative execution is governed not by optimistic backtest curves, but by mathematical risk limiters and ruthless overfit elimination.
          </p>
        </div>

        {/* Editorial Storytelling Layout */}
        <div className="space-y-12">
          {/* Pillar 1: Deflated Sharpe Ratio */}
          <motion.div
            initial={{ opacity: 0, y: 25 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-60px' }}
            transition={{ duration: 0.6 }}
            className="p-8 rounded-3xl border border-[#38383C] bg-[#151515] flex flex-col md:flex-row gap-8 items-start glow-card"
          >
            <div className="p-3.5 rounded-2xl bg-[#222224] border border-[#4D4D51] text-[#D8D8DC] shrink-0">
              <Scale className="w-6 h-6" />
            </div>
            <div>
              <h3 className="text-xl font-semibold text-[#F4F4F5] tracking-tight mb-2">
                Deflated Sharpe Ratio (DSR) & Statistical Significance
              </h3>
              <p className="text-sm text-[#A2A2A8] leading-relaxed">
                Most quantitative algorithms fail in live markets because backtests are over-optimized across hundreds of variations.
                ZILLERS integrates Professor Marcos López de Prado's Deflated Sharpe Ratio framework, statistically discounting performance
                for non-normal returns, skewness, kurtosis, and the number of strategy trials evaluated.
              </p>
            </div>
          </motion.div>

          {/* Pillar 2: 5-Gate Live Safety Governor */}
          <motion.div
            initial={{ opacity: 0, y: 25 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-60px' }}
            transition={{ duration: 0.6, delay: 0.1 }}
            className="p-8 rounded-3xl border border-[#38383C] bg-[#151515] flex flex-col md:flex-row gap-8 items-start glow-card"
          >
            <div className="p-3.5 rounded-2xl bg-[#222224] border border-[#4D4D51] text-[#D8D8DC] shrink-0">
              <ShieldCheck className="w-6 h-6" />
            </div>
            <div>
              <h3 className="text-xl font-semibold text-[#F4F4F5] tracking-tight mb-2">
                The 5-Gate Live Trading Governor
              </h3>
              <p className="text-sm text-[#A2A2A8] leading-relaxed mb-4">
                Live order execution cannot be unlocked by simply flipping a switch. The system enforces an automated fail-closed governance checklist:
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs font-mono text-[#D8D8DC]">
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-[#D8D8DC] shrink-0" />
                  <span>Gate 1: Re-authenticated Operator Password</span>
                </div>
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-[#D8D8DC] shrink-0" />
                  <span>Gate 2: Explicit Single-Token Confirmation</span>
                </div>
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-[#D8D8DC] shrink-0" />
                  <span>Gate 3: 28+ Paper Days & 100+ Trades</span>
                </div>
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-[#D8D8DC] shrink-0" />
                  <span>Gate 4: Indian VDA Tax/GST Cost Hurdle</span>
                </div>
                <div className="flex items-center gap-2 col-span-full">
                  <CheckCircle2 className="w-4 h-4 text-[#D8D8DC] shrink-0" />
                  <span>Gate 5: Deflated Sharpe Ratio (DSR) &gt; 0.95 Threshold</span>
                </div>
              </div>
            </div>
          </motion.div>

          {/* Pillar 3: Risk Transparency & Regulatory Warning */}
          <motion.div
            initial={{ opacity: 0, y: 25 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-60px' }}
            transition={{ duration: 0.6, delay: 0.2 }}
            className="p-6 rounded-2xl border border-[#38383C] bg-[#111319] flex items-start gap-4"
          >
            <div className="p-2 rounded-xl bg-[#222224] text-[#A2A2A8] shrink-0">
              <AlertTriangle className="w-5 h-5" />
            </div>
            <div>
              <h4 className="text-xs font-mono font-semibold uppercase tracking-wider text-[#D8D8DC]">
                Notice of Inherent Market Risk
              </h4>
              <p className="text-xs text-[#A2A2A8] mt-1 leading-relaxed">
                Cryptocurrency and digital asset trading involves significant market volatility and financial risk.
                Algorithmic automation, backtesting validation, and AI deliberation do not eliminate risk or guarantee profit.
                Operators must practice strict capital preservation.
              </p>
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  );
};

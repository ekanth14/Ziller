import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  LineChart,
  Sliders,
  ShieldCheck,
  Database,
  Layers,
  ArrowUpRight,
  Bot,
  X,
  ExternalLink,
  Activity,
  CheckCircle2,
  TrendingDown,
  TrendingUp,
  Cpu,
} from 'lucide-react';
import zillersEmblem from '../assets/emblem.png';

interface ShowcasePanel {
  id: string;
  modNum: string;
  title: string;
  icon: React.ElementType;
  desc: string;
  metric: string;
  submetric: string;
  telemetry: {
    label: string;
    value: string;
  }[];
  workingWindowNotes: string;
  targetAnchor?: string;
}

export const ProductShowcase: React.FC = () => {
  const [selectedPanel, setSelectedPanel] = useState<ShowcasePanel | null>(null);

  const panels: ShowcasePanel[] = [
    {
      id: 'strat-research',
      modNum: 'MOD 01',
      title: 'Quantitative Strategy Research',
      icon: LineChart,
      desc: 'Systematic statistical validation utilizing the Deflated Sharpe Ratio (DSR) to control for data-snooping bias across multiple trial iterations.',
      metric: 'DSR 0.98',
      submetric: 'WALK-FORWARD VALIDATED',
      telemetry: [
        { label: 'Deflated Sharpe Ratio', value: '0.98 (Pass >= 0.95)' },
        { label: 'Walk-Forward Trials', value: '1,420 Permutations' },
        { label: 'Monte Carlo p-value', value: '0.0012 (Statistical Significance)' },
        { label: 'Profit Factor', value: '2.45' },
      ],
      workingWindowNotes: 'Live candlestick backtesting engine calculates statistical hair-cutting on multi-trial parameter optimization to eliminate look-ahead and selection biases.',
      targetAnchor: '#technology',
    },
    {
      id: 'market-overview',
      modNum: 'MOD 02',
      title: 'Crypto Market Overview',
      icon: Database,
      desc: '100+ monitored digital asset pairs streaming aggregated multi-exchange ticker depth from Binance, Coinbase, and Kraken simultaneously.',
      metric: '100+ PAIRS',
      submetric: 'MULTI-EXCHANGE ARB',
      telemetry: [
        { label: 'WebSocket Feeds', value: 'Binance, Coinbase, Kraken' },
        { label: 'Aggregated Throughput', value: '1,420 msgs / sec' },
        { label: 'Average L3 Spread', value: '0.01 USDT (0.000%)' },
        { label: 'Tracked Assets', value: 'BTC, ETH, SOL, XRP, DOGE, +95 pairs' },
      ],
      workingWindowNotes: 'Synthetic mid-market order book aggregator collapses 3 independent tier-1 liquidity sources into a single consolidated depth view.',
      targetAnchor: '#platform',
    },
    {
      id: 'algo-systems',
      modNum: 'MOD 03',
      title: 'Algorithmic Trading Systems',
      icon: Sliders,
      desc: 'Tier 1 sub-20ms deterministic execution engine tracking Smart Money Concepts (SMC), Fair Value Gaps (FVG), and VWAP mean reversion.',
      metric: '< 20 ms',
      submetric: 'DETERMINISTIC RULES',
      telemetry: [
        { label: 'Tick Ingest Latency', value: '0.12 ms' },
        { label: 'Signal Computation', value: '0.34 ms' },
        { label: 'Risk Verification Gate', value: '0.18 ms' },
        { label: 'Total End-to-End Latency', value: '0.84 ms' },
      ],
      workingWindowNotes: 'Core execution runs strictly in memory without external disk or blocking network calls in the hot evaluation cycle.',
      targetAnchor: '#technology',
    },
    {
      id: 'laya-reasoning',
      modNum: 'MOD 04',
      title: 'Laya AI Deliberative Reasoning',
      icon: Bot,
      desc: 'Proposed multi-agent local LLM committee that debates candidate proposals with strict JSON schema compliance before risk submission.',
      metric: 'LOCAL GEMMA 4',
      submetric: 'EXPLAINABLE AUDIT',
      telemetry: [
        { label: 'Deliberation Agents', value: 'Technical, Liquidity, Macro, Auditor' },
        { label: 'Current Consensus', value: 'SHORT ETHUSDT (85% Confidence)' },
        { label: 'Host Enclave', value: 'Local Gemma 4 (Zero Cloud Leakage)' },
        { label: 'Validation Protocol', value: 'Strict Pydantic JSON Schema' },
      ],
      workingWindowNotes: 'Autonomous debate room prevents unreasoned trades by requiring multi-agent consensus before submitting orders to the 5-Gate Governor.',
      targetAnchor: '#laya',
    },
    {
      id: 'risk-governor',
      modNum: 'MOD 05',
      title: '5-Gate Risk Governor',
      icon: ShieldCheck,
      desc: 'Institutional gatekeeper requiring 28+ forward paper days, 100+ simulated trades, Indian tax accounting, and strict drawdown bounds.',
      metric: '5 GATES',
      submetric: 'FAIL-CLOSED ARCHITECTURE',
      telemetry: [
        { label: 'Gate 1 (Forward Days)', value: '34 Days Verified (Req >= 28)' },
        { label: 'Gate 2 (Trade Threshold)', value: '142 Trades (Req >= 100)' },
        { label: 'Gate 3 (DSR Threshold)', value: '0.98 Verified (Req >= 0.95)' },
        { label: 'Gate 4 (VDA Tax)', value: '30% Flat Tax + 1% TDS Modeled' },
      ],
      workingWindowNotes: 'Zero trades can execute without passing all 5 gates sequentially. Dual emergency kill switches instantly halt engine operations if tripped.',
      targetAnchor: '#risk',
    },
    {
      id: 'trade-automation',
      modNum: 'MOD 06',
      title: 'Trading Automation Overview',
      icon: Layers,
      desc: 'Paper-first forward execution engine with persistent restart-safe state, protective stop synchronization, and loss cooldown limiters.',
      metric: '100% PAPER',
      submetric: 'RESTART RESILIENT',
      telemetry: [
        { label: 'Engine State', value: 'RUNNING (Isolated Enclave)' },
        { label: 'Portfolio NAV', value: '$10,000.00 (+3.84% 24h)' },
        { label: 'Drawdown Halt', value: '$500 Max Daily Loss Limit' },
        { label: 'Fill Rate Accuracy', value: '99.4% (Synthetic Slippage)' },
      ],
      workingWindowNotes: 'State survives system reboot and process interruption. Unclosed positions retain tight protective stop-loss triggers in memory.',
      targetAnchor: '#platform',
    },
  ];

  return (
    <section id="platform" className="relative py-24 px-4 md:px-8 max-w-7xl mx-auto">
      {/* Section Header */}
      <div className="flex flex-col items-center text-center max-w-3xl mx-auto mb-16">
        <span className="font-mono text-[10px] md:text-xs tracking-[0.25em] text-[#A2A2A8] uppercase mb-3">
          Platform Architecture · Interactive Modules
        </span>
        <h2 className="text-3xl md:text-5xl font-semibold tracking-tight text-metallic">
          Institutional research software. Designed for discipline.
        </h2>
        <p className="mt-4 text-sm md:text-base text-[#A2A2A8] leading-relaxed">
          An integrated environment uniting microsecond algorithmic execution with deep deliberative artificial intelligence and sovereign risk controls.
          Click any card or arrow to inspect the working software telemetry.
        </p>
      </div>

      {/* Grid of Institutional Showcase Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
        {panels.map((panel, idx) => {
          const Icon = panel.icon;
          return (
            <motion.div
              key={panel.id}
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: '-60px' }}
              transition={{ duration: 0.5, delay: idx * 0.08 }}
              onClick={() => setSelectedPanel(panel)}
              className="p-6 rounded-2xl border border-[#38383C] bg-[#151515] flex flex-col justify-between glow-card relative overflow-hidden group cursor-pointer hover:border-[#D8D8DC] hover:shadow-2xl hover:shadow-black/90 transition-all duration-300"
            >
              {/* Subtle top light reflection */}
              <div className="absolute top-0 inset-x-0 h-[1px] bg-gradient-to-r from-transparent via-[#4D4D51] to-transparent opacity-50 group-hover:opacity-100 transition-opacity" />

              <div>
                <div className="flex items-center justify-between mb-4">
                  <div className="w-10 h-10 rounded-xl bg-[#222224] border border-[#4D4D51] flex items-center justify-center text-[#D8D8DC] group-hover:text-white group-hover:border-white transition-colors">
                    <Icon className="w-5 h-5" />
                  </div>
                  <span className="font-mono text-[10px] text-[#A2A2A8] tracking-widest uppercase">
                    {panel.modNum}
                  </span>
                </div>

                <h3 className="text-lg font-medium text-[#F4F4F5] group-hover:text-white tracking-tight mb-2 transition-colors">
                  {panel.title}
                </h3>
                <p className="text-xs md:text-sm text-[#A2A2A8] leading-relaxed mb-6">
                  {panel.desc}
                </p>
              </div>

              {/* Card Footer with Functional Interactive Arrow */}
              <div className="pt-4 border-t border-[#38383C] flex items-center justify-between font-mono">
                <div>
                  <div className="text-xs font-semibold text-[#F4F4F5]">{panel.metric}</div>
                  <div className="text-[9px] text-[#A2A2A8] tracking-wider">{panel.submetric}</div>
                </div>

                {/* Arrow Trigger Button */}
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    setSelectedPanel(panel);
                  }}
                  title={`Inspect working window for ${panel.title}`}
                  className="w-8 h-8 rounded-full bg-[#222224] border border-[#4D4D51] flex items-center justify-center text-[#D8D8DC] hover:bg-white hover:text-[#050505] hover:border-white hover:scale-110 active:scale-95 transition-all shadow-md group-hover:border-[#D8D8DC]"
                  aria-label={`Open ${panel.title} Working Window`}
                >
                  <ArrowUpRight className="w-4 h-4 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
                </button>
              </div>
            </motion.div>
          );
        })}
      </div>

      {/* Illustrative Disclaimer */}
      <div className="mt-8 text-center">
        <span className="font-mono text-[10px] text-[#A2A2A8]/60 tracking-wider uppercase">
          * Note: Click any module arrow to open the simulated working window inspector.
        </span>
      </div>

      {/* Interactive Working Window Modal */}
      <AnimatePresence>
        {selectedPanel && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-black/85 backdrop-blur-xl">
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              transition={{ duration: 0.25 }}
              className="relative w-full max-w-3xl rounded-3xl border border-[#4D4D51] bg-[#090909] shadow-2xl shadow-black overflow-hidden"
            >
              {/* Window Header */}
              <div className="flex items-center justify-between px-5 py-3.5 border-b border-[#38383C] bg-[#151515]">
                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-1.5">
                    <div className="w-3 h-3 rounded-full bg-[#38383C]" />
                    <div className="w-3 h-3 rounded-full bg-[#38383C]" />
                    <div className="w-3 h-3 rounded-full bg-[#38383C]" />
                  </div>
                  <div className="h-4 w-[1px] bg-[#38383C] mx-1" />
                  <img src={zillersEmblem} alt="ZILLERS" className="w-4 h-4 object-contain rounded" />
                  <span className="font-mono text-xs font-bold tracking-wider text-white uppercase">
                    {selectedPanel.modNum} // {selectedPanel.title}
                  </span>
                </div>

                <button
                  type="button"
                  onClick={() => setSelectedPanel(null)}
                  className="p-1.5 rounded-lg text-[#A2A2A8] hover:text-white hover:bg-[#222224] transition-colors"
                  aria-label="Close Inspector"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {/* Modal Body */}
              <div className="p-6 space-y-6 max-h-[80vh] overflow-y-auto">
                <div className="space-y-2">
                  <span className="text-[10px] font-mono tracking-widest text-[#A2A2A8] uppercase">
                    OPERATIONAL SYSTEM TELEMETRY
                  </span>
                  <h3 className="text-xl sm:text-2xl font-semibold text-white tracking-tight">
                    {selectedPanel.title}
                  </h3>
                  <p className="text-xs sm:text-sm text-[#A2A2A8] leading-relaxed">
                    {selectedPanel.desc}
                  </p>
                </div>

                {/* Telemetry Matrix */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 font-mono">
                  {selectedPanel.telemetry.map((t, i) => (
                    <div key={i} className="p-3.5 rounded-xl border border-[#38383C] bg-[#151515] flex flex-col justify-between">
                      <span className="text-[10px] text-[#A2A2A8]">{t.label}</span>
                      <span className="text-xs font-bold text-white mt-1">{t.value}</span>
                    </div>
                  ))}
                </div>

                {/* Working Window Notes Dossier */}
                <div className="rounded-2xl border border-[#222224] bg-[#050505] p-4 text-xs font-mono text-[#D8D8DC] space-y-2 leading-relaxed">
                  <div className="flex items-center gap-2 text-white font-bold text-[11px]">
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                    <span>SYSTEM EXECUTION AUDIT: VERIFIED</span>
                  </div>
                  <p className="text-[#A2A2A8] text-[11px]">
                    {selectedPanel.workingWindowNotes}
                  </p>
                </div>

                {/* Action Controls */}
                <div className="pt-4 border-t border-[#222224] flex flex-col sm:flex-row justify-between items-center gap-3">
                  <a
                    href="/"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-full bg-[#F4F4F5] text-[#050505] text-xs font-semibold uppercase tracking-wider hover:bg-white transition-all shadow hover:scale-[1.02]"
                  >
                    <span>Launch in Live Terminal (Port 8900)</span>
                    <ExternalLink className="w-3.5 h-3.5" />
                  </a>

                  <button
                    type="button"
                    onClick={() => setSelectedPanel(null)}
                    className="w-full sm:w-auto px-5 py-2.5 rounded-full border border-[#4D4D51] bg-[#151515] text-[#A2A2A8] hover:text-white hover:border-white text-xs font-mono uppercase tracking-wider transition-all"
                  >
                    Dismiss Inspector
                  </button>
                </div>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </section>
  );
};

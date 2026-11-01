import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Activity,
  Shield,
  Bot,
  Layers,
  ArrowUpRight,
  TrendingUp,
  TrendingDown,
  CheckCircle2,
  Lock,
  Cpu,
  BarChart2,
  Sliders,
  ExternalLink,
} from 'lucide-react';
import zillersEmblem from '../assets/emblem.png';

interface TerminalTab {
  id: string;
  name: string;
  badge: string;
  desc: string;
}

const TABS: TerminalTab[] = [
  {
    id: 'tactical',
    name: 'Tactical Workspace & Candles',
    badge: 'LIVE FEED',
    desc: 'Real-time multi-exchange candlestick charting, order book depth L3, and Laya AI deliberative signals.',
  },
  {
    id: 'strategy',
    name: 'Alpha Strategy Fleet',
    badge: '4 ENGINES',
    desc: 'Autonomous quantitative strategies tracking Smart Money Concepts (SMC), FVG, and VWAP arbitrage.',
  },
  {
    id: 'orderbook',
    name: 'L3 Market Depth & SOR',
    badge: '< 1ms SOR',
    desc: 'Microsecond bid/ask ladders aggregated from Binance, Coinbase, and Kraken with live spread telemetry.',
  },
  {
    id: 'laya',
    name: 'Laya AI Deliberation Room',
    badge: 'GEMMA 4 LOCAL',
    desc: 'Multi-agent consensus debate chamber evaluating macro risk, liquidity stress, and trade validity.',
  },
  {
    id: 'governor',
    name: '5-Gate Risk Governor',
    badge: 'FAIL-CLOSED',
    desc: 'Deterministic pre-trade verification checklist, Deflated Sharpe Ratio audit, and dual emergency kill-switch.',
  },
];

export const TerminalGallery: React.FC = () => {
  const [activeTab, setActiveTab] = useState<string>('tactical');

  return (
    <section className="relative py-24 px-4 md:px-8 max-w-7xl mx-auto border-t border-[#38383C]/40 bg-[#050505]">
      {/* Background illumination */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-1/3 left-1/2 -translate-x-1/2 w-[800px] h-[350px] bg-white/[0.02] blur-[120px] rounded-full" />
      </div>

      <div className="relative z-10">
        {/* Section Heading */}
        <div className="flex flex-col items-center text-center max-w-3xl mx-auto mb-12">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-[#4D4D51] bg-[#151515] text-[11px] font-mono tracking-wider uppercase text-[#D8D8DC] mb-4">
            <BarChart2 className="w-3.5 h-3.5 text-[#F4F4F5]" />
            <span>Working Software Enclave</span>
          </div>

          <h2 className="text-3xl sm:text-5xl font-semibold tracking-tight text-metallic">
            The live working engine.
          </h2>

          <p className="mt-4 text-sm sm:text-base text-[#A2A2A8] leading-relaxed">
            Inspect the actual operational interfaces, market depth visualizations, and autonomous decision pipelines
            powering the ZILLERS institutional research terminal.
          </p>

          {/* Interactive Navigation Tabs */}
          <div className="mt-8 flex flex-wrap items-center justify-center gap-2 p-1.5 rounded-2xl bg-[#090909] border border-[#38383C] max-w-fit">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveTab(tab.id)}
                className={`px-4 py-2 rounded-xl text-xs font-mono transition-all flex items-center gap-2 ${
                  activeTab === tab.id
                    ? 'bg-[#222224] text-[#F4F4F5] font-semibold border border-[#4D4D51] shadow-lg'
                    : 'text-[#A2A2A8] hover:text-[#F4F4F5] hover:bg-[#151515]'
                }`}
              >
                <span>{tab.name}</span>
                <span
                  className={`text-[9px] px-1.5 py-0.5 rounded ${
                    activeTab === tab.id
                      ? 'bg-[#151515] text-[#D8D8DC]'
                      : 'bg-[#151515] text-[#A2A2A8]/70'
                  }`}
                >
                  {tab.badge}
                </span>
              </button>
            ))}
          </div>
        </div>

        {/* Realistic Terminal Window Container */}
        <div className="relative rounded-3xl border border-[#4D4D51] bg-[#090909] shadow-[0_20px_70px_rgba(0,0,0,0.95)] overflow-hidden">
          {/* Mac/Linux Style Institutional Window Header */}
          <div className="flex flex-wrap items-center justify-between px-5 py-3.5 border-b border-[#38383C] bg-[#151515]">
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-3 rounded-full bg-[#38383C] border border-[#4D4D51]" />
                <div className="w-3 h-3 rounded-full bg-[#38383C] border border-[#4D4D51]" />
                <div className="w-3 h-3 rounded-full bg-[#38383C] border border-[#4D4D51]" />
              </div>
              <div className="h-4 w-[1px] bg-[#38383C] mx-1" />
              <img
                src={zillersEmblem}
                alt="ZILLERS"
                className="w-5 h-5 object-contain rounded"
              />
              <span className="font-mono text-xs font-bold tracking-widest text-white uppercase">
                ZILLERS
              </span>
              <span className="hidden sm:inline-block px-2 py-0.5 rounded bg-[#222224] border border-[#38383C] text-[10px] font-mono text-[#D8D8DC]">
                PROD // NY4 CO-LOCATED
              </span>
            </div>

            <div className="flex items-center gap-4 text-xs font-mono text-[#A2A2A8]">
              <div className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                <span className="text-[#F4F4F5]">CONNECTED</span>
              </div>
              <span className="hidden md:inline text-[#A2A2A8]">LATENCY: 0.84ms</span>
              <a
                href="/"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[#F4F4F5] text-[#050505] text-[11px] font-semibold tracking-wider hover:bg-white transition-all shadow"
              >
                <span>Open Terminal</span>
                <ExternalLink className="w-3 h-3" />
              </a>
            </div>
          </div>

          {/* Window Viewport Area */}
          <div className="p-4 sm:p-6 bg-[#090909] min-h-[500px]">
            <AnimatePresence mode="wait">
              {/* TAB 1: TACTICAL WORKSPACE */}
              {activeTab === 'tactical' && (
                <motion.div
                  key="tactical"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  transition={{ duration: 0.3 }}
                  className="space-y-4"
                >
                  {/* Top Metric Strip */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    <div className="p-3.5 rounded-xl border border-[#38383C] bg-[#151515]">
                      <div className="text-[10px] font-mono text-[#A2A2A8] flex justify-between">
                        <span>PORTFOLIO NAV</span>
                        <span className="text-emerald-400">+3.84% 24H</span>
                      </div>
                      <div className="mt-1 font-mono text-xl font-bold text-white">$10,000.00</div>
                      <div className="mt-1 text-[9px] font-mono text-[#A2A2A8]">PAPER RESEARCH ACCOUNT</div>
                    </div>

                    <div className="p-3.5 rounded-xl border border-[#38383C] bg-[#151515]">
                      <div className="text-[10px] font-mono text-[#A2A2A8] flex justify-between">
                        <span>OPEN POSITIONS / MTM</span>
                        <span className="text-[#D8D8DC]">SPOT L1</span>
                      </div>
                      <div className="mt-1 font-mono text-xl font-bold text-white">00 <span className="text-xs text-emerald-400 font-normal">+$0.00 MTM</span></div>
                      <div className="mt-1 text-[9px] font-mono text-[#A2A2A8]">FIFO LOTS ACTIVE</div>
                    </div>

                    <div className="p-3.5 rounded-xl border border-[#38383C] bg-[#151515]">
                      <div className="text-[10px] font-mono text-[#A2A2A8] flex justify-between">
                        <span>RISK ATTRIBUTION</span>
                        <span className="text-[#D8D8DC]">LOW VAR (95%)</span>
                      </div>
                      <div className="mt-1 font-mono text-xl font-bold text-white">3.42 <span className="text-xs text-[#A2A2A8]">/ 4.88</span></div>
                      <div className="mt-1 text-[9px] font-mono text-[#A2A2A8]">SHARPE / SORTINO RATIO</div>
                    </div>

                    <div className="p-3.5 rounded-xl border border-[#38383C] bg-[#151515]">
                      <div className="text-[10px] font-mono text-[#A2A2A8] flex justify-between">
                        <span>LATEST MODEL SIGNAL</span>
                        <span className="text-[#D8D8DC]">BTCUSDT</span>
                      </div>
                      <div className="mt-1 font-mono text-xl font-bold text-rose-400 flex items-center gap-1">
                        <TrendingDown className="w-5 h-5" />
                        <span>SHORT</span>
                      </div>
                      <div className="mt-1 text-[9px] font-mono text-[#A2A2A8]">CONFIDENCE: 85% · 23h ago</div>
                    </div>
                  </div>

                  {/* Main Grid: Chart + Orderbook + Laya Signal */}
                  <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
                    {/* Candlestick Chart Window (7 cols) */}
                    <div className="lg:col-span-7 rounded-2xl border border-[#38383C] bg-[#151515] p-4 flex flex-col justify-between">
                      <div className="flex items-center justify-between pb-3 border-b border-[#222224] text-xs font-mono">
                        <div className="flex items-center gap-2">
                          <Activity className="w-4 h-4 text-[#D8D8DC]" />
                          <span className="font-bold text-white">ALPHA PNL ATTRIBUTION & MARKET CONTEXT</span>
                        </div>
                        <div className="flex items-center gap-1.5 bg-[#090909] px-2.5 py-1 rounded-lg border border-[#38383C]">
                          <span className="text-white font-bold">ETHUSDT</span>
                          <span className="text-[#A2A2A8]">· 5m candles</span>
                        </div>
                      </div>

                      {/* Simulated High-Precision Candlestick Visualizer */}
                      <div className="h-64 my-3 relative bg-[#090909] rounded-xl border border-[#222224] p-3 flex flex-col justify-between overflow-hidden">
                        {/* Background Grid Lines */}
                        <div className="absolute inset-0 bg-[linear-gradient(to_right,#222224_1px,transparent_1px),linear-gradient(to_bottom,#222224_1px,transparent_1px)] bg-[size:40px_30px] opacity-40" />

                        {/* Price Axis Overlay */}
                        <div className="relative z-10 flex justify-between text-[10px] font-mono text-[#A2A2A8]">
                          <span>HIGH: 2,284.50 USDT</span>
                          <span>VWAP: 2,268.20 USDT</span>
                          <span>LOW: 2,242.10 USDT</span>
                        </div>

                        {/* Simulated Candle Bars */}
                        <div className="relative z-10 flex items-end justify-between gap-1.5 h-44 px-2">
                          {[
                            { h: 48, up: true, wickTop: 6, wickBot: 8 },
                            { h: 62, up: true, wickTop: 4, wickBot: 12 },
                            { h: 35, up: false, wickTop: 10, wickBot: 5 },
                            { h: 78, up: true, wickTop: 8, wickBot: 15 },
                            { h: 90, up: true, wickTop: 12, wickBot: 6 },
                            { h: 45, up: false, wickTop: 15, wickBot: 10 },
                            { h: 70, up: false, wickTop: 8, wickBot: 12 },
                            { h: 85, up: true, wickTop: 5, wickBot: 8 },
                            { h: 110, up: true, wickTop: 14, wickBot: 18 },
                            { h: 95, up: false, wickTop: 10, wickBot: 8 },
                            { h: 60, up: false, wickTop: 6, wickBot: 14 },
                            { h: 80, up: true, wickTop: 12, wickBot: 6 },
                            { h: 105, up: true, wickTop: 10, wickBot: 10 },
                            { h: 72, up: false, wickTop: 15, wickBot: 5 },
                            { h: 92, up: false, wickTop: 8, wickBot: 12 },
                            { h: 125, up: true, wickTop: 15, wickBot: 20 },
                          ].map((c, i) => (
                            <div key={i} className="flex-1 flex flex-col items-center justify-end h-full">
                              {/* Top Wick */}
                              <div
                                className={`w-[1px] ${c.up ? 'bg-emerald-400' : 'bg-rose-400'}`}
                                style={{ height: `${c.wickTop}px` }}
                              />
                              {/* Candle Body */}
                              <div
                                className={`w-full rounded-sm ${
                                  c.up ? 'bg-emerald-500/80 border border-emerald-400' : 'bg-rose-500/80 border border-rose-400'
                                }`}
                                style={{ height: `${c.h}px` }}
                              />
                              {/* Bottom Wick */}
                              <div
                                className={`w-[1px] ${c.up ? 'bg-emerald-400' : 'bg-rose-400'}`}
                                style={{ height: `${c.wickBot}px` }}
                              />
                            </div>
                          ))}
                        </div>

                        {/* SMC / FVG Imbalance Box Annotation */}
                        <div className="absolute top-16 right-16 px-2.5 py-1 rounded bg-white/10 border border-[#4D4D51] backdrop-blur-md text-[9px] font-mono text-white flex items-center gap-1.5 z-20">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                          <span>BULLISH FVG IMBALANCE: 2,263.40</span>
                        </div>

                        <div className="relative z-10 flex justify-between text-[9px] font-mono text-[#A2A2A8] pt-2 border-t border-[#222224]">
                          <span>18:00 UTC</span>
                          <span>18:30 UTC</span>
                          <span>19:00 UTC</span>
                          <span>19:30 UTC</span>
                          <span>20:00 UTC (CURRENT)</span>
                        </div>
                      </div>

                      {/* Strategy Share Breakdown */}
                      <div className="grid grid-cols-4 gap-2 pt-2 border-t border-[#222224] text-[10px] font-mono">
                        <div>
                          <span className="text-[#A2A2A8]">StatArb</span>
                          <div className="text-emerald-400 font-bold">+42.8%</div>
                        </div>
                        <div>
                          <span className="text-[#A2A2A8]">Funding Basis</span>
                          <div className="text-emerald-400 font-bold">+28.1%</div>
                        </div>
                        <div>
                          <span className="text-[#A2A2A8]">HFT Spreads</span>
                          <div className="text-emerald-400 font-bold">+21.3%</div>
                        </div>
                        <div>
                          <span className="text-[#A2A2A8]">Multi-Trend</span>
                          <div className="text-emerald-400 font-bold">+7.8%</div>
                        </div>
                      </div>
                    </div>

                    {/* Right Column: L3 Depth & Laya Signal (5 cols) */}
                    <div className="lg:col-span-5 space-y-4">
                      {/* Order Book L3 */}
                      <div className="rounded-2xl border border-[#38383C] bg-[#151515] p-4 font-mono">
                        <div className="flex justify-between items-center pb-2 mb-3 border-b border-[#222224] text-xs">
                          <span className="font-bold text-white">MARKET DEPTH L3 (ORDER BOOK)</span>
                          <span className="text-[10px] text-emerald-400">BINANCE + KRAKEN TICKER</span>
                        </div>

                        {/* Asks (Sell Orders) */}
                        <div className="space-y-1 text-[11px]">
                          {[
                            { price: '2264.18', size: '3.40', depth: 25 },
                            { price: '2263.93', size: '6.25', depth: 45 },
                            { price: '2263.68', size: '11.10', depth: 75 },
                            { price: '2263.43', size: '18.42', depth: 95 },
                          ].map((a, i) => (
                            <div key={i} className="flex justify-between items-center relative py-0.5 px-2 rounded">
                              <div
                                className="absolute right-0 top-0 bottom-0 bg-rose-500/15 rounded"
                                style={{ width: `${a.depth}%` }}
                              />
                              <span className="text-rose-400 z-10">{a.price}</span>
                              <span className="text-[#A2A2A8] z-10">{a.size} ETH</span>
                            </div>
                          ))}
                        </div>

                        {/* Midpoint Spread */}
                        <div className="my-2 py-1 px-3 rounded-lg bg-[#090909] border border-[#222224] flex justify-between items-center text-[10px]">
                          <span className="text-[#A2A2A8]">SPREAD: 0.01 USDT (0.000%)</span>
                          <span className="text-white font-bold">MID: 2263.43 USDT</span>
                        </div>

                        {/* Bids (Buy Orders) */}
                        <div className="space-y-1 text-[11px]">
                          {[
                            { price: '2263.42', size: '14.82', depth: 90 },
                            { price: '2263.17', size: '8.40', depth: 60 },
                            { price: '2262.92', size: '5.15', depth: 40 },
                            { price: '2262.67', size: '2.90', depth: 20 },
                          ].map((b, i) => (
                            <div key={i} className="flex justify-between items-center relative py-0.5 px-2 rounded">
                              <div
                                className="absolute left-0 top-0 bottom-0 bg-emerald-500/15 rounded"
                                style={{ width: `${b.depth}%` }}
                              />
                              <span className="text-emerald-400 z-10">{b.price}</span>
                              <span className="text-[#A2A2A8] z-10">{b.size} ETH</span>
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Laya AI Deliberative Recommendation Box */}
                      <div className="rounded-2xl border border-[#38383C] bg-[#151515] p-4 font-mono">
                        <div className="flex justify-between items-center pb-2 mb-2 border-b border-[#222224] text-xs">
                          <span className="font-bold text-white flex items-center gap-1.5">
                            <Bot className="w-3.5 h-3.5 text-[#D8D8DC]" />
                            LAYA DELIBERATIVE SIGNAL
                          </span>
                          <span className="text-[10px] text-[#A2A2A8]">LOCAL WEIGHTS</span>
                        </div>

                        <div className="flex items-center gap-3 my-2">
                          <div className="w-10 h-10 rounded-xl bg-rose-500/20 border border-rose-500/40 flex items-center justify-center text-rose-400">
                            <TrendingDown className="w-5 h-5" />
                          </div>
                          <div>
                            <div className="text-xs font-bold text-white">CONSENSUS: SHORT ETHUSDT</div>
                            <div className="text-[10px] text-[#A2A2A8]">Model Confidence: 85% · Net R:R 1:2.4</div>
                          </div>
                        </div>

                        <p className="text-[11px] text-[#A2A2A8] leading-snug mt-2 pt-2 border-t border-[#222224]">
                          Thesis: Negative Cumulative Volume Delta (CVD) divergence against 2,284 resistance with liquidity pools swept below 2,242.
                        </p>
                      </div>
                    </div>
                  </div>
                </motion.div>
              )}

              {/* TAB 2: ALPHA STRATEGY FLEET */}
              {activeTab === 'strategy' && (
                <motion.div
                  key="strategy"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  transition={{ duration: 0.3 }}
                  className="space-y-4"
                >
                  <div className="p-4 rounded-2xl border border-[#38383C] bg-[#151515]">
                    <h3 className="text-base font-semibold text-white tracking-tight mb-2">
                      Autonomous Strategy Engines · Execution Fleet
                    </h3>
                    <p className="text-xs text-[#A2A2A8] leading-relaxed mb-4">
                      Each quantitative strategy executes within an isolated thread enclave with real-time risk checks,
                      order placement throttles, and synthetic trailing stop synchronization.
                    </p>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {[
                        {
                          name: 'Smart Money Concepts (SMC)',
                          desc: 'Institutional order block discovery & liquidity sweep identification',
                          allocation: '$3,500.00',
                          pnl: '+$428.90 (+12.2%)',
                          status: 'RUNNING',
                          winRate: '71.4%',
                        },
                        {
                          name: 'Fair Value Gap (FVG) Momentum',
                          desc: '3-candle imbalance fill detection and rapid mitigation entries',
                          allocation: '$2,500.00',
                          pnl: '+$281.30 (+11.2%)',
                          status: 'RUNNING',
                          winRate: '68.9%',
                        },
                        {
                          name: 'VWAP Mean Reversion (Z-Score)',
                          desc: 'Statistical standard deviation bands around institutional volume weighted price',
                          allocation: '$2,000.00',
                          pnl: '+$213.00 (+10.6%)',
                          status: 'RUNNING',
                          winRate: '65.2%',
                        },
                        {
                          name: 'Funding Rate & Basis Arbitrage',
                          desc: 'Delta-neutral perpetual funding capture with spot hedge balance',
                          allocation: '$2,000.00',
                          pnl: '+$78.10 (+3.9%)',
                          status: 'RUNNING',
                          winRate: '94.1%',
                        },
                      ].map((strat, i) => (
                        <div key={i} className="p-4 rounded-xl border border-[#38383C] bg-[#090909] font-mono space-y-2">
                          <div className="flex justify-between items-center">
                            <span className="text-sm font-bold text-white">{strat.name}</span>
                            <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-400/10 text-emerald-400 border border-emerald-400/30">
                              {strat.status}
                            </span>
                          </div>
                          <p className="text-[11px] text-[#A2A2A8]">{strat.desc}</p>
                          <div className="pt-2 border-t border-[#222224] flex justify-between text-xs">
                            <span className="text-[#A2A2A8]">Allocated: <b className="text-white">{strat.allocation}</b></span>
                            <span className="text-[#A2A2A8]">Win Rate: <b className="text-white">{strat.winRate}</b></span>
                            <span className="text-emerald-400 font-bold">{strat.pnl}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </motion.div>
              )}

              {/* TAB 3: ORDERBOOK L3 */}
              {activeTab === 'orderbook' && (
                <motion.div
                  key="orderbook"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  transition={{ duration: 0.3 }}
                  className="space-y-4"
                >
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="md:col-span-2 p-4 rounded-2xl border border-[#38383C] bg-[#151515]">
                      <h4 className="text-sm font-semibold text-white mb-2">Aggregated Multi-Exchange Liquidity Depth</h4>
                      <p className="text-xs text-[#A2A2A8] mb-4">
                        Sub-millisecond WebSocket ticks coalesced from Binance Futures, Coinbase Prime, and Kraken.
                      </p>
                      <div className="h-64 rounded-xl bg-[#090909] border border-[#222224] p-4 flex flex-col justify-between font-mono text-xs">
                        <div className="flex justify-between text-[#A2A2A8] pb-2 border-b border-[#222224]">
                          <span>EXCHANGE</span>
                          <span>BEST BID</span>
                          <span>BEST ASK</span>
                          <span>SPREAD</span>
                          <span>WEIGHT</span>
                        </div>
                        <div className="space-y-3 py-2">
                          <div className="flex justify-between items-center">
                            <span className="text-white font-bold">BINANCE US</span>
                            <span className="text-emerald-400">2263.42</span>
                            <span className="text-rose-400">2263.43</span>
                            <span className="text-[#A2A2A8]">0.01 (0.00%)</span>
                            <span className="text-white">52%</span>
                          </div>
                          <div className="flex justify-between items-center">
                            <span className="text-white font-bold">COINBASE PRIME</span>
                            <span className="text-emerald-400">2263.40</span>
                            <span className="text-rose-400">2263.44</span>
                            <span className="text-[#A2A2A8]">0.04 (0.00%)</span>
                            <span className="text-white">31%</span>
                          </div>
                          <div className="flex justify-between items-center">
                            <span className="text-white font-bold">KRAKEN GLOBAL</span>
                            <span className="text-emerald-400">2263.38</span>
                            <span className="text-rose-400">2263.45</span>
                            <span className="text-[#A2A2A8]">0.07 (0.00%)</span>
                            <span className="text-white">17%</span>
                          </div>
                        </div>
                        <div className="pt-2 border-t border-[#222224] flex justify-between text-[11px] text-[#A2A2A8]">
                          <span>SYNTHETIC SOR MIDPOINT: <b className="text-white">2263.425 USDT</b></span>
                          <span>AGGREGATED TICK RATE: <b className="text-emerald-400">1,420 msgs/sec</b></span>
                        </div>
                      </div>
                    </div>

                    <div className="p-4 rounded-2xl border border-[#38383C] bg-[#151515] flex flex-col justify-between">
                      <div>
                        <h4 className="text-sm font-semibold text-white mb-2">Smart Order Router (SOR)</h4>
                        <div className="space-y-3 font-mono text-xs mt-4">
                          <div className="p-2.5 rounded-lg bg-[#090909] border border-[#222224]">
                            <span className="text-[#A2A2A8] text-[10px]">TICK INGEST</span>
                            <div className="text-white font-bold">0.12 ms</div>
                          </div>
                          <div className="p-2.5 rounded-lg bg-[#090909] border border-[#222224]">
                            <span className="text-[#A2A2A8] text-[10px]">INTERNAL ARBITRAGE SCAN</span>
                            <div className="text-white font-bold">0.34 ms</div>
                          </div>
                          <div className="p-2.5 rounded-lg bg-[#090909] border border-[#222224]">
                            <span className="text-[#A2A2A8] text-[10px]">PRE-TRADE 5-GATE AUDIT</span>
                            <div className="text-white font-bold">0.18 ms</div>
                          </div>
                          <div className="p-2.5 rounded-lg bg-[#090909] border border-[#222224]">
                            <span className="text-[#A2A2A8] text-[10px]">TOTAL ROUND-TRIP LATENCY</span>
                            <div className="text-emerald-400 font-bold">0.84 ms (NY4 Equinix)</div>
                          </div>
                        </div>
                      </div>
                      <div className="text-[10px] font-mono text-[#A2A2A8] mt-4">
                        Zero external API calls inside hot 1-second evaluation loop.
                      </div>
                    </div>
                  </div>
                </motion.div>
              )}

              {/* TAB 4: LAYA AI */}
              {activeTab === 'laya' && (
                <motion.div
                  key="laya"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  transition={{ duration: 0.3 }}
                  className="space-y-4"
                >
                  <div className="p-4 sm:p-6 rounded-2xl border border-[#38383C] bg-[#151515]">
                    <div className="flex justify-between items-center pb-3 mb-4 border-b border-[#222224]">
                      <div>
                        <h4 className="text-sm font-semibold text-white">Laya Multi-Agent Deliberation Chamber</h4>
                        <p className="text-xs text-[#A2A2A8]">Autonomous local AI committee debating candle close proposals</p>
                      </div>
                      <span className="px-2.5 py-1 rounded bg-[#222224] border border-[#4D4D51] text-[10px] font-mono text-white">
                        MODEL: GEMMA 4 (LOCAL)
                      </span>
                    </div>

                    <div className="space-y-3 font-mono text-xs">
                      <div className="p-3 rounded-xl bg-[#090909] border border-[#222224] space-y-1">
                        <div className="flex justify-between text-[11px]">
                          <span className="text-cyan-400 font-bold">AGENT 01 // TECHNICAL ANALYST</span>
                          <span className="text-[#A2A2A8]">WEIGHT: 0.35</span>
                        </div>
                        <p className="text-[#D8D8DC]">
                          "Identified 4H Bearish Order Block at 2,284.00. Rejection confirmed with 3-candle sweep and volume spike."
                        </p>
                      </div>

                      <div className="p-3 rounded-xl bg-[#090909] border border-[#222224] space-y-1">
                        <div className="flex justify-between text-[11px]">
                          <span className="text-emerald-400 font-bold">AGENT 02 // LIQUIDITY & SPREAD AUDITOR</span>
                          <span className="text-[#A2A2A8]">WEIGHT: 0.35</span>
                        </div>
                        <p className="text-[#D8D8DC]">
                          "Sufficient market depth on Binance L3 book. 0.01 USDT spread allows low-slippage entry for $3,500 position."
                        </p>
                      </div>

                      <div className="p-3 rounded-xl bg-[#090909] border border-[#222224] space-y-1">
                        <div className="flex justify-between text-[11px]">
                          <span className="text-amber-400 font-bold">AGENT 03 // MACRO REGIME VALIDATOR</span>
                          <span className="text-[#A2A2A8]">WEIGHT: 0.30</span>
                        </div>
                        <p className="text-[#D8D8DC]">
                          "BTC correlation at 0.88. Downside momentum in dominant pair validates short thesis. No high-impact macro news scheduled."
                        </p>
                      </div>

                      <div className="p-3.5 rounded-xl bg-white/[0.04] border border-[#4D4D51] flex justify-between items-center">
                        <div>
                          <span className="text-[10px] text-[#A2A2A8] uppercase">CONSENSUS VERDICT</span>
                          <div className="text-sm font-bold text-white">PROPOSAL APPROVED · CONFIDENCE 85%</div>
                        </div>
                        <span className="px-3 py-1 rounded-full bg-emerald-400/20 text-emerald-400 border border-emerald-400/40 text-xs font-bold">
                          GATE 3 READY
                        </span>
                      </div>
                    </div>
                  </div>
                </motion.div>
              )}

              {/* TAB 5: RISK GOVERNOR */}
              {activeTab === 'governor' && (
                <motion.div
                  key="governor"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  transition={{ duration: 0.3 }}
                  className="space-y-4"
                >
                  <div className="p-4 sm:p-6 rounded-2xl border border-[#38383C] bg-[#151515]">
                    <div className="flex justify-between items-center pb-3 mb-4 border-b border-[#222224]">
                      <div>
                        <h4 className="text-sm font-semibold text-white">5-Gate Quantitative Risk Governor</h4>
                        <p className="text-xs text-[#A2A2A8]">Fail-closed deterministic pre-trade validation checklist</p>
                      </div>
                      <span className="px-2.5 py-1 rounded bg-rose-500/20 border border-rose-500/40 text-[10px] font-mono text-rose-300">
                        KILL-SWITCH ARMED
                      </span>
                    </div>

                    <div className="space-y-2.5 font-mono text-xs">
                      {[
                        { gate: 'GATE 01', name: 'Forward Operation Verification', rule: 'Must operate in forward mode for >= 28 calendar days', status: 'VERIFIED (34 DAYS)', ok: true },
                        { gate: 'GATE 02', name: 'Statistical Trade Threshold', rule: 'Requires >= 100 closed forward trades across market regimes', status: 'VERIFIED (142 TRADES)', ok: true },
                        { gate: 'GATE 03', name: 'Deflated Sharpe Ratio (DSR)', rule: 'DSR must exceed 0.95 threshold controlling for data snooping', status: 'VERIFIED (DSR 0.98)', ok: true },
                        { gate: 'GATE 04', name: 'Statutory Indian Tax Regime', rule: 'Enforces 30% Flat VDA Tax + 1% TDS with strict zero loss set-off', status: 'ACTIVE IN PIPELINE', ok: true },
                        { gate: 'GATE 05', name: 'Persistent Drawdown Bound', rule: 'Daily loss halt ($500 limit) and maximum drawdown threshold (8%)', status: 'ARMED (MAX DD: 4.12%)', ok: true },
                      ].map((g, i) => (
                        <div key={i} className="p-3 rounded-xl bg-[#090909] border border-[#222224] flex items-center justify-between gap-4">
                          <div className="flex items-center gap-3">
                            <div className="w-6 h-6 rounded-full bg-emerald-400/20 text-emerald-400 flex items-center justify-center text-[10px] shrink-0">
                              ✓
                            </div>
                            <div>
                              <div className="text-xs font-bold text-white flex items-center gap-2">
                                <span>{g.gate}: {g.name}</span>
                              </div>
                              <p className="text-[11px] text-[#A2A2A8]">{g.rule}</p>
                            </div>
                          </div>
                          <span className="text-[10px] px-2.5 py-1 rounded bg-[#151515] border border-[#38383C] text-emerald-400 font-bold shrink-0">
                            {g.status}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </div>
    </section>
  );
};

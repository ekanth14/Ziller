import React from 'react';
import { motion } from 'framer-motion';
import { Shield, Cpu, Activity, ArrowRight } from 'lucide-react';

export const Hero: React.FC = () => {
  return (
    <section className="relative pt-24 pb-16 px-4 md:px-8 max-w-7xl mx-auto flex flex-col items-center">
      {/* Outer Rounded Stage Frame (Matching SwiftFunds reference layout) */}
      <div className="relative w-full rounded-[36px] border border-[#38383C] bg-[#090909] overflow-hidden shadow-2xl technical-grid star-dust">
        {/* Soft Radial Ambient Lighting at Top */}
        <div className="absolute top-0 inset-x-0 h-[480px] bg-gradient-to-b from-[#D8D8DC]/10 via-[#151515]/60 to-transparent pointer-events-none" />
        <div className="absolute -top-32 left-1/2 -translate-x-1/2 w-[700px] h-[350px] bg-white/[0.04] blur-[120px] rounded-full pointer-events-none" />

        {/* Content Container */}
        <div className="relative z-10 pt-16 md:pt-24 px-6 md:px-12 flex flex-col items-center text-center">
          {/* Eyebrow Label */}
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
            className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full border border-[#4D4D51] bg-[#151515]/80 backdrop-blur-md mb-8"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-[#D8D8DC] animate-pulse" />
            <span className="font-mono text-[10px] md:text-[11px] font-medium tracking-[0.2em] text-[#D8D8DC] uppercase">
              A Zien Organisation Company
            </span>
          </motion.div>

          {/* Primary Metallic Headline */}
          <motion.h1
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.1 }}
            className="text-4xl sm:text-6xl md:text-7xl lg:text-[76px] font-semibold tracking-[-0.03em] leading-[1.08] text-metallic max-w-4xl"
          >
            Precision engineered.<br />
            Intelligence driven.
          </motion.h1>

          {/* Supporting Subtitle */}
          <motion.p
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.2 }}
            className="mt-6 text-sm sm:text-base md:text-lg text-[#A2A2A8] max-w-2xl font-normal leading-relaxed"
          >
            Quantitative research, algorithmic automation, and AI-powered market intelligence.
            A new approach to systematic cryptocurrency trading.
          </motion.p>

          {/* Dual Action Buttons */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.3 }}
            className="mt-8 flex flex-wrap items-center justify-center gap-4"
          >
            <a
              href="#platform"
              className="inline-flex items-center gap-2 text-xs md:text-sm font-medium tracking-wide bg-[#F4F4F5] text-[#050505] px-6 py-3 rounded-full hover:bg-white transition-all shadow-lg hover:scale-[1.02]"
            >
              <span>Explore ZILLERS</span>
              <ArrowRight className="w-4 h-4" />
            </a>
            <a
              href="#technology"
              className="inline-flex items-center gap-2 text-xs md:text-sm font-medium tracking-wide bg-[#151515] text-[#D8D8DC] border border-[#4D4D51] px-6 py-3 rounded-full hover:bg-[#222224] transition-all hover:border-[#6B6B70]"
            >
              <span>Discover Our Technology</span>
            </a>
          </motion.div>

          {/* Emerging Software Dashboard Mockup (SwiftFunds reference style) */}
          <motion.div
            initial={{ opacity: 0, y: 60 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 1, delay: 0.4 }}
            className="relative mt-14 md:mt-20 w-full max-w-5xl -mb-24 md:-mb-32 z-20"
          >
            {/* Ambient Backlight Behind Dashboard */}
            <div className="absolute inset-0 -top-6 bg-gradient-to-t from-transparent via-[#D8D8DC]/[0.03] to-transparent blur-xl pointer-events-none" />

            {/* Dashboard Shell */}
            <div className="relative rounded-2xl border border-[#4D4D51] bg-[#111319] shadow-[0_30px_90px_rgba(0,0,0,0.95)] overflow-hidden">
              {/* Window Title Bar */}
              <div className="flex items-center justify-between px-4 py-3 border-b border-[#38383C] bg-[#151515]">
                <div className="flex items-center gap-2">
                  <div className="w-2.5 h-2.5 rounded-full bg-[#38383C]" />
                  <div className="w-2.5 h-2.5 rounded-full bg-[#38383C]" />
                  <div className="w-2.5 h-2.5 rounded-full bg-[#38383C]" />
                  <span className="ml-3 font-mono text-[10px] tracking-wider text-[#A2A2A8] uppercase">
                    ZILLERS // QUANTITATIVE DESK V4.2
                  </span>
                </div>
                <div className="flex items-center gap-3 font-mono text-[10px] text-[#A2A2A8]">
                  <span className="flex items-center gap-1.5 text-[#F4F4F5]">
                    <span className="w-1.5 h-1.5 rounded-full bg-[#D8D8DC]" />
                    NY4 CO-LOCATED
                  </span>
                  <span className="border-l border-[#38383C] pl-3">SYSTEMATIC MODE: PAPER</span>
                </div>
              </div>

              {/* Dashboard Content Grid */}
              <div className="p-4 md:p-6 grid grid-cols-12 gap-4 bg-[#090909]">
                {/* Metric Strips */}
                <div className="col-span-12 grid grid-cols-2 md:grid-cols-4 gap-3">
                  <div className="p-3.5 rounded-xl border border-[#38383C] bg-[#151515]">
                    <div className="flex items-center justify-between text-[10px] font-mono text-[#A2A2A8]">
                      <span>PORTFOLIO NAV</span>
                      <span className="text-[#D8D8DC] font-semibold">+3.84% 24H</span>
                    </div>
                    <div className="mt-1 font-mono text-xl md:text-2xl font-bold text-[#F4F4F5]">
                      $10,000.00
                    </div>
                    <div className="mt-1 text-[9px] font-mono text-[#A2A2A8]">
                      RESEARCH ENCLAVE
                    </div>
                  </div>

                  <div className="p-3.5 rounded-xl border border-[#38383C] bg-[#151515]">
                    <div className="flex items-center justify-between text-[10px] font-mono text-[#A2A2A8]">
                      <span>5-GATE RISK GOVERNOR</span>
                      <Shield className="w-3.5 h-3.5 text-[#D8D8DC]" />
                    </div>
                    <div className="mt-1 font-mono text-xl md:text-2xl font-bold text-[#D8D8DC]">
                      GATES VERIFIED
                    </div>
                    <div className="mt-1 text-[9px] font-mono text-[#A2A2A8]">
                      DSR: 0.98 · LOSS HALT: $500
                    </div>
                  </div>

                  <div className="p-3.5 rounded-xl border border-[#38383C] bg-[#151515]">
                    <div className="flex items-center justify-between text-[10px] font-mono text-[#A2A2A8]">
                      <span>TIER 1 EXECUTION</span>
                      <Activity className="w-3.5 h-3.5 text-[#D8D8DC]" />
                    </div>
                    <div className="mt-1 font-mono text-xl md:text-2xl font-bold text-[#F4F4F5]">
                      0.84 ms
                    </div>
                    <div className="mt-1 text-[9px] font-mono text-[#A2A2A8]">
                      SMC / FVG / REVERSION
                    </div>
                  </div>

                  <div className="p-3.5 rounded-xl border border-[#38383C] bg-[#151515]">
                    <div className="flex items-center justify-between text-[10px] font-mono text-[#A2A2A8]">
                      <span>LAYA AI REASONING</span>
                      <Cpu className="w-3.5 h-3.5 text-[#D8D8DC]" />
                    </div>
                    <div className="mt-1 font-mono text-xl md:text-2xl font-bold text-[#D8D8DC]">
                      DELIBERATING
                    </div>
                    <div className="mt-1 text-[9px] font-mono text-[#A2A2A8]">
                      MULTI-AGENT CONSENSUS
                    </div>
                  </div>
                </div>

                {/* Main Candlestick Chart Area (Monochrome High-End Styling) */}
                <div className="col-span-12 md:col-span-8 p-4 rounded-xl border border-[#38383C] bg-[#151515] flex flex-col justify-between min-h-[220px]">
                  <div className="flex items-center justify-between border-b border-[#38383C] pb-3">
                    <div className="flex items-center gap-3">
                      <span className="font-mono text-sm font-bold text-white">ETHUSDT</span>
                      <span className="font-mono text-xs text-[#A2A2A8]">Ethereum · 5m Candles</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="px-2 py-0.5 text-[9px] font-mono rounded bg-[#222224] text-[#D8D8DC] border border-[#38383C]">
                        VWAP 2,263.10
                      </span>
                      <span className="px-2 py-0.5 text-[9px] font-mono rounded bg-[#222224] text-[#D8D8DC] border border-[#38383C]">
                        EMA-20 OVERLAY
                      </span>
                    </div>
                  </div>

                  {/* Simulated Candle SVG Graphic in Monochrome FinTech Shades */}
                  <div className="py-4 relative h-36 w-full flex items-end justify-between px-2">
                    {/* Background Grid */}
                    <div className="absolute inset-0 flex flex-col justify-between pointer-events-none opacity-20">
                      <div className="w-full border-b border-dashed border-[#A2A2A8]" />
                      <div className="w-full border-b border-dashed border-[#A2A2A8]" />
                      <div className="w-full border-b border-dashed border-[#A2A2A8]" />
                    </div>

                    {/* Bars */}
                    {[
                      { h: '45%', o: 'bottom', up: true },
                      { h: '60%', o: 'bottom', up: true },
                      { h: '50%', o: 'top', up: false },
                      { h: '75%', o: 'bottom', up: true },
                      { h: '65%', o: 'top', up: false },
                      { h: '85%', o: 'bottom', up: true },
                      { h: '70%', o: 'top', up: false },
                      { h: '90%', o: 'bottom', up: true },
                      { h: '80%', o: 'top', up: false },
                      { h: '95%', o: 'bottom', up: true },
                      { h: '88%', o: 'top', up: false },
                      { h: '100%', o: 'bottom', up: true },
                    ].map((b, i) => (
                      <div key={i} className="flex flex-col items-center flex-1 mx-1 h-full justify-end">
                        <div className="w-[1px] h-full bg-[#4D4D51]" />
                        <div
                          style={{ height: b.h }}
                          className={`w-3 rounded-xs ${
                            b.up ? 'bg-[#D8D8DC] border border-white' : 'bg-[#222224] border border-[#4D4D51]'
                          }`}
                        />
                      </div>
                    ))}
                  </div>

                  <div className="flex items-center justify-between text-[10px] font-mono text-[#A2A2A8] pt-2 border-t border-[#38383C]">
                    <span>RANGE: 2,240.00 — 2,284.50</span>
                    <span className="text-[#F4F4F5]">SMC ORDER BLOCK: MITIGATED</span>
                    <span>VOLUME: 14.82 ETH</span>
                  </div>
                </div>

                {/* Market Depth L3 Ladder */}
                <div className="col-span-12 md:col-span-4 p-4 rounded-xl border border-[#38383C] bg-[#151515] flex flex-col justify-between font-mono text-[10px]">
                  <div className="flex items-center justify-between border-b border-[#38383C] pb-2">
                    <span className="text-[#F4F4F5] font-semibold">L3 MARKET DEPTH</span>
                    <span className="text-[#A2A2A8]">BINANCE + CB</span>
                  </div>

                  <div className="space-y-1.5 my-2">
                    <div className="flex justify-between text-[#A2A2A8]">
                      <span>BID PRICE</span>
                      <span>SIZE</span>
                      <span>ASK PRICE</span>
                    </div>
                    {[
                      { bid: '2,263.42', size: '14.82', ask: '2,263.43', askSize: '18.42' },
                      { bid: '2,263.17', size: '8.40', ask: '2,263.68', askSize: '11.10' },
                      { bid: '2,262.92', size: '5.15', ask: '2,263.93', askSize: '6.25' },
                      { bid: '2,262.67', size: '2.90', ask: '2,264.18', askSize: '3.40' },
                    ].map((row, i) => (
                      <div key={i} className="flex justify-between items-center py-0.5 border-b border-[#222224]">
                        <span className="text-[#D8D8DC] font-medium">{row.bid}</span>
                        <span className="text-[#A2A2A8]">{row.size}</span>
                        <span className="text-white font-medium">{row.ask}</span>
                      </div>
                    ))}
                  </div>

                  <div className="pt-2 border-t border-[#38383C] flex justify-between text-[#A2A2A8]">
                    <span>SPREAD: 0.01 USDT</span>
                    <span className="text-[#D8D8DC]">MID: 2,263.43</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Illustrative Concept Disclaimer Ribbon */}
            <div className="text-center mt-3">
              <span className="font-mono text-[9px] tracking-wider text-[#A2A2A8]/70 uppercase">
                Illustrative Software Concept // Fictionalized Institutional Research UI
              </span>
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  );
};

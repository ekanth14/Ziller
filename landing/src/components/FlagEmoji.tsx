import React from 'react';

interface FlagProps {
  className?: string;
  title?: string;
}

export const KarnatakaFlagEmoji: React.FC<FlagProps> = ({
  className = "w-4 h-2.5",
  title = "Karnataka, India (ಕರ್ನಾಟಕ)",
}) => (
  <span
    className={`inline-flex items-center justify-center align-middle select-none shrink-0 ${className}`}
    title={title}
    role="img"
    aria-label={title}
  >
    <svg
      viewBox="0 0 36 24"
      className="w-full h-full overflow-hidden rounded-[2.5px] shadow-[0_1px_3px_rgba(0,0,0,0.5)] border border-white/20"
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        <clipPath id="kn-flag-clip">
          <rect width="36" height="24" rx="2.5" ry="2.5" />
        </clipPath>
        <linearGradient id="kn-gloss" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#ffffff" stopOpacity="0.28" />
          <stop offset="45%" stopColor="#ffffff" stopOpacity="0.04" />
          <stop offset="100%" stopColor="#000000" stopOpacity="0.22" />
        </linearGradient>
        <linearGradient id="kn-yellow" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#FFE014" />
          <stop offset="100%" stopColor="#F5B200" />
        </linearGradient>
        <linearGradient id="kn-red" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#E21836" />
          <stop offset="100%" stopColor="#B30C22" />
        </linearGradient>
      </defs>

      <g clipPath="url(#kn-flag-clip)">
        {/* Top Half: Yellow / Arishina (Auspiciousness & Prosperity) */}
        <rect x="0" y="0" width="36" height="12" fill="url(#kn-yellow)" />
        {/* Bottom Half: Red / Kumkuma (Courage & Bravery) */}
        <rect x="0" y="12" width="36" height="12" fill="url(#kn-red)" />
        {/* Subtle Specular Sheen for Emoji Depth */}
        <rect x="0" y="0" width="36" height="24" fill="url(#kn-gloss)" pointerEvents="none" />
      </g>
    </svg>
  </span>
);

export const IndiaFlagEmoji: React.FC<FlagProps> = ({
  className = "w-4 h-2.5",
  title = "India (भारत / 🇮🇳)",
}) => (
  <span
    className={`inline-flex items-center justify-center align-middle select-none shrink-0 ${className}`}
    title={title}
    role="img"
    aria-label={title}
  >
    <svg
      viewBox="0 0 36 24"
      className="w-full h-full overflow-hidden rounded-[2.5px] shadow-[0_1px_3px_rgba(0,0,0,0.5)] border border-white/20"
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        <clipPath id="in-flag-clip">
          <rect width="36" height="24" rx="2.5" ry="2.5" />
        </clipPath>
        <linearGradient id="in-gloss" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#ffffff" stopOpacity="0.28" />
          <stop offset="45%" stopColor="#ffffff" stopOpacity="0.04" />
          <stop offset="100%" stopColor="#000000" stopOpacity="0.22" />
        </linearGradient>
        <linearGradient id="in-saffron" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#FF9933" />
          <stop offset="100%" stopColor="#E67300" />
        </linearGradient>
        <linearGradient id="in-green" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#138808" />
          <stop offset="100%" stopColor="#0D5C06" />
        </linearGradient>
      </defs>

      <g clipPath="url(#in-flag-clip)">
        {/* Top: Saffron / Kesari */}
        <rect x="0" y="0" width="36" height="8" fill="url(#in-saffron)" />
        {/* Middle: White */}
        <rect x="0" y="8" width="36" height="8" fill="#FFFFFF" />
        {/* Bottom: India Green */}
        <rect x="0" y="16" width="36" height="8" fill="url(#in-green)" />

        {/* Ashoka Chakra in Navy Blue */}
        <g transform="translate(18, 12)">
          <circle r="3.2" fill="none" stroke="#000080" strokeWidth="0.6" />
          <circle r="0.75" fill="#000080" />
          <line x1="0" y1="-3.2" x2="0" y2="3.2" stroke="#000080" strokeWidth="0.32" />
          <line x1="0" y1="-3.2" x2="0" y2="3.2" stroke="#000080" strokeWidth="0.32" transform="rotate(15)" />
          <line x1="0" y1="-3.2" x2="0" y2="3.2" stroke="#000080" strokeWidth="0.32" transform="rotate(30)" />
          <line x1="0" y1="-3.2" x2="0" y2="3.2" stroke="#000080" strokeWidth="0.32" transform="rotate(45)" />
          <line x1="0" y1="-3.2" x2="0" y2="3.2" stroke="#000080" strokeWidth="0.32" transform="rotate(60)" />
          <line x1="0" y1="-3.2" x2="0" y2="3.2" stroke="#000080" strokeWidth="0.32" transform="rotate(75)" />
          <line x1="0" y1="-3.2" x2="0" y2="3.2" stroke="#000080" strokeWidth="0.32" transform="rotate(90)" />
          <line x1="0" y1="-3.2" x2="0" y2="3.2" stroke="#000080" strokeWidth="0.32" transform="rotate(105)" />
          <line x1="0" y1="-3.2" x2="0" y2="3.2" stroke="#000080" strokeWidth="0.32" transform="rotate(120)" />
          <line x1="0" y1="-3.2" x2="0" y2="3.2" stroke="#000080" strokeWidth="0.32" transform="rotate(135)" />
          <line x1="0" y1="-3.2" x2="0" y2="3.2" stroke="#000080" strokeWidth="0.32" transform="rotate(150)" />
          <line x1="0" y1="-3.2" x2="0" y2="3.2" stroke="#000080" strokeWidth="0.32" transform="rotate(165)" />
        </g>

        {/* Specular Emoji Gloss */}
        <rect x="0" y="0" width="36" height="24" fill="url(#in-gloss)" pointerEvents="none" />
      </g>
    </svg>
  </span>
);

export const RegionalFlagsBadge: React.FC<{
  className?: string;
  showLabel?: boolean;
  label?: string;
}> = ({
  className = "",
  showLabel = true,
  label = "Karnataka · India",
}) => (
  <span
    className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[#151515] border border-[#38383C] text-[#D8D8DC] shadow-sm hover:border-[#D8D8DC]/60 transition-all ${className}`}
  >
    <span className="inline-flex items-center gap-1">
      <KarnatakaFlagEmoji className="w-4 h-2.5" />
      <IndiaFlagEmoji className="w-4 h-2.5" />
    </span>
    {showLabel && (
      <span className="text-[10px] font-mono tracking-wider uppercase text-[#A2A2A8]">
        {label}
      </span>
    )}
  </span>
);

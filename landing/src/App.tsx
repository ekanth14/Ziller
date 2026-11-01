import React, { useEffect, useState } from 'react';
import { Navigation } from './components/Navigation';
import { Hero } from './components/Hero';
import { ProductShowcase } from './components/ProductShowcase';
import { TerminalGallery } from './components/TerminalGallery';
import { Introduction } from './components/Introduction';
import { CoreCapabilities } from './components/CoreCapabilities';
import { ArchitecturePipeline } from './components/ArchitecturePipeline';
import { LayaAISection } from './components/LayaAISection';
import { RiskPhilosophy } from './components/RiskPhilosophy';
import { FreePhilosophy } from './components/FreePhilosophy';
import { SetupGuide } from './components/SetupGuide';
import { FAQ } from './components/FAQ';
import { ZienOrganisation } from './components/ZienOrganisation';
import { Collaborate } from './components/Collaborate';
import { Footer } from './components/Footer';
import { MobileHome } from './components/MobileHome';
import { ArrowLeft, Smartphone } from 'lucide-react';
import zillersEmblem from './assets/emblem.png';

export const App: React.FC = () => {
  const [route, setRoute] = useState<'home' | 'collaborate' | 'setup'>(() => {
    if (window.location.pathname.startsWith('/setup')) return 'setup';
    if (window.location.pathname.startsWith('/collaborate')) return 'collaborate';
    return 'home';
  });

  const [isMobile, setIsMobile] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false;
    const saved = sessionStorage.getItem('zillers_view_mode');
    if (saved === 'desktop') return false;
    if (saved === 'mobile') return true;
    return window.innerWidth < 768;
  });

  useEffect(() => {
    const handleResize = () => {
      const saved = sessionStorage.getItem('zillers_view_mode');
      if (!saved) {
        setIsMobile(window.innerWidth < 768);
      }
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const toggleViewMode = () => {
    const nextMode = isMobile ? 'desktop' : 'mobile';
    sessionStorage.setItem('zillers_view_mode', nextMode);
    setIsMobile(!isMobile);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  useEffect(() => {
    const handleLocationChange = () => {
      if (window.location.pathname.startsWith('/setup')) {
        setRoute('setup');
      } else if (window.location.pathname.startsWith('/collaborate')) {
        setRoute('collaborate');
      } else {
        setRoute('home');
      }
    };

    window.addEventListener('popstate', handleLocationChange);
    return () => window.removeEventListener('popstate', handleLocationChange);
  }, []);

  // Handle smooth scroll if landing with hash
  useEffect(() => {
    if (window.location.hash) {
      const elem = document.querySelector(window.location.hash);
      if (elem) {
        setTimeout(() => {
          elem.scrollIntoView({ behavior: 'smooth' });
        }, 150);
      }
    }
  }, [route]);

  const navigateToHome = (e: React.MouseEvent) => {
    e.preventDefault();
    window.history.pushState({}, '', '/');
    setRoute('home');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  if (route === 'setup') {
    return (
      <div className="min-h-screen bg-[#050505] text-[#F4F4F5] selection:bg-[#38383C] selection:text-white relative overflow-x-hidden font-sans">
        {/* Dedicated Back Bar */}
        <header className="fixed top-5 inset-x-0 z-50 flex justify-center px-4 pointer-events-none">
          <nav className="pointer-events-auto flex items-center justify-between gap-6 px-4 py-2.5 rounded-full border bg-[#151515]/90 border-[#4D4D51] shadow-2xl backdrop-blur-xl max-w-fit w-full">
            <button
              type="button"
              onClick={navigateToHome}
              className="flex items-center gap-2 text-xs font-mono text-[#A2A2A8] hover:text-[#F4F4F5] transition-colors"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>Back to Overview</span>
            </button>

            <a href="#" onClick={navigateToHome} className="flex items-center gap-2 px-2">
              <img
                src={zillersEmblem}
                alt="ZILLERS"
                className="w-5 h-5 object-contain rounded-md opacity-90"
                onError={(e) => {
                  (e.target as HTMLElement).style.display = 'none';
                }}
              />
              <span className="font-mono text-xs font-semibold tracking-widest text-[#F4F4F5] uppercase">
                ZILLERS
              </span>
            </a>
          </nav>
        </header>

        <main>
          <SetupGuide isStandalone={true} />
        </main>

        <Footer />
      </div>
    );
  }

  if (route === 'collaborate') {
    return (
      <div className="min-h-screen bg-[#050505] text-[#F4F4F5] selection:bg-[#38383C] selection:text-white relative overflow-x-hidden font-sans">
        {/* Dedicated Back Bar */}
        <header className="fixed top-5 inset-x-0 z-50 flex justify-center px-4 pointer-events-none">
          <nav className="pointer-events-auto flex items-center justify-between gap-6 px-4 py-2.5 rounded-full border bg-[#151515]/90 border-[#4D4D51] shadow-2xl backdrop-blur-xl max-w-fit w-full">
            <button
              type="button"
              onClick={navigateToHome}
              className="flex items-center gap-2 text-xs font-mono text-[#A2A2A8] hover:text-[#F4F4F5] transition-colors"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>Back to Overview</span>
            </button>

            <a href="#" onClick={navigateToHome} className="flex items-center gap-2 px-2">
              <img
                src={zillersEmblem}
                alt="ZILLERS"
                className="w-5 h-5 object-contain rounded-md opacity-90"
                onError={(e) => {
                  (e.target as HTMLElement).style.display = 'none';
                }}
              />
              <span className="font-mono text-xs font-semibold tracking-widest text-[#F4F4F5] uppercase">
                ZILLERS
              </span>
            </a>
          </nav>
        </header>

        <main>
          <Collaborate isStandalone={true} />
        </main>

        <Footer />
      </div>
    );
  }

  // 1. MOBILE-FIRST STREAMLINED VIEW (NO HEAVY PICTOGRAPHY)
  if (isMobile) {
    return <MobileHome onSwitchToDesktop={toggleViewMode} />;
  }

  // 2. FULL DESKTOP TERMINAL VIEWPORT
  return (
    <div className="min-h-screen bg-[#050505] text-[#F4F4F5] selection:bg-[#38383C] selection:text-white relative overflow-x-hidden font-sans">
      {/* Smoked Glass Top Navigation */}
      <Navigation />

      {/* Floating View Switcher (Desktop to Mobile tester) */}
      <div className="fixed bottom-4 right-4 z-40">
        <button
          type="button"
          onClick={toggleViewMode}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-[#18181B]/80 hover:bg-[#27272A] border border-[#38383C] text-[11px] font-mono text-[#A2A2A8] hover:text-white shadow-xl backdrop-blur-md transition-all"
          title="Switch to Mobile View"
        >
          <Smartphone className="w-3.5 h-3.5" />
          <span>Mobile View</span>
        </button>
      </div>

      {/* Main Flow */}
      <main>
        {/* 1. Hero Viewport Stage */}
        <Hero />

        {/* 2. Institutional Product Showcase (With Interactive Working Window Arrows) */}
        <ProductShowcase />

        {/* 3. Live System Workspace – Authentic Working Windows Gallery */}
        <TerminalGallery />

        {/* 4. Introducing ZILLERS */}
        <Introduction />

        {/* 5. Core Capabilities */}
        <CoreCapabilities />

        {/* 6. Technology Architecture Pipeline */}
        <ArchitecturePipeline />

        {/* 7. Dedicated Laya AI Section */}
        <LayaAISection />

        {/* 8. Risk and Research Philosophy */}
        <RiskPhilosophy />

        {/* 9. Free Software Philosophy */}
        <FreePhilosophy />

        {/* 10. Developer Documentation & Setup Guide */}
        <SetupGuide isStandalone={false} />

        {/* 11. FAQ Knowledge Base (AEO & Search Generative Snippets) */}
        <FAQ />

        {/* 12. Zien Organisation Parent Showcase */}
        <ZienOrganisation />

        {/* 13. Collaborate and Build Together */}
        <Collaborate isStandalone={false} />
      </main>

      {/* 14. Closing Section and Minimalist Footer */}
      <Footer />
    </div>
  );
};

export default App;

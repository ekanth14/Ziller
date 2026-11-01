import React, { useEffect, useState } from 'react';
import { Navigation } from './components/Navigation';
import { Hero } from './components/Hero';
import { ProductShowcase } from './components/ProductShowcase';
import { Introduction } from './components/Introduction';
import { CoreCapabilities } from './components/CoreCapabilities';
import { ArchitecturePipeline } from './components/ArchitecturePipeline';
import { LayaAISection } from './components/LayaAISection';
import { RiskPhilosophy } from './components/RiskPhilosophy';
import { FreePhilosophy } from './components/FreePhilosophy';
import { ZienOrganisation } from './components/ZienOrganisation';
import { Collaborate } from './components/Collaborate';
import { Footer } from './components/Footer';
import { ArrowLeft } from 'lucide-react';

export const App: React.FC = () => {
  const [isCollaboratePage, setIsCollaboratePage] = useState<boolean>(() => {
    return window.location.pathname.startsWith('/collaborate');
  });

  useEffect(() => {
    const handleLocationChange = () => {
      setIsCollaboratePage(window.location.pathname.startsWith('/collaborate'));
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
  }, [isCollaboratePage]);

  const navigateToHome = (e: React.MouseEvent) => {
    e.preventDefault();
    window.history.pushState({}, '', '/');
    setIsCollaboratePage(false);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  if (isCollaboratePage) {
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
                src="./assets/emblem.png"
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

  return (
    <div className="min-h-screen bg-[#050505] text-[#F4F4F5] selection:bg-[#38383C] selection:text-white relative overflow-x-hidden font-sans">
      {/* Smoked Glass Top Navigation */}
      <Navigation />

      {/* Main Flow */}
      <main>
        {/* 1. Hero Viewport Stage */}
        <Hero />

        {/* 2. Institutional Product Showcase */}
        <ProductShowcase />

        {/* 3. Introducing ZILLERS */}
        <Introduction />

        {/* 4. Core Capabilities */}
        <CoreCapabilities />

        {/* 5. Technology Architecture Pipeline */}
        <ArchitecturePipeline />

        {/* 6. Dedicated Laya AI Section */}
        <LayaAISection />

        {/* 7. Risk and Research Philosophy */}
        <RiskPhilosophy />

        {/* 8. Free Software Philosophy */}
        <FreePhilosophy />

        {/* 9. Zien Organisation Parent Showcase */}
        <ZienOrganisation />

        {/* 10. Collaborate and Build Together */}
        <Collaborate isStandalone={false} />
      </main>

      {/* 11. Closing Section and Minimalist Footer */}
      <Footer />
    </div>
  );
};

export default App;

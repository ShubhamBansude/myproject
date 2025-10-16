// src/components/WelcomePage.jsx
import React from 'react';

const WelcomePage = ({ onGetStarted }) => {
  return (
    <div className="min-h-screen w-screen relative overflow-hidden bg-black font-sans">
      {/* Background image subtle overlay */}
      <div className="absolute inset-0 -z-10">
        <picture>
          <source srcSet="/bg-login.webp" type="image/webp" />
          <img
            src="/bg-login.jpg"
            alt="bg"
            className="w-full h-full object-cover opacity-[0.35]"
            loading="lazy"
            decoding="async"
            fetchpriority="low"
          />
        </picture>
        <div className="absolute inset-0 bg-gradient-to-br from-black/50 via-black/40 to-black/30" />
      </div>

      {/* Dotted matrix background */}
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.06]"
        style={{
          backgroundImage:
            'radial-gradient(rgba(255,255,255,0.28) 1px, transparent 1px)',
          backgroundSize: '22px 22px',
        }}
      />

      {/* Animated gradient blobs */}
      <div className="pointer-events-none absolute -top-32 -left-32 w-[40rem] h-[40rem] bg-eco-green/20 rounded-full blur-3xl animate-pulse-slow" />
      <div className="pointer-events-none absolute -bottom-40 -right-32 w-[45rem] h-[45rem] bg-eco-accent/30 rounded-full blur-3xl animate-float-slow" />

      {/* Minimal top bar (brand + login) */}
      <header className="relative z-20 flex items-center justify-between px-6 md:px-12 py-6">
        <div className="flex items-center space-x-3">
          <img
            src="/swachh-bharat.svg"
            alt="Swachh Bharat"
            className="h-6 w-auto opacity-90"
          />
          <div className="flex items-center space-x-2">
            <span className="text-gray-100 font-extrabold text-xl font-display">
              Waste
            </span>
            <span className="text-eco-green font-extrabold text-xl font-display">
              Bounty
            </span>
          </div>
        </div>
        <nav className="hidden md:flex items-center gap-6 text-gray-300">
          <a href="#how" className="hover:text-white transition">
            How it works
          </a>
          <a href="#features" className="hover:text-white transition">
            Features
          </a>
          <a href="#about" className="hover:text-white transition">
            About
          </a>
        </nav>
        <button
          onClick={onGetStarted}
          className="relative group px-4 py-2 rounded-full bg-white/5 text-gray-200 border border-white/10 transition-all duration-300 hover:bg-white/10 hover:-translate-y-0.5"
        >
          <span className="absolute inset-0 rounded-full bg-eco-green/20 blur opacity-0 group-hover:opacity-100 transition" />
          <span className="relative flex items-center gap-2">
            Log In
            <span className="transform transition-transform duration-300 group-hover:translate-x-0.5">
              →
            </span>
          </span>
        </button>
      </header>

      {/* Centered Hero */}
      <section className="relative z-10 flex items-center justify-center px-6 md:px-12">
        <div className="text-center max-w-5xl w-full">
          <h1 className="text-[44px] md:text-[62px] leading-[1.05] font-black tracking-tight bg-clip-text text-transparent bg-[linear-gradient(180deg,#e5f8ef,rgba(255,255,255,0.55))] font-display [text-shadow:_0_8px_40px_rgba(16,185,129,0.12)] animate-hue">
            Waste<span className="text-eco-green">Rewards</span> & Bounty
          </h1>
          <div className="mx-auto mt-3 h-[3px] w-28 rounded-full bg-gradient-to-r from-eco-green via-white/40 to-eco-accent animate-shimmer" />

          {/* Glass info block with richer copy */}
          <div className="mt-6 mx-auto max-w-3xl rounded-2xl bg-white/5 border border-white/10 p-5 backdrop-blur-md shadow-xl animate-fadeUp">
            <p className="text-[18px] md:text-[20px] text-gray-200/90">
              Turn your everyday waste into real perks. Our{' '}
              <span className="text-eco-green font-semibold">AI</span> spots
              recyclable and hazardous items in your photos, lets you{' '}
              <span className="text-eco-accent font-semibold">
                report waste hotspots
              </span>{' '}
              as bounties, coordinate cleanups with your city, and redeem
              eco-friendly rewards straight from your dashboard.
            </p>
            <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
              {[
                'Fast detection',
                'Privacy-first',
                'Real rewards',
                'Student friendly',
              ].map((t, i) => (
                <span
                  key={i}
                  className="px-3 py-1 rounded-full text-xs md:text-sm bg-white/10 text-gray-100 border border-white/10"
                >
                  {t}
                </span>
              ))}
            </div>
          </div>

          <div className="mt-8 flex items-center justify-center gap-4">
            <button
              onClick={onGetStarted}
              className="relative px-8 py-4 rounded-full bg-eco-accent text-eco-dark font-bold transition-all duration-300 hover:scale-[1.03] focus:scale-[1.02]"
            >
              <span className="absolute -inset-0.5 rounded-full bg-gradient-to-r from-eco-accent/35 to-eco-green/35 blur opacity-60 animate-pulse-slow" />
              <span className="relative flex items-center gap-2">
                Get Started <span>🚀</span>
              </span>
            </button>
            <a
              href="#how"
              className="px-8 py-4 rounded-full bg-white/10 text-gray-100 border border-white/10 font-semibold hover:bg-white/20 transition-all duration-300"
            >
              How it works
            </a>
          </div>

          {/* Impact strip */}
          <div className="mt-8 grid grid-cols-3 gap-3 max-w-xl mx-auto text-center">
            {[
              { n: '100K+', l: 'Detections' },
              { n: '3K+', l: 'Rewards Claimed' },
              { n: '50K+', l: 'Items Recycled' },
            ].map((s, i) => (
              <div
                key={i}
                className="rounded-xl bg-white/5 border border-white/10 p-4"
              >
                <div className="text-xl md:text-2xl font-extrabold text-gray-100 font-display">
                  {s.n}
                </div>
                <div className="text-xs text-gray-400">{s.l}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="relative z-10 px-6 md:px-12 mt-12">
        <div className="max-w-6xl mx-auto grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {[
            {
              icon: '🧠',
              title: 'AI Waste Detection',
              desc: 'Detect recyclable, hazardous, and general waste in a snap.',
            },
            {
              icon: '🗺️',
              title: 'Waste Bounty',
              desc: 'Report public waste spots and mobilize cleanups.',
            },
            {
              icon: '🎁',
              title: 'Rewards Shop',
              desc: 'Redeem eco-friendly coupons with your points.',
            },
            {
              icon: '🛡️',
              title: 'Clans & Leaderboard',
              desc: 'Team up, compete, and climb city ranks.',
            },
          ].map((f, i) => (
            <div
              key={i}
              className="rounded-2xl bg-white/5 backdrop-blur border border-white/10 p-5 hover:bg-white/10 transition-colors animate-fadeUp"
              style={{ animationDelay: `${80 * (i + 1)}ms` }}
            >
              <div className="text-3xl mb-2">{f.icon}</div>
              <div className="text-gray-100 font-semibold text-lg font-display">
                {f.title}
              </div>
              <div className="text-gray-300/90 text-sm mt-1">{f.desc}</div>
            </div>
          ))}
        </div>
      </section>

      {/* How It Works */}
      <section id="how" className="relative z-10 px-6 md:px-12 mt-16 md:mt-24">
        <div className="max-w-6xl mx-auto">
          <div className="grid md:grid-cols-4 gap-6">
            {[
              {
                icon: '📸',
                title: 'Snap / Upload',
                desc: 'Upload waste photos or videos with location.',
              },
              {
                icon: '🤖',
                title: 'AI Detects',
                desc: 'We classify items and verify disposal.',
              },
              {
                icon: '🗺️',
                title: 'Create/Claim Bounty',
                desc: 'Report hotspots or claim nearby cleanups.',
              },
              {
                icon: '💰',
                title: 'Earn & Redeem',
                desc: 'Get points for impact, redeem rewards.',
              },
            ].map((f, i) => (
              <div
                key={i}
                className="relative rounded-2xl bg-white/5 backdrop-blur border border-white/10 p-6 hover:bg-white/10 transition-colors animate-fadeUp"
                style={{ animationDelay: `${100 * (i + 1)}ms` }}
              >
                <div className="flex items-center justify-between mb-3">
                  <div className="text-3xl">{f.icon}</div>
                  <div className="w-8 h-8 rounded-full bg-eco-green/20 border border-eco-green/30 text-eco-green flex items-center justify-center font-bold">
                    {i + 1}
                  </div>
                </div>
                <div className="text-gray-100 font-semibold text-lg font-display">
                  {f.title}
                </div>
                <div className="text-gray-300/90 text-sm mt-1">{f.desc}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* About Us */}
      <section id="about" className="relative z-10 px-6 md:px-12 mt-16 md:mt-24">
        <div className="max-w-5xl mx-auto text-center">
          <h2 className="text-gray-100 text-3xl md:text-4xl font-extrabold font-display">
            About Us
          </h2>
          <p className="text-gray-300/90 mt-3 leading-relaxed">
            We are a small team on a big mission: make recycling rewarding and
            city cleanups collaborative. Waste Bounty connects AI-driven waste
            detection with community action so every snap, report, and cleanup
            counts toward a cleaner planet.
          </p>
          <div className="grid sm:grid-cols-3 gap-4 mt-8 text-left">
            {[
              {
                t: 'Our Mission',
                d: 'Turn responsible disposal into a habit powered by instant feedback and rewards.',
              },
              {
                t: 'Our Approach',
                d: 'Blend computer vision, location awareness, and gamified incentives to drive action.',
              },
              {
                t: 'Community',
                d: 'Clans, leaderboards, and city chats keep people connected and motivated.',
              },
            ].map((c, i) => (
              <div
                key={i}
                className="rounded-2xl bg-white/5 border border-white/10 p-5"
              >
                <div className="text-gray-100 font-semibold text-lg font-display">
                  {c.t}
                </div>
                <div className="text-gray-300/90 text-sm mt-1">{c.d}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Footer CTA */}
      <footer className="relative z-10 px-6 md:px-12 mt-16 mb-12">
        <div className="max-w-4xl mx-auto text-center">
          <h3 className="text-gray-100 text-2xl md:text-3xl font-extrabold font-display">
            Ready to earn while you recycle?
          </h3>
          <p className="text-gray-300/90 mt-2">
            Join the squad, start detecting, and grab rewards.
          </p>
          <button
            onClick={onGetStarted}
            className="mt-6 px-8 py-3 rounded-full bg-eco-green text-white font-bold hover:brightness-110 transition"
          >
            I’m In 🚀
          </button>
        </div>
      </footer>

      {/* Local animations */}
      <style>{`
        .animate-float-slow { animation: float 12s ease-in-out infinite; }
        .animate-pulse-slow { animation: pulse 3.5s ease-in-out infinite; }
        .animate-shimmer { background-size: 200% 100%; animation: shimmer 2.5s linear infinite; }
        .animate-fadeUp { opacity: 0; animation: fadeUp 0.6s ease-out forwards; }
        .animate-hue { animation: hue 10s linear infinite; }
        @keyframes float { 0%,100%{ transform: translateY(0) } 50%{ transform: translateY(-8px) } }
        @keyframes pulse { 0%, 100% { opacity: 0.85 } 50% { opacity: 1 } }
        @keyframes shimmer { 0% { background-position: 200% 0 } 100% { background-position: -200% 0 } }
        @keyframes fadeUp { 0% { opacity: 0; transform: translateY(14px) } 100% { opacity: 1; transform: translateY(0) } }
        @keyframes hue { 0% { filter: hue-rotate(0deg) } 100% { filter: hue-rotate(360deg) } }
      `}</style>
    </div>
  );
};

export default WelcomePage;

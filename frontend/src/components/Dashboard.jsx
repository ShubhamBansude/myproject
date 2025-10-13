// src/components/Dashboard.jsx

import React, { useState, useEffect, lazy, Suspense } from 'react';

// Lazy-load heavy tab panels to split Dashboard chunk
const EarnPoints = lazy(() => import('./EarnPoints'));
const WasteBounty = lazy(() => import('./WasteBounty'));

const RewardsShop = ({ onRedeem }) => {
  const [coupons, setCoupons] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const token = localStorage.getItem('authToken');

  useEffect(() => {
    const load = async () => {
      setLoading(true); setError('');
      try {
        const res = await fetch('http://localhost:5000/api/coupons', { headers: { Authorization: `Bearer ${token}` } });
        const data = await res.json();
        if (!res.ok) throw new Error(data?.error || 'Failed to load coupons');
        setCoupons(data.coupons || []);
      } catch (e) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    };
    if (token) load();
  }, [token]);

  const redeem = async (couponId) => {
    setError('');
    try {
      const res = await fetch('http://localhost:5000/api/redeem', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ coupon_id: couponId })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error || 'Redeem failed');
      onRedeem(data.total_points, true); // mark redeemed
      alert(`Redeemed! Code: ${data.coupon_code}`);
    } catch (e) {
      setError(e.message);
    }
  };

  return (
    <div>
      {loading && <div className="text-gray-300">Loading...</div>}
      {error && <div className="p-3 mb-3 text-sm text-red-300 bg-red-500/10 border border-red-500/20 rounded">{error}</div>}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {coupons.map(c => (
          <div key={c.id} className="rounded-xl bg-white/5 border border-white/10 p-4">
            <div className="text-lg font-semibold text-gray-100">{c.name}</div>
            <div className="text-sm text-gray-300 mb-2">{c.description}</div>
            <div className="flex items-center justify-between">
              <span className="px-3 py-1 rounded-full bg-eco-green/20 text-eco-green border border-eco-green/30 text-sm">{c.points_cost} pts</span>
              <button onClick={() => redeem(c.id)} className="px-3 py-2 rounded-lg bg-eco-green text-white text-sm hover:brightness-110">Redeem</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

const ProfileView = ({ user }) => {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <div className="rounded-xl bg-white/5 border border-white/10 p-4">
        <div className="text-gray-400 text-sm">Username</div>
        <div className="text-gray-100 text-xl font-semibold">{user.username}</div>
      </div>
      <div className="rounded-xl bg-white/5 border border-white/10 p-4">
        <div className="text-gray-400 text-sm">Total Points</div>
        <div className="text-gray-100 text-xl font-semibold">{user.total_points}</div>
      </div>
      <div className="rounded-xl bg-white/5 border border-white/10 p-4">
        <div className="text-gray-400 text-sm">Location</div>
        <div className="text-gray-100 text-lg font-semibold">
          {user.city}, {user.state}
        </div>
        <div className="text-gray-300 text-sm">{user.country}</div>
      </div>
      <div className="rounded-xl bg-white/5 border border-white/10 p-4">
        <div className="text-gray-400 text-sm">Bounty Status</div>
        <div className="text-gray-100 text-lg font-semibold">Active</div>
        <div className="text-gray-300 text-sm">Can report & claim bounties</div>
      </div>
      <div className="rounded-xl bg-white/5 border border-white/10 p-4 md:col-span-2">
        <div className="text-gray-400 text-sm mb-2">Eco Tips</div>
        <ul className="list-disc pl-6 text-gray-300 space-y-1 text-sm">
          <li>Rinse and recycle plastic bottles and cans.</li>
          <li>Separate hazardous waste like batteries and bulbs.</li>
          <li>Use reusable bags and containers to reduce plastic.</li>
          <li>Report public waste spots to earn bounty points.</li>
        </ul>
      </div>
    </div>
  );
};

const Dashboard = ({ currentUser, onLogout, setCurrentUser }) => {
  const [activeTab, setActiveTab] = useState('detection');
  const [stats, setStats] = useState({ detections: 0, redemptions: 0, lifetime_points: 0 });

  const fetchStats = async () => {
    const token = localStorage.getItem('authToken');
    try {
      const res = await fetch('http://localhost:5000/api/stats', { headers: { Authorization: `Bearer ${token}` } });
      const data = await res.json();
      if (res.ok) setStats({ detections: data.detections || 0, redemptions: data.redemptions || 0, lifetime_points: data.lifetime_points || 0 });
    } catch {}
  };

  useEffect(() => { fetchStats(); }, []);

  const updatePoints = (newPoints, redeemed = false) => {
    setCurrentUser(prev => ({ ...prev, total_points: newPoints }));
    if (redeemed || activeTab === 'detection') fetchStats();
  };

  const tabs = [
    { key: 'detection', label: 'Earn Points', icon: '📸' },
    { key: 'bounty', label: 'Waste Bounty', icon: '🗺️' },
    { key: 'rewards', label: 'Rewards', icon: '🎁' },
    { key: 'profile', label: 'Profile', icon: '👤' },
  ];

  let main;
  if (activeTab === 'detection') {
    main = <EarnPoints currentUser={currentUser} updatePoints={updatePoints} />;
  } else if (activeTab === 'bounty') {
    main = <WasteBounty currentUser={currentUser} updatePoints={updatePoints} />;
  } else if (activeTab === 'rewards') {
    main = <RewardsShop onRedeem={updatePoints} />;
  } else {
    main = <ProfileView user={currentUser} />;
  }

  const progressA = 75;
  const progressB = 50;
  const circlePct = 60;

  return (
    <div className="relative min-h-screen font-sans bg-black">
      {/* Background */}
      <div className="pointer-events-none absolute inset-0 -z-10">
        <div className="absolute inset-0 opacity-[0.06]" style={{ backgroundImage: 'radial-gradient(rgba(255,255,255,0.28) 1px, transparent 1px)', backgroundSize: '22px 22px' }} />
        <div className="absolute -top-24 -right-24 w-[60rem] h-[60rem] rotate-[-20deg] bg-gradient-to-br from-emerald-500/20 via-transparent to-amber-400/20 blur-3xl" />
        <div className="absolute -bottom-32 -left-24 w-[52rem] h-[52rem] rotate-[15deg] bg-gradient-to-tr from-amber-400/20 via-transparent to-emerald-500/20 blur-3xl" />
      </div>

      {/* Top Navbar */}
      <header className="sticky top-0 z-20 backdrop-blur bg-[#0b1220]/70 border-b border-white/10">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-white font-extrabold text-xl font-display">Waste</span>
            <span className="text-eco-green font-extrabold text-xl font-display">Rewards</span>
          </div>
          <div className="flex items-center gap-3 text-sm">
            <span className="px-3 py-1 rounded-full bg-white/5 border border-white/10 text-gray-200">{currentUser.username}</span>
            <span className="px-3 py-1 rounded-full bg-eco-green/20 text-eco-green border border-eco-green/30">{currentUser.total_points} pts</span>
            <button onClick={onLogout} className="px-3 py-1 rounded-lg border border-red-400/40 text-red-200 hover:bg-red-900/40 transition">Logout</button>
          </div>
        </div>
      </header>

      {/* Page body */}
      <div className="max-w-7xl mx-auto px-6 py-8">
        {/* Tabs */}
        <div className="flex flex-wrap items-center gap-2">
          {tabs.map(t => (
            <button
              key={t.key}
              onClick={() => setActiveTab(t.key)}
              className={`px-4 py-2 rounded-full border text-sm transition ${
                activeTab === t.key
                  ? 'bg-eco-green text-eco-dark border-eco-green'
                  : 'bg-white/5 text-gray-200 border-white/10 hover:bg-white/10'
              }`}
            >
              <span className="mr-1">{t.icon}</span> {t.label}
            </button>
          ))}
        </div>

        {/* Stats strip with overlays */}
        <div className="relative mt-6">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="rounded-xl border border-white/10 bg-white/5 p-4 relative overflow-hidden">
              <div className="absolute inset-0 bg-gradient-to-br from-emerald-500/20 to-transparent" />
              <div className="relative">
                <div className="text-xs text-gray-300">Total Points</div>
                <div className="text-2xl font-extrabold text-gray-100 mt-1">{currentUser.total_points}</div>
              </div>
            </div>
            <div className="rounded-xl border border-white/10 bg-white/5 p-4 relative overflow-hidden">
              <div className="absolute inset-0 bg-gradient-to-br from-amber-400/20 to-transparent" />
              <div className="relative">
                <div className="text-xs text-gray-300">Redemptions</div>
                <div className="text-2xl font-extrabold text-gray-100 mt-1">{stats.redemptions}</div>
              </div>
            </div>
            <div className="rounded-xl border border-white/10 bg-white/5 p-4 relative overflow-hidden">
              <div className="absolute inset-0 bg-gradient-to-br from-white/10 to-transparent" />
              <div className="relative">
                <div className="text-xs text-gray-300">Detections</div>
                <div className="text-2xl font-extrabold text-gray-100 mt-1">{stats.detections}</div>
              </div>
            </div>
          </div>

          {activeTab === 'rewards' && (
            <div className="pointer-events-none absolute top-1/2 right-4 -translate-y-1/2 flex items-start gap-6 z-10">
              {/* Two horizontal bars */}
              <div className="flex-1 space-y-3">
                <div className="h-6 rounded-full bg-white/5 border border-white/10 overflow-hidden">
                  <div className="h-full bg-gradient-to-r from-eco-green to-emerald-400" style={{ width: `${progressA}%` }} />
                </div>
                <div className="h-6 rounded-full bg-white/5 border border-white/10 overflow-hidden">
                  <div className="h-full bg-gradient-to-r from-amber-400 to-yellow-300" style={{ width: `${progressB}%` }} />
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Content card */}
        <section className="mt-6 rounded-2xl bg-white/5 backdrop-blur border border-white/10 p-6 shadow-2xl relative">
          <h2 className="text-2xl md:text-3xl font-extrabold text-gray-100 mb-6">
            {activeTab === 'detection' ? 'Upload Waste & Start Earning!' : activeTab.toUpperCase()}
          </h2>
          <div className="opacity-0 animate-fade-in-up" key={activeTab}>
            <Suspense fallback={<div className="text-gray-400">Loading section…</div>}>
              {main}
            </Suspense>
          </div>
          {activeTab === 'rewards' && (
            <div className="pointer-events-none absolute bottom-4 right-4 z-10">
              <div className="relative w-32 h-32">
                <div className="absolute inset-0 rounded-full bg-white/5 border border-white/10" />
                <div className="absolute inset-0 rounded-full" style={{ background: `conic-gradient(#f59e0b ${60}%, transparent 0)` }} />
                <div className="absolute inset-[12px] rounded-full bg-black flex items-center justify-center">
                  <div className="text-center">
                    <div className="text-[10px] text-gray-300 uppercase tracking-wide">Lifetime Points</div>
                    <div className="text-sm text-gray-200 font-semibold">{stats.lifetime_points} pts</div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </section>
      </div>

      <style>{`
        .animate-fade-in-up { opacity: 0; animation: fadeUp 0.55s ease-out forwards; }
        @keyframes fadeUp { 0% { opacity: 0; transform: translateY(14px) } 100% { opacity: 1; transform: translateY(0) } }
      `}</style>
    </div>
  );
};

export default Dashboard;
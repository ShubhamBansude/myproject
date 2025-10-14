// src/components/Leaderboard.jsx

import React, { useEffect, useState } from 'react';

const RankBadge = ({ rank }) => {
  const stylesByRank = {
    1: 'bg-yellow-400 text-black border-yellow-300',
    2: 'bg-gray-300 text-black border-gray-200',
    3: 'bg-amber-600 text-white border-amber-500',
  };
  const style = stylesByRank[rank] || 'bg-white/10 text-gray-200 border-white/20';
  return (
    <span className={`inline-flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold border ${style}`}>
      {rank}
    </span>
  );
};

const Avatar = ({ label }) => {
  const letter = (label || '?').toString().charAt(0).toUpperCase();
  return (
    <div className="w-8 h-8 rounded-lg bg-eco-green/15 border border-eco-green/30 text-eco-green flex items-center justify-center font-bold">
      {letter}
    </div>
  );
};

const LeaderList = ({ title, items, type }) => {
  return (
    <div className="rounded-xl bg-white/5 border border-white/10 p-4">
      <div className="flex items-center justify-between mb-2">
        <div className="text-gray-200 font-semibold">{title}</div>
      </div>
      <ol className="divide-y divide-white/10">
        {items.length === 0 && (
          <li className="py-3 text-xs text-gray-400">No data available.</li>
        )}
        {items.map((item, idx) => (
          <li key={(item.username || item.id || idx) + String(idx)} className="py-3 flex items-center gap-3">
            <RankBadge rank={idx + 1} />
            <Avatar label={type === 'users' ? item.username : item.name} />
            <div className="flex-1 min-w-0">
              <div className="text-sm text-gray-100 truncate">
                {type === 'users' ? `@${item.username}` : item.name}
              </div>
              <div className="text-[11px] text-gray-400 truncate">
                {type === 'users' ? (item.city ? item.city : '—') : (item.city ? item.city : '—')}
              </div>
            </div>
            <div className="text-eco-green text-sm font-semibold">
              {(type === 'users' ? item.total_points : item.points) ?? 0} pts
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
};

const Leaderboard = () => {
  const [topUsers, setTopUsers] = useState([]);
  const [topClans, setTopClans] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const load = async () => {
    setLoading(true); setError('');
    try {
      const [uRes, cRes] = await Promise.all([
        fetch('http://localhost:5000/api/leaderboard/users?limit=10'),
        fetch('http://localhost:5000/api/leaderboard/clans?limit=10'),
      ]);
      const [uData, cData] = await Promise.all([uRes.json(), cRes.json()]);
      if (uRes.ok) setTopUsers(Array.isArray(uData.users) ? uData.users : []); else setError(uData?.error || 'Failed to load users leaderboard');
      if (cRes.ok) setTopClans(Array.isArray(cData.clans) ? cData.clans : []); else setError((prev) => prev || cData?.error || 'Failed to load clans leaderboard');
    } catch (e) {
      setError('Network error while loading leaderboard');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-extrabold text-gray-100">Leaderboard</h2>
        <button onClick={load} disabled={loading} className="px-3 py-2 rounded-lg text-sm bg-white/10 text-gray-200 border border-white/10 hover:bg-white/20 disabled:opacity-60">
          {loading ? 'Loading…' : 'Refresh'}
        </button>
      </div>
      {error && (
        <div className="p-3 text-sm text-red-300 bg-red-500/10 border border-red-500/20 rounded">{error}</div>
      )}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <LeaderList title="Top Users" items={topUsers} type="users" />
        <LeaderList title="Top Clans" items={topClans} type="clans" />
      </div>
      <div className="rounded-xl bg-gradient-to-r from-eco-green/10 via-white/5 to-amber-400/10 border border-white/10 p-4">
        <div className="text-xs text-gray-300">
          Rankings update periodically. Earn points by scanning waste, claiming bounties, and redeeming responsibly.
        </div>
      </div>
    </div>
  );
};

export default Leaderboard;

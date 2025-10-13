// src/components/LeaderboardAside.jsx
import React, { useEffect, useState } from 'react';

const LeaderboardAside = () => {
  const token = localStorage.getItem('authToken');
  const [users, setUsers] = useState([]);
  const [clans, setClans] = useState([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const loadAll = async () => {
    if (!token) return;
    setLoading(true); setError('');
    try {
      const [ru, rc] = await Promise.all([
        fetch('http://localhost:5000/api/leaderboard/users?limit=5', { headers: { Authorization: `Bearer ${token}` } }),
        fetch('http://localhost:5000/api/leaderboard/clans?limit=5', { headers: { Authorization: `Bearer ${token}` } }),
      ]);
      const udata = await ru.json();
      const cdata = await rc.json();
      if (!ru.ok) throw new Error(udata?.error || 'Failed to load users');
      if (!rc.ok) throw new Error(cdata?.error || 'Failed to load clans');
      setUsers(udata.users || []);
      setClans(cdata.clans || []);
    } catch (e) {
      setError(e.message);
    } finally { setLoading(false); }
  };

  useEffect(() => { loadAll(); }, []);

  return (
    <div className="space-y-4">
      <div className="rounded-xl bg-white/5 border border-white/10 p-4">
        <div className="flex items-center justify-between mb-2">
          <div className="text-gray-200 font-semibold">Top Users</div>
          <button onClick={loadAll} className="text-xs text-gray-300 hover:text-white">Refresh</button>
        </div>
        {loading && <div className="text-gray-400 text-sm">Loading…</div>}
        {error && <div className="p-2 text-xs text-red-300 bg-red-500/10 border border-red-500/20 rounded">{error}</div>}
        <ol className="space-y-2 list-decimal list-inside text-sm">
          {users.map((u) => (
            <li key={u.username} className="flex justify-between">
              <span className="text-gray-200">@{u.username}</span>
              <span className="text-gray-400">{u.total_points} pts</span>
            </li>
          ))}
          {users.length === 0 && !loading && <div className="text-gray-400 text-sm">No users yet.</div>}
        </ol>
      </div>

      <div className="rounded-xl bg-white/5 border border-white/10 p-4">
        <div className="flex items-center justify-between mb-2">
          <div className="text-gray-200 font-semibold">Top Clans</div>
          <button onClick={loadAll} className="text-xs text-gray-300 hover:text-white">Refresh</button>
        </div>
        <ol className="space-y-2 list-decimal list-inside text-sm">
          {clans.map((c) => (
            <li key={c.id} className="flex justify-between">
              <span className="text-gray-200">{c.name}</span>
              <span className="text-gray-400">{c.clan_points} pts</span>
            </li>
          ))}
          {clans.length === 0 && !loading && <div className="text-gray-400 text-sm">No clans yet.</div>}
        </ol>
      </div>
    </div>
  );
};

export default LeaderboardAside;

// src/components/Clans.jsx

import React, { useEffect, useMemo, useState } from 'react';

const apiBase = 'http://localhost:5000';

const SectionCard = ({ title, children, right }) => (
  <div className="bg-white/5 border border-white/10 rounded-xl p-4">
    <div className="flex items-center justify-between mb-3">
      <h3 className="text-lg font-semibold text-gray-100">{title}</h3>
      {right}
    </div>
    {children}
  </div>
);

const Clans = ({ currentUser }) => {
  const token = useMemo(() => localStorage.getItem('authToken'), []);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // My clan
  const [myClan, setMyClan] = useState(null); // { id, name, role, code?, members: [{username,total_points,role}], clan_points }
  // Nearby clans in same city
  const [clans, setClans] = useState([]);

  // Create / join inputs
  const [newClanName, setNewClanName] = useState('');
  const [joinCode, setJoinCode] = useState('');

  // Chat
  const [chatMessages, setChatMessages] = useState([]);
  const [chatInput, setChatInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);

  const fetchMyClan = async () => {
    setError('');
    try {
      const res = await fetch(`${apiBase}/api/clans/me`, { headers: { Authorization: `Bearer ${token}` } });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error || 'Failed to load my clan');
      setMyClan(data.clan);
    } catch (e) {
      setError(e.message);
    }
  };

  const fetchClans = async () => {
    setError('');
    try {
      const res = await fetch(`${apiBase}/api/clans`, { headers: { Authorization: `Bearer ${token}` } });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error || 'Failed to load clans');
      setClans(Array.isArray(data.clans) ? data.clans : []);
    } catch (e) {
      setError(e.message);
    }
  };

  const refreshAll = async () => {
    setLoading(true);
    await Promise.all([fetchMyClan(), fetchClans()]);
    setLoading(false);
  };

  useEffect(() => { if (token) { void refreshAll(); } }, [token]);

  const createClan = async () => {
    if (!newClanName.trim()) { setError('Enter clan name'); return; }
    setError('');
    try {
      const res = await fetch(`${apiBase}/api/clans/create`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ name: newClanName.trim() })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error || 'Failed to create clan');
      setNewClanName('');
      await refreshAll();
      if (data.code) alert(`Clan created. Invite code: ${data.code}`);
    } catch (e) {
      setError(e.message);
    }
  };

  const joinClan = async () => {
    const code = joinCode.trim();
    if (!/^\d{4}$/.test(code)) { setError('Enter 4-digit code'); return; }
    setError('');
    try {
      const res = await fetch(`${apiBase}/api/clans/join`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ code })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error || 'Failed to join clan');
      setJoinCode('');
      await refreshAll();
    } catch (e) {
      setError(e.message);
    }
  };

  const leaveClan = async () => {
    if (!confirm('Leave clan?')) return;
    try {
      const res = await fetch(`${apiBase}/api/clans/leave`, { method: 'POST', headers: { Authorization: `Bearer ${token}` } });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error || 'Failed to leave clan');
      await refreshAll();
    } catch (e) { setError(e.message); }
  };

  const kickMember = async (username) => {
    if (!confirm(`Kick @${username}?`)) return;
    try {
      const res = await fetch(`${apiBase}/api/clans/kick`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ username })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error || 'Failed to kick');
      await refreshAll();
    } catch (e) { setError(e.message); }
  };

  const loadChat = async () => {
    if (!myClan) return;
    setChatLoading(true);
    try {
      const res = await fetch(`${apiBase}/api/clans/messages?clan_id=${encodeURIComponent(myClan.id)}`, { headers: { Authorization: `Bearer ${token}` } });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error || 'Failed to load chat');
      setChatMessages(data.messages || []);
    } catch (e) { setError(e.message); }
    finally { setChatLoading(false); }
  };

  const sendChat = async () => {
    const text = chatInput.trim();
    if (!text || !myClan) return;
    setChatLoading(true);
    try {
      const res = await fetch(`${apiBase}/api/clans/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ clan_id: myClan.id, message: text })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error || 'Failed to send');
      setChatMessages((prev) => [ ...(prev || []), data.message ]);
      setChatInput('');
    } catch (e) { setError(e.message); }
    finally { setChatLoading(false); }
  };

  useEffect(() => { if (myClan?.id) loadChat(); }, [myClan?.id]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-gray-100">🛡️ City Clans</h2>
        <div className="text-sm text-gray-400">Create or join clans in {currentUser?.city}</div>
      </div>

      {error && (
        <div className="p-3 text-sm text-red-300 bg-red-500/10 border border-red-500/20 rounded">{error}</div>
      )}

      <div className="grid md:grid-cols-3 gap-4">
        <SectionCard title="My Clan" right={
          myClan ? (
            <div className="flex items-center gap-2">
              {myClan.role === 'leader' && myClan.code && (
                <span className="px-2 py-1 text-xs rounded bg-white/10 border border-white/20 text-gray-300">Code: {myClan.code}</span>
              )}
              <button onClick={leaveClan} className="text-xs px-2 py-1 rounded bg-red-500/20 text-red-200 border border-red-500/30">Leave</button>
            </div>
          ) : (
            <button onClick={refreshAll} className="text-xs px-2 py-1 rounded bg-white/10 text-gray-300 border border-white/20">Refresh</button>
          )
        }>
          {!myClan ? (
            <div className="text-gray-300 text-sm">You are not in a clan.</div>
          ) : (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div className="text-gray-100 font-semibold">{myClan.name}</div>
                <div className="text-xs text-gray-300">{myClan.member_count} members</div>
              </div>
              <div className="text-sm text-gray-400">Clan points: <span className="text-gray-200 font-semibold">{myClan.clan_points}</span></div>
              <div className="divide-y divide-white/10">
                {(myClan.members || []).map((m) => (
                  <div key={m.username} className="flex items-center justify-between py-2">
                    <div className="text-gray-200 text-sm">
                      <span className="font-medium">@{m.username}</span>
                      {m.role === 'leader' && <span className="ml-2 text-amber-300 text-xs">(Leader)</span>}
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-gray-400">{m.total_points} pts</span>
                      {myClan.role === 'leader' && m.role !== 'leader' && (
                        <button onClick={() => kickMember(m.username)} className="text-xs px-2 py-1 rounded bg-red-500/20 text-red-200 border border-red-500/30">Kick</button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </SectionCard>

        <SectionCard title="Create Clan">
          {!myClan ? (
            <div className="space-y-3">
              <input
                type="text"
                value={newClanName}
                onChange={(e) => setNewClanName(e.target.value)}
                placeholder="Clan name"
                className="w-full px-3 py-2 rounded-lg bg-white/10 border border-white/20 text-white placeholder-gray-400 text-sm"
              />
              <button onClick={createClan} disabled={!newClanName.trim() || loading}
                className={`w-full py-2 rounded-lg text-sm font-semibold ${!newClanName.trim() || loading ? 'bg-gray-500/40 text-gray-300' : 'bg-eco-green text-eco-dark hover:brightness-110'}`}>
                {loading ? 'Creating…' : 'Create Clan'}
              </button>
            </div>
          ) : (
            <div className="text-gray-400 text-sm">Leave current clan to create a new one.</div>
          )}
        </SectionCard>

        <SectionCard title="Join Clan">
          {!myClan ? (
            <div className="space-y-3">
              <input
                type="text"
                value={joinCode}
                onChange={(e) => setJoinCode(e.target.value.replace(/[^0-9]/g, '').slice(0, 4))}
                placeholder="4-digit code"
                className="w-full px-3 py-2 rounded-lg bg-white/10 border border-white/20 text-white placeholder-gray-400 text-sm tracking-widest"
              />
              <button onClick={joinClan} disabled={!/^\d{4}$/.test(joinCode)}
                className={`w-full py-2 rounded-lg text-sm font-semibold ${!/^\d{4}$/.test(joinCode) ? 'bg-gray-500/40 text-gray-300' : 'bg-eco-accent text-eco-dark hover:brightness-110'}`}>
                Join with Code
              </button>
            </div>
          ) : (
            <div className="text-gray-400 text-sm">Already in a clan.</div>
          )}
        </SectionCard>
      </div>

      <SectionCard title="Clans in Your City" right={<button onClick={fetchClans} className="text-xs px-2 py-1 rounded bg-white/10 text-gray-300 border border-white/20">Refresh</button>}>
        {clans.length === 0 ? (
          <div className="text-gray-400 text-sm">No clans yet. Be the first to create one!</div>
        ) : (
          <div className="grid md:grid-cols-2 gap-3">
            {clans.map((c) => (
              <div key={c.id} className="p-3 rounded-lg bg-white/5 border border-white/10">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-gray-100 font-semibold">{c.name}</div>
                    <div className="text-xs text-gray-400">{c.city}, {c.state}</div>
                  </div>
                  <div className="text-xs text-gray-300">{c.member_count} members</div>
                </div>
                <div className="mt-2 text-sm text-gray-300">Clan points: <span className="text-gray-200 font-semibold">{c.clan_points}</span></div>
              </div>
            ))}
          </div>
        )}
      </SectionCard>

      {myClan && (
        <SectionCard title="Clan Chat" right={<button onClick={loadChat} className="text-xs px-2 py-1 rounded bg-white/10 text-gray-300 border border-white/20">Refresh</button>}>
          <div className="max-h-64 overflow-y-auto space-y-2 pr-1">
            {(chatMessages || []).map((m) => (
              <div key={m.id} className="text-sm text-gray-200">
                <span className="text-gray-400 text-xs">@{m.sender_username}</span>
                <div className="whitespace-pre-wrap">{m.message}</div>
              </div>
            ))}
            {(chatMessages || []).length === 0 && !chatLoading && (
              <div className="text-xs text-gray-400">No messages yet. Say hi!</div>
            )}
          </div>
          <div className="mt-3 flex items-center gap-2">
            <input
              type="text"
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              placeholder="Type a message…"
              className="flex-1 px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-400 text-sm"
            />
            <button onClick={sendChat} disabled={chatLoading || !chatInput.trim()} className={`px-3 py-2 rounded-lg text-sm font-semibold ${chatLoading || !chatInput.trim() ? 'bg-gray-500/40 text-gray-300' : 'bg-eco-green text-eco-dark hover:brightness-110'}`}>Send</button>
          </div>
        </SectionCard>
      )}
    </div>
  );
};

export default Clans;

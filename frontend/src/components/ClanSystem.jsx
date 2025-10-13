// src/components/ClanSystem.jsx
import React, { useEffect, useState } from 'react';

const ClanSystem = () => {
  const token = localStorage.getItem('authToken');
  const viewerUsername = token && token.startsWith('token_') ? token.replace('token_', '') : '';
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [meClan, setMeClan] = useState(null);
  const [clans, setClans] = useState([]);
  const [createName, setCreateName] = useState('');
  const [createDesc, setCreateDesc] = useState('');
  const [joinCode, setJoinCode] = useState('');
  const [chatInput, setChatInput] = useState('');
  const [chat, setChat] = useState([]);
  const [chatLoading, setChatLoading] = useState(false);

  const loadMeClan = async () => {
    if (!token) return;
    setLoading(true); setError('');
    try {
      const res = await fetch('http://localhost:5000/api/clans/me', { headers: { Authorization: `Bearer ${token}` } });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error || 'Failed to load clan');
      setMeClan(data.clan || null);
      if (data.clan) await loadChat();
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const loadClans = async () => {
    if (!token) return;
    try {
      const res = await fetch('http://localhost:5000/api/clans/list', { headers: { Authorization: `Bearer ${token}` } });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error || 'Failed to load clans');
      setClans(data.clans || []);
    } catch (e) {
      setError(e.message);
    }
  };

  const createClan = async () => {
    if (!createName.trim()) { setError('Clan name is required'); return; }
    setLoading(true); setError('');
    try {
      const res = await fetch('http://localhost:5000/api/clans/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ name: createName.trim(), description: createDesc.trim() })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error || 'Failed to create clan');
      setCreateName(''); setCreateDesc('');
      await loadMeClan();
      await loadClans();
    } catch (e) {
      setError(e.message);
    } finally { setLoading(false); }
  };

  const joinClan = async () => {
    const code = joinCode.trim();
    if (!/^\d{4}$/.test(code)) { setError('Enter 4-digit code'); return; }
    setLoading(true); setError('');
    try {
      const res = await fetch('http://localhost:5000/api/clans/join', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ code })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error || 'Failed to join clan');
      setJoinCode('');
      await loadMeClan();
      await loadClans();
    } catch (e) { setError(e.message); } finally { setLoading(false); }
  };

  const leaveClan = async () => {
    setLoading(true); setError('');
    try {
      const res = await fetch('http://localhost:5000/api/clans/leave', { method: 'POST', headers: { Authorization: `Bearer ${token}` } });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error || 'Failed to leave clan');
      setMeClan(null);
      setChat([]);
      await loadClans();
    } catch (e) { setError(e.message); } finally { setLoading(false); }
  };

  const kickMember = async (username) => {
    setLoading(true); setError('');
    try {
      const res = await fetch('http://localhost:5000/api/clans/kick', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ username })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error || 'Failed to kick');
      await loadMeClan();
    } catch (e) { setError(e.message); } finally { setLoading(false); }
  };

  const loadChat = async () => {
    setChatLoading(true);
    try {
      const res = await fetch('http://localhost:5000/api/clans/chat', { headers: { Authorization: `Bearer ${token}` } });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error || 'Failed to load chat');
      setChat(data.messages || []);
    } catch (e) { setError(e.message); } finally { setChatLoading(false); }
  };

  const sendChat = async () => {
    const text = chatInput.trim();
    if (!text) return;
    setChatLoading(true);
    try {
      const res = await fetch('http://localhost:5000/api/clans/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ message: text })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error || 'Failed to send');
      setChat((prev) => [ ...(prev || []), data.message ]);
      setChatInput('');
    } catch (e) { setError(e.message); } finally { setChatLoading(false); }
  };

  const deleteChat = async (id) => {
    setChatLoading(true);
    try {
      const res = await fetch(`http://localhost:5000/api/clans/chat/${id}`, { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error || 'Failed to delete');
      setChat((prev) => (prev || []).filter((m) => m.id !== id));
    } catch (e) { setError(e.message); } finally { setChatLoading(false); }
  };

  useEffect(() => { loadMeClan(); loadClans(); }, []);

  const isLeader = !!(meClan && meClan.leader_username && meClan.leader_username === viewerUsername);

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <div className="rounded-xl bg-white/5 border border-white/10 p-4">
        <div className="text-gray-200 font-semibold mb-2">Clans in Your City</div>
        <div className="space-y-2 max-h-72 overflow-auto pr-1">
          {clans.map((c) => (
            <div key={c.id} className="p-3 rounded-lg bg-white/5 border border-white/10">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-gray-100 font-semibold">{c.name}</div>
                  <div className="text-gray-400 text-xs">Members: {c.member_count} · Points: {c.clan_points}</div>
                </div>
                <div className="text-gray-400 text-xs">Code: {c.join_code}</div>
              </div>
            </div>
          ))}
          {clans.length === 0 && <div className="text-gray-400 text-sm">No clans yet.</div>}
        </div>
      </div>

      <div className="rounded-xl bg-white/5 border border-white/10 p-4">
        <div className="text-gray-200 font-semibold mb-2">Create or Join</div>
        <div className="space-y-3">
          <div className="flex gap-2">
            <input value={createName} onChange={(e)=>setCreateName(e.target.value)} placeholder="Clan name" className="flex-1 px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-400 text-sm" />
            <button onClick={createClan} disabled={loading} className="px-3 py-2 rounded-lg bg-eco-green text-eco-dark text-sm font-semibold">Create</button>
          </div>
          <input value={createDesc} onChange={(e)=>setCreateDesc(e.target.value)} placeholder="Description (optional)" className="w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-400 text-sm" />
          <div className="flex gap-2 items-center">
            <input value={joinCode} onChange={(e)=>setJoinCode(e.target.value)} placeholder="4-digit code" maxLength={4} className="flex-1 px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-400 text-sm" />
            <button onClick={joinClan} disabled={loading} className="px-3 py-2 rounded-lg bg-eco-accent text-eco-dark text-sm font-semibold">Join</button>
          </div>
        </div>
      </div>

      <div className="md:col-span-2 rounded-xl bg-white/5 border border-white/10 p-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-gray-200 font-semibold">My Clan</div>
            {!meClan && <div className="text-gray-400 text-sm">You are not in a clan yet.</div>}
            {meClan && (
              <div className="text-gray-300 text-sm">
                <span className="text-gray-100 font-semibold">{meClan.name}</span> · Code: <span className="text-gray-200">{meClan.join_code}</span>
              </div>
            )}
          </div>
          {meClan && <button onClick={leaveClan} disabled={loading} className="px-3 py-2 rounded-lg bg-red-500/20 text-red-200 border border-red-400/20 text-sm">Leave</button>}
        </div>

        {meClan && (
          <div className="mt-3 grid md:grid-cols-2 gap-3">
            <div className="rounded-lg bg-white/5 border border-white/10 p-3">
              <div className="text-gray-300 text-sm mb-2">Members</div>
              <div className="space-y-2 max-h-56 overflow-auto pr-1">
                {meClan.members?.map((m) => {
                  const canKick = isLeader && m.role !== 'leader' && m.username !== viewerUsername;
                  return (
                    <div key={m.username} className="flex items-center justify-between text-sm">
                      <div className="text-gray-200">
                        @{m.username} <span className="text-gray-400">· {m.total_points} pts</span> {m.role === 'leader' && <span className="ml-1 text-eco-green">(Leader)</span>}
                      </div>
                      {canKick && (
                        <button onClick={() => kickMember(m.username)} className="text-xs text-red-300 hover:text-red-200">Kick</button>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
            <div className="rounded-lg bg-white/5 border border-white/10 p-3">
              <div className="flex items-center justify-between mb-2">
                <div className="text-gray-300 text-sm">Clan Chat</div>
                {chatLoading ? (
                  <div className="text-xs text-gray-400">Loading…</div>
                ) : (
                  <button onClick={loadChat} className="text-xs text-gray-300 hover:text-white">Refresh</button>
                )}
              </div>
              <div className="max-h-56 overflow-auto space-y-2 pr-1">
                {(chat || []).map((m) => (
                  <div key={m.id} className="flex items-start gap-2">
                    <div className="flex-1">
                      <div className="text-[11px] text-gray-400">
                        <span className="text-gray-200 font-semibold">@{m.sender_username}</span>
                        <span className="ml-2 opacity-70">{new Date((m.created_at || '').replace(' ', 'T') + 'Z').toLocaleString()}</span>
                      </div>
                      <div className="text-sm text-gray-100 whitespace-pre-wrap">{m.message}</div>
                    </div>
                    <button onClick={() => deleteChat(m.id)} className="text-xs text-red-300 hover:text-red-200">✖</button>
                  </div>
                ))}
                {(chat || []).length === 0 && !chatLoading && <div className="text-xs text-gray-400">No messages yet.</div>}
              </div>
              <div className="mt-2 flex items-center gap-2">
                <input value={chatInput} onChange={(e)=>setChatInput(e.target.value)} placeholder="Type a message…" className="flex-1 px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-400 text-sm" />
                <button onClick={sendChat} disabled={chatLoading || !chatInput.trim()} className={`px-3 py-2 rounded-lg text-sm font-semibold ${chatLoading || !chatInput.trim() ? 'bg-gray-500/40 text-gray-300 cursor-not-allowed' : 'bg-eco-green text-eco-dark hover:brightness-110'}`}>Send</button>
              </div>
            </div>
          </div>
        )}
      </div>

      {error && <div className="md:col-span-2 p-3 text-sm text-red-300 bg-red-500/10 border border-red-500/20 rounded">{error}</div>}
    </div>
  );
};

export default ClanSystem;

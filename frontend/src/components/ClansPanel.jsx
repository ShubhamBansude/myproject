// src/components/ClansPanel.jsx
import React, { useEffect, useMemo, useState } from 'react';
import { apiUrl } from '../lib/api';

const ClansPanel = ({ currentUser }) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [myClan, setMyClan] = useState(null);
  const [cityClans, setCityClans] = useState([]);
  const [newClanName, setNewClanName] = useState('');
  const [joinCode, setJoinCode] = useState('');
  const [pendingRequests, setPendingRequests] = useState([]);

  const token = useMemo(() => localStorage.getItem('authToken'), []);

  const load = async () => {
    setError(''); setSuccess(''); setLoading(true);
    try {
      const [mineRes, listRes] = await Promise.all([
        fetch(apiUrl('/api/my_clan'), { headers: { Authorization: `Bearer ${token}` } }),
        fetch(apiUrl('/api/clans'), { headers: { Authorization: `Bearer ${token}` } }),
      ]);
      const mine = await mineRes.json();
      const list = await listRes.json();
      if (mineRes.ok) setMyClan(mine.clan || null); else setError(mine?.error || 'Failed to load my clan');
      if (listRes.ok) setCityClans(Array.isArray(list.clans) ? list.clans : []); else setError(list?.error || 'Failed to load clans');
      // If leader, load requests
      if (mine?.clan?.leader_username && mine.clan.leader_username === currentUser?.username) {
        try {
          const r = await fetch(apiUrl('/api/clan_join_requests'), { headers: { Authorization: `Bearer ${token}` } });
          const d = await r.json();
          if (r.ok) setPendingRequests(Array.isArray(d.requests) ? d.requests : []);
        } catch {}
      } else {
        setPendingRequests([]);
      }
    } catch (e) {
      setError('Network error.');
    } finally { setLoading(false); }
  };

  useEffect(() => { if (token) load(); }, [token]);

  const createClan = async (e) => {
    e.preventDefault(); setError(''); setSuccess('');
    if (!newClanName.trim()) { setError('Enter a clan name.'); return; }
    try {
      const res = await fetch(apiUrl('/api/clans'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ name: newClanName.trim() }),
      });
      const data = await res.json();
      if (!res.ok) { setError(data?.error || 'Failed to create clan'); return; }
      setSuccess('Clan created. Share the code to invite.');
      setNewClanName('');
      await load();
    } catch { setError('Network error.'); }
  };

  const joinClan = async (e) => {
    e.preventDefault(); setError(''); setSuccess('');
    const code = (joinCode || '').trim();
    try {
      const res = await fetch(apiUrl('/api/clans/join'), {
        method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ code })
      });
      const data = await res.json();
      if (!res.ok) { setError(data?.error || 'Failed to request join'); return; }
      if (data.status === 'requested') setSuccess('Join request sent to clan leader.');
      else setSuccess('Joined clan successfully.');
      setJoinCode('');
      await load();
    } catch { setError('Network error.'); }
  };

  const leaveClan = async () => {
    if (!window.confirm('Leave clan?')) return;
    try {
      const res = await fetch(apiUrl('/api/my_clan/leave'), { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } });
      const data = await res.json();
      if (!res.ok) { setError(data?.error || 'Failed to leave clan'); return; }
      setSuccess('Left clan.');
      await load();
    } catch { setError('Network error.'); }
  };

  const kickUser = async (username) => {
    if (!window.confirm(`Kick @${username}?`)) return;
    try {
      const res = await fetch(apiUrl('/api/clans/kick'), { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }, body: JSON.stringify({ username }) });
      const data = await res.json();
      if (!res.ok) { setError(data?.error || 'Failed to kick'); return; }
      setSuccess(`Kicked @${username}.`);
      await load();
    } catch { setError('Network error.'); }
  };

  // Chat state
  const [chatMessages, setChatMessages] = useState([]);
  const [chatText, setChatText] = useState('');
  const [chatLoading, setChatLoading] = useState(false);

  const loadChat = async () => {
    if (!myClan) return; setChatLoading(true); setError('');
    try {
      const res = await fetch(apiUrl(`/api/clan_chat?clan_id=${encodeURIComponent(myClan.id)}`), { headers: { Authorization: `Bearer ${token}` } });
      const data = await res.json();
      if (!res.ok) { setError(data?.error || 'Failed to load chat'); return; }
      setChatMessages(Array.isArray(data.messages) ? data.messages : []);
    } catch { setError('Network error.'); } finally { setChatLoading(false); }
  };

  useEffect(() => { if (myClan) loadChat(); }, [myClan?.id]);

  const sendChat = async () => {
    const text = (chatText || '').trim(); if (!text || !myClan) return;
    setChatLoading(true);
    try {
      const res = await fetch(apiUrl('/api/clan_chat'), { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }, body: JSON.stringify({ clan_id: myClan.id, message: text }) });
      const data = await res.json();
      if (!res.ok) { setError(data?.error || 'Failed to send'); return; }
      setChatMessages((prev) => [...prev, data.message]);
      setChatText('');
    } catch { setError('Network error.'); } finally { setChatLoading(false); }
  };

  const deleteMessage = async (id) => {
    if (!myClan) return;
    try {
      const res = await fetch(apiUrl(`/api/clan_chat/${id}`), { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } });
      const data = await res.json();
      if (!res.ok) { setError(data?.error || 'Failed to delete'); return; }
      setChatMessages((prev) => prev.filter(m => m.id !== id));
    } catch { setError('Network error.'); }
  };

  const isLeader = !!myClan && myClan.leader_username === currentUser?.username;

  return (
    <div className="grid gap-4 md:grid-cols-[1.1fr_1.2fr]">
      {/* Left: Create / Join */}
      <div className="rounded-xl bg-white/5 border border-white/10 p-4">
        <div className="text-gray-100 text-lg font-semibold mb-2">Clans in {currentUser?.city}</div>
        {error && <div className="p-2 text-sm text-red-300 bg-red-500/10 border border-red-500/20 rounded mb-2">{error}</div>}
        {success && <div className="p-2 text-sm text-green-300 bg-emerald-500/10 border border-emerald-500/20 rounded mb-2">{success}</div>}
        {!myClan && (
          <div className="space-y-4">
            <form onSubmit={createClan} className="space-y-2">
              <div className="text-gray-300 text-sm">Create a clan</div>
              <div className="flex items-center gap-2">
                <input type="text" value={newClanName} onChange={(e)=>setNewClanName(e.target.value)} placeholder="Clan name" className="flex-1 px-3 py-2 rounded bg-black/40 border border-white/10 text-gray-100" />
                <button type="submit" className="px-3 py-2 rounded bg-eco-green text-eco-dark font-semibold">Create</button>
              </div>
            </form>
            <form onSubmit={joinClan} className="space-y-2">
              <div className="text-gray-300 text-sm">Join with 4-digit code</div>
              <div className="flex items-center gap-2">
                <input type="text" value={joinCode} onChange={(e)=>setJoinCode(e.target.value.replace(/[^0-9]/g,''))} placeholder="1234" maxLength={4} className="w-24 px-3 py-2 rounded bg-black/40 border border-white/10 text-gray-100 tracking-widest text-center" />
                <button type="submit" className="px-3 py-2 rounded bg-eco-accent text-eco-dark font-semibold">Join</button>
              </div>
            </form>
            <div>
              <div className="text-gray-300 text-sm mb-2">Clans in your city</div>
              <div className="space-y-2 max-h-64 overflow-auto pr-1">
                {cityClans.length === 0 ? (
                  <div className="text-gray-400 text-sm">No clans yet. Create the first!</div>
                ) : cityClans.map(c => (
                  <div key={c.id} className="p-2 rounded bg-white/5 border border-white/10">
                    <div className="flex items-center justify-between">
                      <div>
                        <div className="text-gray-100 font-medium">{c.name}</div>
                        <div className="text-gray-400 text-xs">Leader @{c.leader_username || c.leader_user_id}</div>
                      </div>
                      <button
                        onClick={async ()=>{
                          try {
                            const res = await fetch(apiUrl('/api/clans/join'), { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }, body: JSON.stringify({ clan_id: c.id }) });
                            const data = await res.json();
                            if (!res.ok) { setError(data?.error || 'Failed to request join'); return; }
                            setSuccess('Join request sent to leader.');
                          } catch { setError('Network error.'); }
                        }}
                        className="px-2 py-1 rounded bg-eco-accent text-eco-dark text-xs font-semibold"
                      >Request to Join</button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {myClan && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-gray-200 font-semibold">{myClan.name}</div>
                <div className="text-gray-400 text-xs">{myClan.city}{myClan.state ? `, ${myClan.state}` : ''}</div>
              </div>
              <div className="flex items-center gap-2">
                {isLeader && myClan.join_code && (
                  <span className="px-2 py-1 rounded bg-white/10 border border-white/10 text-xs text-gray-200">Code: {myClan.join_code}</span>
                )}
                <button onClick={leaveClan} className="px-3 py-1 rounded bg-red-500/20 text-red-200 border border-red-500/30 text-xs">Leave</button>
              </div>
            </div>
            <div>
              <div className="text-gray-300 text-sm mb-1">Members</div>
              <div className="space-y-2 max-h-44 overflow-auto pr-1">
                {(myClan.members||[]).map(m => (
                  <div key={m.id} className="p-2 rounded bg-white/5 border border-white/10 flex items-center justify-between">
                    <div>
                      <button
                        onClick={()=>{
                          // Emit event to open profile modal globally via CustomEvent
                          window.dispatchEvent(new CustomEvent('openUserPeek',{ detail: { username: m.username } }));
                        }}
                        className="text-left text-gray-100 font-medium hover:underline"
                        title="View profile"
                      >@{m.username}</button>
                      <span className="ml-2 text-gray-400 text-xs">{m.role}</span>
                      <span className="ml-2 text-eco-green text-xs">{m.total_points} pts</span>
                    </div>
                    {isLeader && m.role !== 'leader' && (
                      <button onClick={() => kickUser(m.username)} className="px-2 py-1 rounded bg-red-500/20 text-red-200 border border-red-500/30 text-xs">Kick</button>
                    )}
                  </div>
                ))}
              </div>
            </div>
            {isLeader && (
              <div className="mt-4">
                <div className="text-gray-300 text-sm mb-1">Pending Join Requests</div>
                <div className="space-y-2 max-h-40 overflow-auto pr-1">
                  {pendingRequests.length === 0 ? (
                    <div className="text-gray-400 text-xs">No pending requests.</div>
                  ) : pendingRequests.map(r => (
                    <div key={r.id} className="p-2 rounded bg-white/5 border border-white/10 flex items-center justify-between">
                      <div className="text-gray-100 text-sm">@{r.applicant_username}</div>
                      <div className="flex items-center gap-2">
                        <button onClick={async ()=>{ try{ const res = await fetch(apiUrl('/api/clan_join_requests/decision'), { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }, body: JSON.stringify({ request_id: r.id, decision: 'approve' })}); const d = await res.json(); if(res.ok){ setSuccess('Approved.'); load(); } else setError(d?.error||'Failed'); } catch{ setError('Network error.'); } }} className="px-2 py-1 rounded bg-eco-green/20 text-eco-green text-xs">Approve</button>
                        <button onClick={async ()=>{ try{ const res = await fetch(apiUrl('/api/clan_join_requests/decision'), { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }, body: JSON.stringify({ request_id: r.id, decision: 'reject' })}); const d = await res.json(); if(res.ok){ setSuccess('Rejected.'); load(); } else setError(d?.error||'Failed'); } catch{ setError('Network error.'); } }} className="px-2 py-1 rounded bg-red-500/20 text-red-200 text-xs">Reject</button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Right: Clan chat */}
      <div className="rounded-xl bg-white/5 border border-white/10 p-4">
        <div className="text-gray-100 text-lg font-semibold mb-2">Clan Chat</div>
        {!myClan ? (
          <div className="text-gray-400 text-sm">Join or create a clan to chat.</div>
        ) : (
          <div className="flex flex-col h-80">
            <div className="flex items-center justify-between mb-2">
              <div className="text-gray-300 text-sm">Chatting in {myClan.name}</div>
              <button onClick={loadChat} disabled={chatLoading} className="text-xs text-gray-300 hover:text-white">{chatLoading ? 'Loading…' : 'Refresh'}</button>
            </div>
            <div className="flex-1 overflow-auto space-y-2 pr-1">
              {chatMessages.map(m => (
                <div key={m.id} className="flex items-start gap-2">
                  <div className="flex-1">
                    <div className="text-xs text-gray-400"><span className="text-gray-200 font-semibold">@{m.sender_username}</span> <span className="ml-2 text-[10px] opacity-70">{new Date((m.created_at||'').replace(' ','T')+'Z').toLocaleString()}</span></div>
                    <div className="text-sm text-gray-100 whitespace-pre-wrap">{m.message}</div>
                  </div>
                  {/* Allow delete for sender or leader - backend enforces */}
                  <button onClick={() => deleteMessage(m.id)} className="text-xs text-red-300 hover:text-red-200" title="Delete">✖</button>
                </div>
              ))}
              {chatMessages.length === 0 && !chatLoading && (
                <div className="text-xs text-gray-400">No messages yet.</div>
              )}
            </div>
            <div className="mt-2 flex items-center gap-2">
              <input type="text" value={chatText} onChange={(e)=>setChatText(e.target.value)} placeholder="Type a message…" className="flex-1 px-3 py-2 rounded bg-black/40 border border-white/10 text-gray-100" />
              <button onClick={sendChat} disabled={!chatText.trim() || chatLoading} className={`px-3 py-2 rounded text-sm font-semibold ${(!chatText.trim()||chatLoading)?'bg-gray-500/40 text-gray-300':'bg-eco-green text-eco-dark'}`}>Send</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default ClansPanel;

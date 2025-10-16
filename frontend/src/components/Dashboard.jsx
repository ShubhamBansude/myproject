// src/components/Dashboard.jsx

import React, { useState, useEffect, lazy, Suspense, useRef } from 'react';
import { apiUrl, API_BASE_URL } from '../lib/api';

// Lazy-load heavy tab panels to split Dashboard chunk
const EarnPoints = lazy(() => import('./EarnPoints'));
const WasteBounty = lazy(() => import('./WasteBounty'));
const ClansPanel = lazy(() => import('./ClansPanel'));
const Leaderboard = lazy(() => import('./Leaderboard'));

const RewardsShop = ({ onRedeem }) => {
  const [coupons, setCoupons] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [certUrl, setCertUrl] = useState('');
  const [redeemingCert, setRedeemingCert] = useState(false);
  const token = localStorage.getItem('authToken');

  useEffect(() => {
    const load = async () => {
      setLoading(true); setError('');
      try {
        const res = await fetch(apiUrl('/api/coupons'), { headers: { Authorization: `Bearer ${token}` } });
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


  // On mount/load, check if user already has a certificate issued
  useEffect(() => {
    const loadMyCert = async () => {
      try {
        const res = await fetch(apiUrl('/api/my_certificate'), { headers: { Authorization: `Bearer ${token}` } });
        const data = await res.json();
        if (res.ok && data?.certificate_url) {
          setCertUrl(data.certificate_url);
        }
      } catch {/* noop */}
    };
    if (token) loadMyCert();
  }, [token]);

  const redeem = async (couponId) => {
    setError('');
    try {
      const res = await fetch(apiUrl('/api/redeem'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ coupon_id: couponId })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error || 'Redeem failed');
      onRedeem(data.total_points, true); // mark redeemed
      alert(`Redeemed! Code: ${data.coupon_code}`);
      if (data.external_url) {
        window.open(data.external_url, '_blank', 'noopener');
      }
    } catch (e) {
      setError(e.message);
    }
  };

  const redeemCertificate = async () => {
    setError(''); setRedeemingCert(true);
    try {
      const res = await fetch(apiUrl('/api/redeem_certificate'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({})
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error || 'Certificate redeem failed');
      onRedeem(data.total_points, true);
      setCertUrl(data.certificate_url);
    } catch (e) {
      setError(e.message);
    } finally {
      setRedeemingCert(false);
    }
  };

  return (
    <div>
      {loading && <div className="text-gray-300">Loading...</div>}
      {error && <div className="p-3 mb-3 text-sm text-red-300 bg-red-500/10 border border-red-500/20 rounded">{error}</div>}
      <div className="flex items-center mb-3">
        <div className="text-sm text-gray-300">Redeem eco-friendly coupons with your points.</div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {/* Carbon Warrior Certificate card */}
        <div className="rounded-xl bg-white/5 border border-white/10 p-4 relative overflow-hidden">
          <div className="absolute inset-0 pointer-events-none">
            <div className="absolute -top-8 -right-8 w-48 h-48 bg-emerald-500/20 rounded-full blur-2xl" />
            <div className="absolute -bottom-8 -left-8 w-48 h-48 bg-amber-400/20 rounded-full blur-2xl" />
          </div>
          <div className="flex items-center gap-3">
            <img src="/swachh-bharat.svg" alt="Swachh Bharat" className="h-8 w-auto" />
            <img src="/vpkbiet-logo.png" alt="VPKBIET" className="h-8 w-auto ml-1 opacity-90" />
            <div>
              <div className="text-lg font-semibold text-gray-100">Carbon Warrior Certificate</div>
              <div className="text-sm text-gray-300">Personalized certificate with your username</div>
            </div>
          </div>
          {certUrl && (
            <a
              href={`${API_BASE_URL}${certUrl.replace('/certificates/', '/certificates/download/')}`}
              className="absolute top-4 right-4 px-2 py-1 rounded-md bg-eco-green/90 text-eco-dark border border-eco-green/40 text-xs hover:brightness-110"
              title="Download certificate"
            >
              📥
            </a>
          )}
          <div className="mt-3 text-xs text-gray-400">
            Features themed design with cleanliness and recycling motifs, Swachh Bharat Mission logo and VPKBIET logo.
          </div>
          <div className="mt-3 flex items-center justify-between">
            <span className="px-3 py-1 rounded-full bg-eco-green/20 text-eco-green border border-eco-green/30 text-sm">5000 pts</span>
            {!certUrl ? (
              <button onClick={redeemCertificate} disabled={redeemingCert} className="px-3 py-2 rounded-lg bg-eco-green text-white text-sm hover:brightness-110 disabled:opacity-60">
                {redeemingCert ? 'Generating…' : 'Get Certificate'}
              </button>
            ) : (
              <div className="flex gap-2">
                <a href={`${API_BASE_URL}${certUrl}`} target="_blank" rel="noreferrer" className="px-3 py-2 rounded-md bg-white/10 border border-white/20 text-gray-100 text-sm hover:bg-white/20">Open</a>
                <a href={`${API_BASE_URL}${certUrl.replace('/certificates/', '/certificates/download/')}`} download className="px-3 py-2 rounded-md bg-eco-green text-eco-dark text-sm hover:brightness-110">Download</a>
              </div>
            )}
          </div>
          {certUrl && (
            <div className="mt-4 p-3 rounded-lg bg-black/30 border border-white/10">
              <div className="text-gray-200 text-sm font-medium mb-2">Your Certificate</div>
              <div className="flex gap-2">
                <a href={`${API_BASE_URL}${certUrl}`} target="_blank" rel="noreferrer" className="px-3 py-2 rounded-md bg-white/10 border border-white/20 text-gray-100 text-sm hover:bg-white/20">Open</a>
                <a href={`${API_BASE_URL}${certUrl.replace('/certificates/', '/certificates/download/')}`} download className="px-3 py-2 rounded-md bg-eco-green text-eco-dark text-sm hover:brightness-110">Download</a>
              </div>
              <div className="mt-3 h-48 bg-white/5 border border-white/10 rounded-md overflow-hidden">
                <iframe title="certificate" src={`${API_BASE_URL}${certUrl}`} className="w-full h-full"></iframe>
              </div>
            </div>
          )}
        </div>
        {coupons.map(c => (
          <div key={c.id} className="rounded-xl bg-white/5 border border-white/10 p-4">
            <div className="text-lg font-semibold text-gray-100">{c.name}</div>
            <div className="text-sm text-gray-300 mb-2">{c.description}</div>
            <div className="flex items-center justify-between">
              <span className="px-3 py-1 rounded-full bg-eco-green/20 text-eco-green border border-eco-green/30 text-sm">{c.points_cost} pts</span>
              <button onClick={() => redeem(c.id)} className="px-3 py-2 rounded-lg bg-eco-green text-white text-sm hover:brightness-110">Redeem</button>
            </div>
            {c.external_url && (
              <a href={c.external_url} target="_blank" rel="noreferrer" className="inline-block mt-2 text-xs text-eco-accent hover:underline">View offer ↗</a>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

const FriendsPanel = () => {
  const token = localStorage.getItem('authToken');
  const [friends, setFriends] = useState([]);
  const [pendingIn, setPendingIn] = useState([]);
  const [pendingOut, setPendingOut] = useState([]);
  const [addUsername, setAddUsername] = useState('');
  const [dmWith, setDmWith] = useState('');
  const [messages, setMessages] = useState([]);
  const [text, setText] = useState('');
  // Clean-buddy state
  const [botOpen, setBotOpen] = useState(false);
  const [botMsgs, setBotMsgs] = useState([]);
  const [botText, setBotText] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const load = async () => {
    setError('');
    try {
      const r = await fetch(apiUrl('/api/friends'), { headers: { Authorization: `Bearer ${token}` } });
      const d = await r.json();
      if (!r.ok) { setError(d?.error||'Failed to load'); return; }
      setFriends(d.friends||[]);
      setPendingIn(d.pending_incoming||[]);
      setPendingOut(d.pending_outgoing||[]);
    } catch { setError('Network error.'); }
  };
  useEffect(()=>{ if (token) load(); }, [token]);
  const add = async () => {
    const u = (addUsername||'').trim(); if (!u) return;
    setLoading(true); setError('');
    try {
      const r = await fetch(apiUrl('/api/friends/add'), { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }, body: JSON.stringify({ username: u }) });
      const d = await r.json();
      if (!r.ok) { setError(d?.error||'Failed'); } else { setAddUsername(''); await load(); window.dispatchEvent(new CustomEvent('openUserPeek',{ detail: { username: u } })); }
    } catch { setError('Network error.'); } finally { setLoading(false); }
  };
  const decide = async (u, decision) => {
    try { const r = await fetch(apiUrl('/api/friends/decision'), { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }, body: JSON.stringify({ username: u, decision })}); const d = await r.json(); if (r.ok) load(); else setError(d?.error||'Failed'); } catch { setError('Network error.'); }
  };
  const loadDm = async (u) => {
    setDmWith(u); setLoading(true); setError('');
    try { const r = await fetch(apiUrl(`/api/dm?with=${encodeURIComponent(u)}`), { headers: { Authorization: `Bearer ${token}` } }); const d = await r.json(); if (!r.ok) { setError(d?.error||'Failed'); setMessages([]); } else setMessages(d.messages||[]); } catch { setError('Network error.'); } finally { setLoading(false); }
  };
  const sendDm = async () => {
    const body = (text||'').trim(); if (!body || !dmWith) return;
    setLoading(true);
    try { const r = await fetch(apiUrl('/api/dm'), { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }, body: JSON.stringify({ to: dmWith, message: body }) }); const d = await r.json(); if (r.ok) { setMessages((m)=>[...m, d.message]); setText(''); } else setError(d?.error||'Failed'); } catch { setError('Network error.'); } finally { setLoading(false); }
  };

  const openBot = async () => {
    setBotOpen(true); setDmWith(''); setMessages([]);
    try {
      const r = await fetch(apiUrl('/api/clean_buddy'), { headers: { Authorization: `Bearer ${token}` } });
      const d = await r.json();
      if (r.ok) setBotMsgs(d.messages || []);
    } catch {/* noop */}
  };

  const sendBot = async () => {
    const body = (botText||'').trim(); if (!body) return;
    try {
      const r = await fetch(apiUrl('/api/clean_buddy'), { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }, body: JSON.stringify({ message: body }) });
      const d = await r.json();
      if (r.ok) {
        // Optimistically show user message then bot reply
        const now = new Date().toISOString().slice(0,19).replace('T',' ');
        setBotMsgs((m)=>[...m, { id: `u_${Date.now()}`, sender_username: 'you', message: body, created_at: now }, d.message]);
        setBotText('');
      }
    } catch {/* noop */}
  };

  // Allow deep-linking to DM via global event from notifications
  useEffect(() => {
    const handler = (e) => {
      const u = e?.detail?.username; if (u) loadDm(u);
    };
    window.addEventListener('openDmWith', handler);
    return () => window.removeEventListener('openDmWith', handler);
  }, []);
  return (
    <div className="grid gap-4 md:grid-cols-[1.1fr_1.2fr]">
      <div className="rounded-xl bg-white/5 border border-white/10 p-4">
        <div className="text-gray-100 text-lg font-semibold mb-2">Friends</div>
        {error && <div className="p-2 text-sm text-red-300 bg-red-500/10 border border-red-500/20 rounded mb-2">{error}</div>}
        <div className="mb-3 flex items-center gap-2">
          <input type="text" value={addUsername} onChange={(e)=>setAddUsername(e.target.value)} placeholder="Add by username" className="flex-1 px-3 py-2 rounded bg-black/40 border border-white/10 text-gray-100" />
          <button onClick={add} disabled={loading} className="px-3 py-2 rounded bg-eco-green text-eco-dark font-semibold">Add</button>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <div className="text-gray-300 text-sm mb-1">Your friends</div>
            <div className="space-y-2 max-h-48 overflow-auto pr-1">
              {friends.map(f => (
                <div key={f.username} className="p-2 rounded bg-white/5 border border-white/10 flex items-center justify-between">
                  <button
                    onClick={()=>window.dispatchEvent(new CustomEvent('openUserPeek',{ detail: { username: f.username } }))}
                    className="text-left text-gray-100 text-sm hover:underline"
                    title="View profile"
                  >@{f.username}</button>
                  <button onClick={()=>loadDm(f.username)} className="px-2 py-1 text-xs rounded bg-eco-green/20 text-eco-green border border-eco-green/30">Chat</button>
                </div>
              ))}
              {friends.length===0 && <div className="text-gray-400 text-xs">No friends yet.</div>}
            </div>
          </div>
          <div>
            <div className="text-gray-300 text-sm mb-1">Requests</div>
            <div className="space-y-2 max-h-48 overflow-auto pr-1">
              {pendingIn.map(u => (
                <div key={u} className="p-2 rounded bg-white/5 border border-white/10 flex items-center justify-between">
                  <span className="text-gray-100 text-sm">@{u}</span>
                  <div className="flex items-center gap-2 text-xs">
                    <button onClick={()=>decide(u,'accept')} className="px-2 py-1 rounded bg-eco-green/20 text-eco-green">Accept</button>
                    <button onClick={()=>decide(u,'reject')} className="px-2 py-1 rounded bg-red-500/20 text-red-200">Reject</button>
                  </div>
                </div>
              ))}
              {pendingIn.length===0 && <div className="text-gray-400 text-xs">No incoming.</div>}
              {pendingOut.length>0 && (
                <div className="text-gray-400 text-xs mt-2">Outgoing: {pendingOut.map(u=>'@'+u).join(', ')}</div>
              )}
            </div>
          </div>
        </div>
      </div>
      <div className="rounded-xl bg-white/5 border border-white/10 p-4">
        <div className="flex items-center justify-between mb-2">
          <div className="text-gray-100 text-lg font-semibold">Direct Messages</div>
          <button onClick={openBot} className="text-xs px-2 py-1 rounded bg-eco-accent text-eco-dark">Chat with Clean-buddy</button>
        </div>
        {!dmWith && !botOpen && (
          <div className="text-gray-400 text-sm">Select a friend or open Clean-buddy.</div>
        )}
        {dmWith && !botOpen && (
          <div className="flex flex-col h-80">
            <div className="flex items-center justify-between mb-2">
              <div className="text-gray-300 text-sm">Chatting with @{dmWith}</div>
              <button onClick={()=>loadDm(dmWith)} disabled={loading} className="text-xs text-gray-300 hover:text-white">{loading?'Loading…':'Refresh'}</button>
            </div>
            <div className="flex-1 overflow-auto space-y-2 pr-1">
              {messages.map(m => (
                <div key={m.id} className="flex items-start gap-2">
                  <div className="flex-1">
                    <div className="text-xs text-gray-400"><span className="text-gray-200 font-semibold">@{m.sender_username}</span> <span className="ml-2 text-[10px] opacity-70">{new Date((m.created_at||'').replace(' ','T')+'Z').toLocaleString()}</span></div>
                    <div className="text-sm text-gray-100 whitespace-pre-wrap">{m.message}</div>
                  </div>
                </div>
              ))}
              {messages.length===0 && !loading && <div className="text-xs text-gray-400">No messages yet.</div>}
            </div>
            <div className="mt-2 flex items-center gap-2">
              <input type="text" value={text} onChange={(e)=>setText(e.target.value)} placeholder="Type a message…" className="flex-1 px-3 py-2 rounded bg-black/40 border border-white/10 text-gray-100" onKeyDown={(e)=>{ if(e.key==='Enter'){ e.preventDefault(); sendDm(); } }} />
              <button onClick={sendDm} disabled={!text.trim()||loading} className={`px-3 py-2 rounded text-sm font-semibold ${(!text.trim()||loading)?'bg-gray-500/40 text-gray-300':'bg-eco-green text-eco-dark'}`}>Send</button>
            </div>
          </div>
        )}
        {botOpen && (
          <div className="flex flex-col h-80">
            <div className="flex items-center justify-between mb-2">
              <div className="text-gray-300 text-sm">Chatting with Clean-buddy</div>
              <button onClick={openBot} className="text-xs text-gray-300 hover:text-white">Refresh</button>
            </div>
            <div className="flex-1 overflow-auto space-y-2 pr-1">
              {botMsgs.map(m => (
                <div key={m.id} className="flex items-start gap-2">
                  <div className="flex-1">
                    <div className="text-xs text-gray-400"><span className="text-gray-200 font-semibold">@{m.sender_username}</span> <span className="ml-2 text-[10px] opacity-70">{new Date((m.created_at||'').replace(' ','T')+'Z').toLocaleString()}</span></div>
                    <div className="text-sm text-gray-100 whitespace-pre-wrap">{m.message}</div>
                  </div>
                </div>
              ))}
              {botMsgs.length===0 && <div className="text-xs text-gray-400">No messages yet.</div>}
            </div>
            <div className="mt-2 flex items-center gap-2">
              <input type="text" value={botText} onChange={(e)=>setBotText(e.target.value)} placeholder="Ask anything…" className="flex-1 px-3 py-2 rounded bg-black/40 border border-white/10 text-gray-100" onKeyDown={(e)=>{ if(e.key==='Enter'){ e.preventDefault(); sendBot(); } }} />
              <button onClick={sendBot} disabled={!botText.trim()} className={`px-3 py-2 rounded text-sm font-semibold ${(!botText.trim())?'bg-gray-500/40 text-gray-300':'bg-eco-green text-eco-dark'}`}>Send</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

const UserProfilePeek = ({ username, onClose }) => {
  const token = localStorage.getItem('authToken');
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => {
    const load = async () => {
      setError('');
      try {
        const res = await fetch(apiUrl(`/api/user_profile?username=${encodeURIComponent(username)}`), { headers: { Authorization: `Bearer ${token}` } });
        const d = await res.json();
        if (!res.ok) { setError(d?.error||'Failed to load profile'); } else { setData(d); }
      } catch { setError('Network error.'); }
    };
    if (username) load();
  }, [username]);
  if (!username) return null;
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/60">
      <div className="w-full max-w-md rounded-xl bg-[#0b1220] border border-white/10 p-4">
        <div className="flex items-center justify-between mb-2">
          <div className="text-gray-100 font-semibold">@{username}</div>
          <button onClick={onClose} className="text-sm text-gray-300 hover:text-white">✖</button>
        </div>
        {error && <div className="p-2 text-xs text-red-300 bg-red-500/10 border border-red-500/20 rounded mb-2">{error}</div>}
        {!data ? (
          <div className="text-gray-400 text-sm">Loading…</div>
        ) : (
          <div className="space-y-2 text-sm text-gray-200">
            <div className="flex items-center justify-between"><span className="text-gray-400">Location</span><span>{data.location?.city}, {data.location?.state}, {data.location?.country}</span></div>
            <div className="flex items-center justify-between"><span className="text-gray-400">Total Points</span><span className="text-eco-green font-semibold">{data.total_points}</span></div>
            <div className="flex items-center justify-between"><span className="text-gray-400">Lifetime Points</span><span>{data.lifetime_points}</span></div>
            <div className="flex items-center justify-between"><span className="text-gray-400">Lifetime Detections</span><span>{data.lifetime_detections}</span></div>
            <div className="flex items-center justify-between"><span className="text-gray-400">Claimed Bounties</span><span>{data.lifetime_claimed_bounties}</span></div>
            <div className="flex items-center justify-between"><span className="text-gray-400">Clan</span><span>{data.clan ? `${data.clan.name} (${data.clan.role})` : '—'}</span></div>
          </div>
        )}
      </div>
    </div>
  );
};

const ProfileView = ({ user, setCurrentUser, lifetimePoints }) => {
  const [openChange, setOpenChange] = useState(false);
  const [email, setEmail] = useState(user.email || '');
  const [newUsername, setNewUsername] = useState('');
  const [otp, setOtp] = useState('');
  const [step, setStep] = useState('request'); // request | confirm
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const requestChange = async (e) => {
    e.preventDefault(); setError(''); setMessage('');
    if (!newUsername.trim()) { setError('Enter a new username.'); return; }
    try {
      const res = await fetch(apiUrl('/api/request_username_change'), {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim(), new_username: newUsername.trim() })
      });
      const data = await res.json();
      if (!res.ok) { setError(data?.error || 'Failed to send OTP.'); return; }
      setMessage('OTP sent to your email. Enter it below to confirm.');
      setStep('confirm');
    } catch { setError('Network error. Please try again.'); }
  };

  const confirmChange = async (e) => {
    e.preventDefault(); setError(''); setMessage('');
    if (!otp.trim()) { setError('Enter the OTP received by email.'); return; }
    try {
      const res = await fetch(apiUrl('/api/confirm_username_change'), {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim(), otp: otp.trim() })
      });
      const data = await res.json();
      if (!res.ok) { setError(data?.error || 'Failed to update username.'); return; }
      setMessage('Username updated successfully.');
      // Update auth token and in-memory user
      localStorage.setItem('authToken', data.token);
      setCurrentUser((prev) => ({ ...prev, ...data.user }));
      setOpenChange(false); setStep('request'); setOtp(''); setNewUsername('');
    } catch { setError('Network error. Please try again.'); }
  };

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <div className="rounded-xl bg-white/5 border border-white/10 p-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-gray-400 text-sm">Username</div>
            <div className="text-gray-100 text-xl font-semibold">{user.username}</div>
          </div>
          <button onClick={() => { setOpenChange((o)=>!o); setError(''); setMessage(''); }} className="px-3 py-1 text-xs rounded-lg bg-white/5 border border-white/10 text-gray-200 hover:bg-white/10">Change</button>
        </div>
        {openChange && (
          <div className="mt-3 p-3 rounded-lg bg-white/5 border border-white/10">
            <form onSubmit={step==='request'?requestChange:confirmChange} className="space-y-3">
              <div>
                <label className="block text-xs text-gray-300 mb-1">Email</label>
                <input type="email" value={email} onChange={(e)=>setEmail(e.target.value)} className="w-full px-3 py-2 rounded bg-black/40 border border-white/10 text-gray-100" />
              </div>
              {step==='request' ? (
                <div>
                  <label className="block text-xs text-gray-300 mb-1">New Username</label>
                  <input type="text" value={newUsername} onChange={(e)=>setNewUsername(e.target.value)} className="w-full px-3 py-2 rounded bg-black/40 border border-white/10 text-gray-100" />
                </div>
              ) : (
                <div>
                  <label className="block text-xs text-gray-300 mb-1">OTP</label>
                  <input type="text" value={otp} onChange={(e)=>setOtp(e.target.value)} placeholder="6-digit code" className="w-full px-3 py-2 rounded bg-black/40 border border-white/10 text-gray-100" />
                </div>
              )}
              {error && <div className="text-red-300 text-xs bg-red-500/10 border border-red-500/20 rounded p-2">{error}</div>}
              {message && <div className="text-green-300 text-xs bg-emerald-500/10 border border-emerald-500/20 rounded p-2">{message}</div>}
              <div className="flex items-center gap-2">
                <button type="submit" className="px-3 py-2 text-xs rounded-lg bg-eco-green text-eco-dark font-semibold">{step==='request'?'Send OTP':'Confirm'}</button>
                <button type="button" onClick={()=>{ setOpenChange(false); setStep('request'); setOtp(''); setNewUsername(''); }} className="px-3 py-2 text-xs rounded-lg bg-white/5 border border-white/10 text-gray-200">Cancel</button>
              </div>
            </form>
          </div>
        )}
      </div>
      <div className="rounded-xl bg-white/5 border border-white/10 p-4">
        <div className="text-gray-400 text-sm">Total Points</div>
        <div className="text-gray-100 text-xl font-semibold">{user.total_points}</div>
      </div>
      <div className="rounded-xl bg-white/5 border border-white/10 p-4">
        <div className="text-gray-400 text-sm">Lifetime Points</div>
        <div className="text-gray-100 text-xl font-semibold">{lifetimePoints ?? 0}</div>
      </div>
      <div className="rounded-xl bg-white/5 border border-white/10 p-4">
        <div className="text-gray-400 text-sm">Email</div>
        <div className="text-gray-100 text-xl font-semibold break-all">{user.email || '—'}</div>
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
  const [activeTab, setActiveTab] = useState('scan');
  const [stats, setStats] = useState({ detections: 0, redemptions: 0, lifetime_points: 0 });
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [notifOpen, setNotifOpen] = useState(false);
  const eventSourceRef = useRef(null);
  const [peekUser, setPeekUser] = useState('');
  const [missions, setMissions] = useState([]);
  const [missionLoading, setMissionLoading] = useState(false);
  const [missionError, setMissionError] = useState('');
  const [rewardOpen, setRewardOpen] = useState(false);
  const [confettiBurst, setConfettiBurst] = useState(false);
  const [carbon, setCarbon] = useState({ week_total_kg: 0, sources: { plastic: 0, paper: 0, metal: 0 }, planet_health: 0 });
  const [streak, setStreak] = useState({ current_streak: 0, best_streak: 0, days: [] });
  const [bountyToOpen, setBountyToOpen] = useState(null);

  const fetchStats = async () => {
    const token = localStorage.getItem('authToken');
    try {
      const res = await fetch(apiUrl('/api/stats'), { headers: { Authorization: `Bearer ${token}` } });
      const data = await res.json();
      if (res.ok) setStats({ detections: data.detections || 0, redemptions: data.redemptions || 0, lifetime_points: data.lifetime_points || 0 });
    } catch {
      // ignore network errors
    }
  };

  useEffect(() => { fetchStats(); }, []);

  // Load missions
  const loadMissions = async () => {
    setMissionLoading(true); setMissionError('');
    try {
      const token = localStorage.getItem('authToken');
      const res = await fetch(apiUrl('/api/missions/today'), { headers: { Authorization: `Bearer ${token}` } });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error || 'Failed to load missions');
      setMissions(Array.isArray(data.missions) ? data.missions : []);
    } catch (e) {
      setMissionError(e.message || 'Failed to load missions');
    } finally { setMissionLoading(false); }
  };
  useEffect(()=>{ loadMissions(); }, []);

  // Load carbon stats
  const loadCarbon = async () => {
    try {
      const token = localStorage.getItem('authToken');
      const res = await fetch(apiUrl('/api/stats/carbon'), { headers: { Authorization: `Bearer ${token}` } });
      const data = await res.json();
      if (res.ok) setCarbon({
        week_total_kg: data.week_total_kg || 0,
        sources: data.sources || { plastic: 0, paper: 0, metal: 0 },
        planet_health: data.planet_health || 0
      });
    } catch {/* noop */}
  };
  useEffect(()=>{ loadCarbon(); }, []);

  // Load streak
  const loadStreak = async () => {
    try {
      const token = localStorage.getItem('authToken');
      const res = await fetch(apiUrl('/api/streak'), { headers: { Authorization: `Bearer ${token}` } });
      const data = await res.json();
      if (res.ok) setStreak(data);
    } catch {/* noop */}
  };
  useEffect(()=>{ loadStreak(); }, []);

  const completeMission = async (missionId) => {
    try {
      const token = localStorage.getItem('authToken');
      const res = await fetch(apiUrl('/api/missions/complete'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ mission_id: missionId })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error || 'Failed to complete mission');
      setRewardOpen(true); setConfettiBurst(true);
      setTimeout(()=>setConfettiBurst(false), 1400);
      if (typeof data.total_points === 'number') {
        updatePoints(data.total_points);
      }
      await loadMissions();
    } catch (e) {
      alert(e.message || 'Mission failed');
    }
  };

  // Global listener to open UserProfilePeek from other components
  useEffect(() => {
    const handler = (e) => {
      const u = e?.detail?.username; if (u) setPeekUser(u);
    };
    window.addEventListener('openUserPeek', handler);
    return () => window.removeEventListener('openUserPeek', handler);
  }, []);

  // Global listener for leader to open bounty from ClansPanel
  useEffect(() => {
    const handler = (e) => {
      const id = e?.detail?.bountyId; if (id) { setActiveTab('bounty'); setBountyToOpen(id); }
    };
    window.addEventListener('openBountyFromLeader', handler);
    return () => window.removeEventListener('openBountyFromLeader', handler);
  }, []);

  // Load stored notifications on login/mount
  useEffect(() => {
    const token = localStorage.getItem('authToken');
    if (!token) return;
    const load = async () => {
      try {
        const res = await fetch(apiUrl('/api/notifications'), {
          headers: { Authorization: `Bearer ${token}` },
        });
        const data = await res.json();
        if (res.ok) {
          let list = Array.isArray(data.notifications) ? data.notifications : [];
          // Filter out Clean-buddy chat notifications by type or text
          list = list.filter((n)=> {
            const t = String(n.type||'');
            const title = String(n.title||'');
            const msg = String(n.message||'');
            const isCleanBuddyType = /CLEAN_BUDDY_CHAT|CLEANBUDDY|CLEAN_BUDDY/i.test(t);
            const mentionsCleanBuddy = /clean[-_\s]?buddy/i.test(title) || /clean[-_\s]?buddy/i.test(msg);
            return !isCleanBuddyType && !mentionsCleanBuddy;
          });
          // Inject eco tips notifications (non-intrusive) at top once per session
          const tips = [
            { id: `tip_${Date.now()}_1`, type: 'TIP', title: 'Eco Tip', message: 'Separate wet and dry waste daily to improve recycling.', created_at: new Date().toISOString().slice(0,19).replace('T',' '), read_at: null },
            { id: `tip_${Date.now()}_2`, type: 'TIP', title: 'Recycling Tip', message: 'Rinse bottles before recycling to avoid contamination.', created_at: new Date().toISOString().slice(0,19).replace('T',' '), read_at: null },
          ];
          list = [...tips, ...list];
          setNotifications(list);
          setUnreadCount(list.filter((n) => !n.read_at).length);
        }
      } catch {
        // ignore network errors
      }
    };
    load();
  }, []);

  // Subscribe to real-time notifications via SSE
  useEffect(() => {
    const token = localStorage.getItem('authToken');
    if (!token) return;
    try {
      const es = new EventSource(apiUrl(`/api/notifications/stream?token=${encodeURIComponent(token)}`));
      eventSourceRef.current = es;
      es.onmessage = (evt) => {
        try {
          const payload = JSON.parse(evt.data);
          // Ignore Clean-buddy chat message events
          const t = String(payload.type || '');
          const title = String(payload.title||'');
          const msg = String(payload.message||'');
          if (/CLEAN_BUDDY_CHAT|CLEANBUDDY|CLEAN_BUDDY/i.test(t)) return;
          if (/clean[-_\s]?buddy/i.test(title) || /clean[-_\s]?buddy/i.test(msg)) return;
          const notif = {
            id: payload.id || `temp_${Date.now()}`,
            type: payload.type,
            title: payload.title,
            message: payload.message,
            city: payload.city || '',
            payload: payload.payload || null,
            context_bounty_id: payload.context_bounty_id,
            created_at: payload.created_at || new Date().toISOString().slice(0, 19).replace('T', ' '),
            read_at: null,
          };
          setNotifications((prev) => [notif, ...prev]);
          setUnreadCount((c) => c + 1);
        } catch {
          // ignore malformed SSE message
        }
      };
      es.onerror = () => {
        // Let the browser handle reconnection automatically
      };
      return () => {
        try { es.close(); } catch { /* noop */ }
      };
    } catch { /* noop */ }
  }, []);

  const markAllNotificationsRead = async () => {
    const token = localStorage.getItem('authToken');
    try {
      const res = await fetch(apiUrl('/api/notifications/read'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ all: true }),
      });
      if (res.ok) {
        const now = new Date().toISOString().slice(0, 19).replace('T', ' ');
        setNotifications((prev) => prev.map((n) => (n.read_at ? n : { ...n, read_at: now })));
        setUnreadCount(0);
      }
    } catch { /* noop */ }
  };

  const formatDateTime = (s) => {
    if (!s) return '';
    // s is typically 'YYYY-MM-DD HH:MM:SS'
    try {
      const asIso = s.includes('T') ? s : s.replace(' ', 'T') + 'Z';
      return new Date(asIso).toLocaleString();
    } catch {
      return s;
    }
  };

  const updatePoints = (newPoints, redeemed = false) => {
    setCurrentUser(prev => ({ ...prev, total_points: newPoints }));
    if (redeemed || activeTab === 'scan') fetchStats();
  };

  const tabs = [
    { key: 'scan', label: 'Smart Waste Scan', icon: '♻️' },
    { key: 'bounty', label: 'Waste Bounty', icon: '🗺️' },
    { key: 'clans', label: 'Clans', icon: '🛡️' },
    { key: 'friends', label: 'Friends & Chat', icon: '💬' },
    { key: 'leaderboard', label: 'Leaderboard', icon: '🏆' },
    { key: 'rewards', label: 'Rewards', icon: '🎁' },
    { key: 'profile', label: 'Profile', icon: '👤' },
  ];

  let main;
  if (activeTab === 'scan') {
    main = <EarnPoints currentUser={currentUser} updatePoints={updatePoints} />;
  } else if (activeTab === 'bounty') {
    main = <WasteBounty currentUser={currentUser} updatePoints={updatePoints} bountyToOpen={bountyToOpen} />;
  } else if (activeTab === 'clans') {
    main = <ClansPanel currentUser={currentUser} />;
  } else if (activeTab === 'friends') {
    main = <FriendsPanel />;
  } else if (activeTab === 'leaderboard') {
    main = <Leaderboard />;
  } else if (activeTab === 'rewards') {
    main = <RewardsShop onRedeem={updatePoints} />;
  } else {
    main = <ProfileView user={currentUser} setCurrentUser={setCurrentUser} lifetimePoints={stats.lifetime_points} />;
  }

  // removed unused progress constants

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
          <div className="flex items-center gap-3">
            <img src="/swachh-bharat.svg" alt="Swachh Bharat" className="h-6 w-auto opacity-90" />
            <div className="flex items-center gap-1">
              <span className="text-white font-extrabold text-xl font-display">Waste</span>
              <span className="text-eco-green font-extrabold text-xl font-display">Rewards</span>
            </div>
          </div>
          <div className="flex items-center gap-3 text-sm relative">
            {/* Notification bell placed to the left of the username */}
            <div className="relative">
              <button
                onClick={() => setNotifOpen((o) => !o)}
                className="px-3 py-1 rounded-lg border border-white/10 bg-white/5 text-gray-200 hover:bg-white/10 transition relative"
                aria-label="Notifications"
              >
                🔔
                {unreadCount > 0 && (
                  <span className="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 rounded-full bg-eco-accent text-eco-dark text-[10px] font-bold flex items-center justify-center border border-amber-300/50">
                    {unreadCount}
                  </span>
                )}
              </button>
              {notifOpen && (
                <div className="absolute right-0 mt-2 w-80 max-h-96 overflow-auto bg-[#0b1220] border border-white/10 rounded-xl shadow-2xl z-30">
                  <div className="flex items-center justify-between p-3 border-b border-white/10">
                    <div className="text-gray-200 font-semibold text-sm">Notifications</div>
                    <button onClick={markAllNotificationsRead} className="text-xs text-eco-green hover:underline">
                      Mark all read
                    </button>
                  </div>
                  <div className="divide-y divide-white/10">
                    {notifications.length === 0 ? (
                      <div className="p-3 text-gray-400 text-sm">No notifications</div>
                    ) : (
                      notifications.map((n) => (
                        <div key={n.id || Math.random()} className="p-3 hover:bg-white/5">
                          <div className="flex items-start justify-between">
                            <div onClick={() => {
                              // Route to specific section based on notification
                              const t = (n.type||'');
                              if (t === 'FRIEND_REQUEST' || t === 'FRIEND_ACCEPTED') {
                                setActiveTab('friends');
                                if (n?.payload?.from_username) {
                                  // open DM thread directly
                                  window.dispatchEvent(new CustomEvent('openDmWith', { detail: { username: n.payload.from_username } }));
                                }
                              } else if (t === 'CLAN_JOIN_REQUEST' || t === 'CLAN_JOIN_DECISION') {
                                setActiveTab('clans');
                              } else if (t === 'BOUNTY_CREATED' || t === 'CLAN_BOUNTY_REQUEST' || t === 'CLAN_BOUNTY_DECISION') {
                                setActiveTab('bounty');
                                if (n.context_bounty_id) setBountyToOpen(n.context_bounty_id);
                              } else if (t === 'FRIEND_DM') {
                                setActiveTab('friends');
                                if (n?.payload?.from_username) {
                                  window.dispatchEvent(new CustomEvent('openDmWith', { detail: { username: n.payload.from_username } }));
                                }
                              } else if (/CLAN/i.test(t) && /(MESSAGE|CHAT)/i.test(t)) {
                                setActiveTab('clans');
                              } else if (/FRIEND/i.test(t) && /(MESSAGE|DM|CHAT)/i.test(t)) {
                                setActiveTab('friends');
                                if (n?.payload?.from_username) {
                                  window.dispatchEvent(new CustomEvent('openDmWith', { detail: { username: n.payload.from_username } }));
                                }
                              }
                              setNotifOpen(false);
                            }} className="cursor-pointer">
                              <div className="text-gray-100 text-sm font-medium">{n.title}</div>
                              <div className="text-gray-300 text-xs">{n.message}</div>
                              <div className="text-gray-500 text-[11px] mt-1">{formatDateTime(n.created_at)}</div>
                            </div>
                            {!n.read_at && <span className="ml-2 mt-1 w-2 h-2 rounded-full bg-eco-green inline-block" />}
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              )}
            </div>
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
          <div className="flex flex-wrap gap-2 bg-white/5 border border-white/10 p-1 rounded-2xl">
            {tabs.map(t => (
              <button
                key={t.key}
                onClick={() => setActiveTab(t.key)}
                className={`px-3 py-2 rounded-xl text-sm transition font-medium ${
                  activeTab === t.key
                    ? 'bg-eco-green text-eco-dark shadow border border-eco-green'
                    : 'text-gray-200 hover:bg-white/10 border border-transparent'
                }`}
              >
                <span className="mr-1">{t.icon}</span> {t.label}
              </button>
            ))}
          </div>
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

          {/* Eco Missions + Carbon Tracker + Eco-Streak (Profile only) */}
          {activeTab === 'profile' && (
            <div className="mt-4 grid grid-cols-1 lg:grid-cols-3 gap-4">
              {/* Missions Card */}
              <div className="rounded-2xl border border-white/10 bg-gradient-to-br from-emerald-500/10 to-white/5 p-4 relative overflow-hidden">
                <div className="flex items-center justify-between mb-2">
                  <div className="text-gray-100 font-semibold">Daily & Weekly Eco Missions</div>
                  <button onClick={loadMissions} className="text-xs text-eco-green hover:underline">Refresh</button>
                </div>
                {missionLoading && <div className="text-xs text-gray-400">Loading…</div>}
                {missionError && <div className="text-xs text-red-300 bg-red-500/10 border border-red-500/20 rounded p-2 mb-2">{missionError}</div>}
                <div className="space-y-3">
                  {missions.map(m => (
                    <div key={m.id} className="p-3 rounded-xl bg-white/5 border border-white/10">
                      <div className="flex items-center justify-between">
                        <div>
                          <div className="text-gray-100 text-sm font-semibold">{m.title}</div>
                          <div className="text-xs text-gray-400">{m.description || (m.goal_type==='daily'?'New challenge arrives tomorrow!':'Ends this week')}</div>
                        </div>
                        <span className="px-2 py-1 rounded-full bg-eco-green/20 text-eco-green border border-eco-green/30 text-xs">+{m.points} pts</span>
                      </div>
                      <div className="mt-2">
                        <div className="w-full h-2 bg-white/10 rounded-full overflow-hidden">
                          <div className="h-2 bg-eco-green rounded-full transition-all" style={{ width: `${m.progress || 0}%` }} />
                        </div>
                        <div className="flex items-center justify-between mt-2 text-xs text-gray-400">
                          <span>{m.status === 'completed' ? 'Completed' : `${m.progress || 0}%`}</span>
                          <button onClick={()=>completeMission(m.id)} disabled={m.status==='completed'} className={`px-2 py-1 rounded-md text-xs font-semibold ${m.status==='completed' ? 'bg-gray-500/30 text-gray-300 cursor-not-allowed' : 'bg-eco-green text-eco-dark'}`}>
                            {m.status==='completed' ? 'Done' : 'Mark Done'}
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                  {missions.length===0 && !missionLoading && (
                    <div className="text-xs text-gray-400">No missions found. Check back soon.</div>
                  )}
                </div>
              </div>

              {/* Carbon Footprint Tracker */}
              <div className="rounded-2xl border border-white/10 bg-gradient-to-br from-emerald-500/10 to-amber-400/10 p-4">
                <div className="text-gray-100 font-semibold mb-1">Carbon Footprint Tracker</div>
                <div className="text-sm text-gray-300">You saved <span className="text-eco-green font-bold">{carbon.week_total_kg.toFixed(1)} kg</span> CO₂ this week!</div>
                <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
                  {['plastic','paper','metal'].map((cat)=> (
                    <div key={cat} className="p-2 rounded-lg bg-white/5 border border-white/10">
                      <div className="text-gray-300 capitalize">{cat}</div>
                      <div className="text-eco-green font-semibold">{(carbon.sources[cat]||0).toFixed(1)} kg</div>
                    </div>
                  ))}
                </div>
                <div className="mt-3">
                  <div className="text-xs text-gray-400 mb-1">Planet Health</div>
                  <div className="w-full h-2 bg-white/10 rounded-full overflow-hidden">
                    <div className="h-2 bg-emerald-400 rounded-full transition-all" style={{ width: `${carbon.planet_health || 0}%` }} />
                  </div>
                </div>
              </div>

              {/* Eco-Streak */}
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="text-gray-100 font-semibold">Eco-Streak</div>
                  <div className="text-xs text-gray-400">Best: {streak.best_streak || 0}</div>
                </div>
                <div className="grid grid-cols-7 gap-2">
                  {(streak.days || []).map((d) => (
                    <div key={d.date} className={`h-8 rounded-lg border flex items-center justify-center text-xs ${d.active ? 'bg-eco-green/30 border-eco-green/40 text-eco-green' : 'bg-white/5 border-white/10 text-gray-300'}`}>✓</div>
                  ))}
                </div>
                <div className="text-xs text-gray-400 mt-2">Current streak: <span className="text-eco-green font-semibold">{streak.current_streak || 0} days</span></div>
              </div>
            </div>
          )}
        </div>

        {/* Content card */}
        <section className="mt-6 rounded-2xl bg-white/5 backdrop-blur border border-white/10 p-6 shadow-2xl relative">
          <h2 className="text-2xl md:text-3xl font-extrabold text-gray-100 mb-6">
            {({
              scan: 'Smart Waste Scan',
              bounty: 'Waste Bounty',
              clans: 'Clans',
              leaderboard: 'Leaderboard',
              rewards: 'Rewards',
              profile: 'Your Profile',
            })[activeTab]}
          </h2>
          <div className="opacity-0 animate-fade-in-up" key={activeTab}>
            <Suspense fallback={<div className="text-gray-400">Loading section…</div>}>
              {main}
            </Suspense>
          </div>
          {/* Lifetime Points widget removed from Rewards */}
        </section>
      </div>

      {/* Reward Modal */}
      {rewardOpen && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/60">
          <div className="w-full max-w-sm rounded-2xl bg-[#0b1220] border border-white/10 p-6 text-center relative overflow-hidden">
            <div className="absolute inset-0 pointer-events-none">
              <div className="absolute -top-20 -right-10 w-64 h-64 bg-emerald-500/20 rounded-full blur-3xl"></div>
              <div className="absolute -bottom-24 -left-16 w-72 h-72 bg-amber-400/20 rounded-full blur-3xl"></div>
            </div>
            <div className="relative">
              <div className="text-3xl mb-2">🎉</div>
              <div className="text-xl text-gray-100 font-bold">Mission Complete!</div>
              <div className="text-sm text-gray-300 mt-1">New challenge arrives tomorrow!</div>
              <button onClick={()=>setRewardOpen(false)} className="mt-4 px-4 py-2 rounded-lg bg-eco-green text-eco-dark font-semibold">Close</button>
            </div>
            {confettiBurst && (
              <div className="absolute inset-0 pointer-events-none animate-ping-slow"></div>
            )}
          </div>
        </div>
      )}

      {/* Simple confetti animation via CSS ping */}
      <style>{`
        .animate-ping-slow { animation: ping 1.2s cubic-bezier(0, 0, 0.2, 1) 3; background: radial-gradient(circle, rgba(16,185,129,0.3) 0%, rgba(0,0,0,0) 60%); }
        @keyframes ping { 75%, 100% { transform: scale(2); opacity: 0; } }
      `}</style>

      {peekUser && (
        <UserProfilePeek username={peekUser} onClose={()=>setPeekUser('')} />
      )}

      <style>{`
        .animate-fade-in-up { opacity: 0; animation: fadeUp 0.55s ease-out forwards; }
        @keyframes fadeUp { 0% { opacity: 0; transform: translateY(14px) } 100% { opacity: 1; transform: translateY(0) } }
      `}</style>
    </div>
  );
};

export default Dashboard;
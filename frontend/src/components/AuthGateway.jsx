// src/components/AuthGateway.jsx

import React, { useMemo, useState } from 'react';
import { Country, State, City } from 'country-state-city';

const Login = ({ onLoginSuccess, onForgot }) => {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [showPassword, setShowPassword] = useState(false);
    const [error, setError] = useState(null);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError(null);

        if (!username.trim() || !password.trim()) {
            setError('Please enter both username and password.');
            return;
        }

        try {
            const res = await fetch('http://localhost:5000/api/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username: username.trim(), password: password.trim() })
            });
            const data = await res.json();
            if (!res.ok) {
                setError(data?.error || 'Login failed.');
                return;
            }
            onLoginSuccess(data.user, data.token);
        } catch {
            setError('Network error. Please try again.');
        }
    };

    return (
        <form className="space-y-4" onSubmit={handleSubmit}>
            <div>
                <label className="block text-sm text-gray-300 mb-1">Username or Email</label>
                <input type="text" placeholder="e.g. eco_hero or user@example.com"
                    value={username}
                    onChange={e => setUsername(e.target.value)}
                    className="w-full px-4 py-3 rounded-xl bg-white/5 border border-white/10 text-gray-100 placeholder:text-gray-400 focus:outline-none focus:border-eco-green focus:ring-2 focus:ring-eco-green/30 transition" />
            </div>
            <div className="relative">
                <label className="block text-sm text-gray-300 mb-1">Password</label>
                <input type={showPassword ? 'text' : 'password'} placeholder="Your password"
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                    className="w-full px-4 py-3 pr-12 rounded-xl bg-white/5 border border-white/10 text-gray-100 placeholder:text-gray-400 focus:outline-none focus:border-eco-green focus:ring-2 focus:ring-eco-green/30 transition" />
                <button type="button" onClick={() => setShowPassword(v => !v)} className="absolute bottom-3 right-3 text-gray-400 hover:text-gray-200">
                    {showPassword ? '🙈' : '👁️'}
                </button>
            </div>
            {error && <div className="text-red-400 text-sm bg-red-500/10 border border-red-500/30 rounded-lg p-2">{error}</div>}
            <button type="submit" className="w-full py-3 bg-eco-green text-white font-semibold rounded-xl hover:brightness-110 transition duration-300 shadow-[0_8px_30px_rgba(16,185,129,0.25)]">
                Log In
            </button>
            <div className="text-right">
                <button type="button" onClick={onForgot} className="text-xs text-gray-300 hover:text-gray-100 underline">Forgot password?</button>
            </div>
        </form>
    );
};


// Lightweight auto-suggest input for locations
const AutoSuggestInput = ({ label, placeholder, value, onChange, onSelect, suggestions, inputProps = {} }) => {
    const [open, setOpen] = useState(false);
    const filtered = useMemo(() => {
        const q = (value || '').toLowerCase();
        if (q.length < 2) return [];
        return suggestions
            .filter((s) => s.toLowerCase().startsWith(q))
            .slice(0, 10);
    }, [value, suggestions]);

    return (
        <div className="relative">
            <label className="block text-sm text-gray-300 mb-1">{label}</label>
            <input
                type="text"
                placeholder={placeholder}
                value={value}
                onChange={(e) => { onChange(e.target.value); setOpen(true); }}
                onFocus={() => setOpen(true)}
                onBlur={() => setTimeout(() => setOpen(false), 120)}
                className="w-full px-4 py-3 rounded-xl bg-white/5 border border-white/10 text-gray-100 placeholder:text-gray-400 focus:outline-none focus:border-eco-green focus:ring-2 focus:ring-eco-green/30 transition"
                {...inputProps}
            />
            {open && filtered.length > 0 && (
                <div className="absolute z-20 mt-1 w-full max-h-56 overflow-auto rounded-lg bg-[#0f172a]/95 border border-white/10 shadow-2xl">
                    {filtered.map((s, idx) => (
                        <button
                            key={idx}
                            type="button"
                            onMouseDown={(e) => e.preventDefault()}
                            onClick={() => { (onSelect ? onSelect(s) : onChange(s)); setOpen(false); }}
                            className="w-full text-left px-3 py-2 text-sm text-gray-200 hover:bg-white/10"
                        >
                            {s}
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
};

const DISTRICT_SUGGESTIONS = [
    'Pune', 'Mumbai Suburban', 'Bengaluru Urban', 'Delhi', 'Chennai', 'Hyderabad', 'Kolkata', 'Ahmedabad', 'Jaipur', 'Thane', 'Nagpur'
];

const ForgotPassword = ({ onBackToLogin }) => {
    const [step, setStep] = useState('request');
    const [email, setEmail] = useState('');
    const [otp, setOtp] = useState('');
    const [newPassword, setNewPassword] = useState('');
    const [showPassword, setShowPassword] = useState(false);
    const [message, setMessage] = useState('');
    const [error, setError] = useState('');

    const requestOtp = async (e) => {
        e.preventDefault();
        setError(''); setMessage('');
        const emailVal = email.trim();
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(emailVal)) {
            setError('Please enter a valid email address.');
            return;
        }
        try {
            const res = await fetch('http://localhost:5000/api/request_password_reset', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: emailVal })
            });
            const data = await res.json();
            if (!res.ok) { setError(data?.error || 'Failed to send OTP.'); return; }
            setMessage('We sent an OTP to your email. Enter it below to reset your password.');
            setStep('reset');
        } catch {
            setError('Network error. Please try again.');
        }
    };

    const submitReset = async (e) => {
        e.preventDefault();
        setError(''); setMessage('');
        if (!otp.trim() || !newPassword.trim()) { setError('Enter OTP and new password.'); return; }
        try {
            const res = await fetch('http://localhost:5000/api/reset_password', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: email.trim(), otp: otp.trim(), new_password: newPassword.trim() })
            });
            const data = await res.json();
            if (!res.ok) { setError(data?.error || 'Password reset failed.'); return; }
            setMessage('Password reset successful. You can now log in.');
            setTimeout(onBackToLogin, 800);
        } catch {
            setError('Network error. Please try again.');
        }
    };

    return (
        <div className="space-y-4">
            {step === 'request' ? (
                <form onSubmit={requestOtp} className="space-y-4">
                    <div>
                        <label className="block text-sm text-gray-300 mb-1">Email</label>
                        <input type="email" placeholder="you@example.com" value={email} onChange={(e)=>setEmail(e.target.value)}
                               className="w-full px-4 py-3 rounded-xl bg-white/5 border border-white/10 text-gray-100 placeholder:text-gray-400 focus:outline-none focus:border-eco-green focus:ring-2 focus:ring-eco-green/30 transition" />
                    </div>
                    {error && <div className="text-red-400 text-sm bg-red-500/10 border border-red-500/30 rounded-lg p-2">{error}</div>}
                    {message && <div className="text-green-300 text-sm bg-emerald-500/10 border border-emerald-500/30 rounded-lg p-2">{message}</div>}
                    <button type="submit" className="w-full py-3 bg-eco-green text-white font-semibold rounded-xl hover:brightness-110 transition">Send OTP</button>
                    <button type="button" onClick={onBackToLogin} className="w-full py-2 text-xs text-gray-300 hover:text-gray-100 underline">Back to Login</button>
                </form>
            ) : (
                <form onSubmit={submitReset} className="space-y-4">
                    <div>
                        <label className="block text-sm text-gray-300 mb-1">Email</label>
                        <input type="email" value={email} disabled
                               className="w-full px-4 py-3 rounded-xl bg-white/5 border border-white/10 text-gray-400" />
                    </div>
                    <div>
                        <label className="block text-sm text-gray-300 mb-1">OTP</label>
                        <input type="text" placeholder="6-digit code" value={otp} onChange={(e)=>setOtp(e.target.value)}
                               className="w-full px-4 py-3 rounded-xl bg-white/5 border border-white/10 text-gray-100 placeholder:text-gray-400 focus:outline-none focus:border-eco-accent focus:ring-2 focus:ring-eco-accent/30 transition" />
                    </div>
                    <div className="relative">
                        <label className="block text-sm text-gray-300 mb-1">New Password</label>
                        <input type={showPassword ? 'text' : 'password'} placeholder="Create a new password" value={newPassword} onChange={(e)=>setNewPassword(e.target.value)}
                               className="w-full px-4 py-3 pr-12 rounded-xl bg-white/5 border border-white/10 text-gray-100 placeholder:text-gray-400 focus:outline-none focus:border-eco-green focus:ring-2 focus:ring-eco-green/30 transition" />
                        <button type="button" onClick={()=>setShowPassword(v=>!v)} className="absolute bottom-3 right-3 text-gray-400 hover:text-gray-200">{showPassword ? '🙈' : '👁️'}</button>
                    </div>
                    {error && <div className="text-red-400 text-sm bg-red-500/10 border border-red-500/30 rounded-lg p-2">{error}</div>}
                    {message && <div className="text-green-300 text-sm bg-emerald-500/10 border border-emerald-500/30 rounded-lg p-2">{message}</div>}
                    <button type="submit" className="w-full py-3 bg-eco-accent text-eco-dark font-semibold rounded-xl hover:brightness-110 transition">Reset Password</button>
                    <button type="button" onClick={onBackToLogin} className="w-full py-2 text-xs text-gray-300 hover:text-gray-100 underline">Back to Login</button>
                </form>
            )}
        </div>
    );
};

const Signup = ({ onSignupSuccess }) => {
    const [username, setUsername] = useState('');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [country, setCountry] = useState('');
    const [region, setRegion] = useState(''); // state/province name
    const [city, setCity] = useState('');
    const [district, setDistrict] = useState('');
    const [selectedCountry, setSelectedCountry] = useState(null);
    const [selectedStateObj, setSelectedStateObj] = useState(null);
    const [showPassword, setShowPassword] = useState(false);
    const [showConfirmPassword, setShowConfirmPassword] = useState(false);
    const [error, setError] = useState(null);

    // Dynamic suggestions from country-state-city
    const allCountries = useMemo(() => Country.getAllCountries(), []);
    const countryNames = useMemo(() => allCountries.map(c => c.name), [allCountries]);
    const countryByName = useMemo(() => {
        const map = Object.create(null);
        for (const c of allCountries) map[c.name] = c;
        return map;
    }, [allCountries]);

    const statesForCountry = useMemo(() => {
        if (!selectedCountry) return [];
        return State.getStatesOfCountry(selectedCountry.isoCode);
    }, [selectedCountry]);
    const stateNames = useMemo(() => statesForCountry.map(s => s.name), [statesForCountry]);
    const stateByName = useMemo(() => {
        const map = Object.create(null);
        for (const s of statesForCountry) map[s.name] = s;
        return map;
    }, [statesForCountry]);

    const citiesForState = useMemo(() => {
        if (!selectedCountry || !selectedStateObj) return [];
        return City.getCitiesOfState(selectedCountry.isoCode, selectedStateObj.isoCode);
    }, [selectedCountry, selectedStateObj]);
    const cityNames = useMemo(() => citiesForState.map(c => c.name), [citiesForState]);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError(null);

        if (!username.trim() || !email.trim() || !password.trim() || !confirmPassword.trim() || !country.trim() || !region.trim() || !city.trim() || !district.trim()) {
            setError('Please fill all fields.');
            return;
        }
        // Minimal email validation
        const emailVal = email.trim();
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(emailVal)) {
            setError('Please enter a valid email address.');
            return;
        }
        if (password !== confirmPassword) {
            setError('Passwords do not match.');
            return;
        }

        try {
            const res = await fetch('http://localhost:5000/api/signup', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    username: username.trim(),
                    email: emailVal,
                    password: password.trim(),
                    country: country.trim(),
                    state: region.trim(),
                    city: city.trim(),
                    district: district.trim()
                })
            });
            const data = await res.json();
            if (!res.ok) {
                setError(data?.error || 'Signup failed.');
                return;
            }
            onSignupSuccess();
        } catch {
            setError('Network error. Please try again.');
        }
    };

    return (
        <form className="space-y-4" onSubmit={handleSubmit}>
            <div>
                <label className="block text-sm text-gray-300 mb-1">Choose Username</label>
                <input type="text" placeholder="e.g. green_ninja"
                    value={username}
                    onChange={e => setUsername(e.target.value)}
                    className="w-full px-4 py-3 rounded-xl bg-white/5 border border-white/10 text-gray-100 placeholder:text-gray-400 focus:outline-none focus:border-eco-green focus:ring-2 focus:ring-eco-green/30 transition" />
            </div>
            <div>
                <label className="block text-sm text-gray-300 mb-1">Email</label>
                <input type="email" placeholder="you@example.com"
                    value={email}
                    onChange={e => setEmail(e.target.value)}
                    className="w-full px-4 py-3 rounded-xl bg-white/5 border border-white/10 text-gray-100 placeholder:text-gray-400 focus:outline-none focus:border-eco-accent focus:ring-2 focus:ring-eco-accent/30 transition" />
            </div>
            <div className="relative">
                <label className="block text-sm text-gray-300 mb-1">Password</label>
                <input type={showPassword ? 'text' : 'password'} placeholder="Create a strong password"
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                    className="w-full px-4 py-3 pr-12 rounded-xl bg-white/5 border border-white/10 text-gray-100 placeholder:text-gray-400 focus:outline-none focus:border-eco-green focus:ring-2 focus:ring-eco-green/30 transition" />
                <button type="button" onClick={() => setShowPassword(v => !v)} className="absolute bottom-3 right-3 text-gray-400 hover:text-gray-200">
                    {showPassword ? '🙈' : '👁️'}
                </button>
            </div>
            <div className="relative">
                <label className="block text-sm text-gray-300 mb-1">Confirm Password</label>
                <input type={showConfirmPassword ? 'text' : 'password'} placeholder="Re-enter password"
                    value={confirmPassword}
                    onChange={e => setConfirmPassword(e.target.value)}
                    className="w-full px-4 py-3 pr-12 rounded-xl bg-white/5 border border-white/10 text-gray-100 placeholder:text-gray-400 focus:outline-none focus:border-eco-green focus:ring-2 focus:ring-eco-green/30 transition" />
                <button type="button" onClick={() => setShowConfirmPassword(v => !v)} className="absolute bottom-3 right-3 text-gray-400 hover:text-gray-200">
                    {showConfirmPassword ? '🙈' : '👁️'}
                </button>
            </div>
            <AutoSuggestInput 
                label="Country" 
                placeholder="Country name" 
                value={country} 
                onChange={(val) => { 
                    setCountry(val); 
                    setSelectedCountry(null); 
                    setRegion('');
                    setSelectedStateObj(null);
                    setCity('');
                }} 
                onSelect={(name) => { 
                    setCountry(name); 
                    const c = countryByName[name] || null; 
                    setSelectedCountry(c);
                    setRegion('');
                    setSelectedStateObj(null);
                    setCity('');
                }}
                suggestions={countryNames} 
            />
            <AutoSuggestInput 
                label="State/Province" 
                placeholder="State name" 
                value={region} 
                onChange={(val) => { 
                    setRegion(val);
                    setSelectedStateObj(null);
                    setCity('');
                }} 
                onSelect={(name) => { 
                    setRegion(name); 
                    const s = stateByName[name] || null; 
                    setSelectedStateObj(s);
                    setCity('');
                }}
                suggestions={stateNames} 
                inputProps={{ disabled: !selectedCountry }}
            />
            <AutoSuggestInput 
                label="District" 
                placeholder="District name" 
                value={district} 
                onChange={setDistrict} 
                suggestions={DISTRICT_SUGGESTIONS}
                inputProps={{ disabled: !selectedStateObj }}
            />
            <AutoSuggestInput 
                label="City/Village" 
                placeholder="City or Village" 
                value={city} 
                onChange={setCity} 
                suggestions={cityNames} 
                inputProps={{ disabled: !selectedStateObj }}
            />
            {error && <div className="text-red-400 text-sm bg-red-500/10 border border-red-500/30 rounded-lg p-2">{error}</div>}
            <button type="submit" className="w-full py-3 bg-eco-accent text-eco-dark font-semibold rounded-xl hover:brightness-110 transition duration-300 shadow-[0_8px_30px_rgba(245,158,11,0.25)]">
                Create Account
            </button>
        </form>
    );
};


const AuthGateway = ({ onAuthSuccess }) => {
    const [authMode, setAuthMode] = useState('login'); 
    const [authMessage, setAuthMessage] = useState('');

    const handleLoginSuccess = (userData, token) => {
        onAuthSuccess(userData, token);
    };

    const handleSignupSuccess = () => {
        setAuthMessage('Account created. Log in now.');
        setAuthMode('login');
    };

    return (
        <div className="min-h-screen relative flex items-center justify-center bg-black px-4 overflow-hidden">
            {/* Tailwind-based background design */}
            <div className="pointer-events-none absolute inset-0">
                {/* dotted grid */}
                <div className="absolute inset-0 opacity-[0.06]" style={{ backgroundImage: 'radial-gradient(rgba(255,255,255,0.28) 1px, transparent 1px)', backgroundSize: '22px 22px' }} />
                {/* soft gradient glows */}
                <div className="absolute -top-40 -left-40 w-[40rem] h-[40rem] bg-emerald-500/25 blur-3xl rounded-full" />
                <div className="absolute -bottom-48 -right-40 w-[42rem] h-[42rem] bg-amber-400/25 blur-3xl rounded-full" />
                {/* conic beam */}
                <div className="absolute left-1/2 -translate-x-1/2 top-0 w-[60rem] h-[60rem] opacity-20" style={{ background: 'conic-gradient(from 180deg at 50% 50%, rgba(16,185,129,0.25), transparent 40%, rgba(245,158,11,0.25))' }} />
            </div>

            <div className="relative z-10 w-full max-w-md">
                <div className="mb-6 text-center">
                    <div className="inline-flex items-center space-x-3">
                        <img src="/swachh-bharat.svg" alt="Swachh Bharat" className="h-6 w-auto opacity-90" />
                        <span className="text-gray-100 font-extrabold text-2xl">Waste</span>
                        <span className="text-eco-green font-extrabold text-2xl">Rewards</span>
                    </div>
                </div>

                {/* Opaque auth card */}
                <div className="rounded-2xl bg-[#0f172a]/95 border border-white/10 p-6 shadow-2xl">
                    <div className="flex justify-center mb-6 border-b border-white/10">
                        <button 
                            onClick={() => setAuthMode('login')}
                            className={`px-4 py-2 font-semibold transition-colors ${authMode === 'login' ? 'text-eco-green border-b-4 border-eco-green' : 'text-gray-400 hover:text-gray-200'}`}
                        >
                            LOG IN
                        </button>
                        <button 
                            onClick={() => setAuthMode('signup')}
                            className={`px-4 py-2 font-semibold transition-colors ${authMode === 'signup' ? 'text-eco-accent border-b-4 border-eco-accent' : 'text-gray-400 hover:text-gray-200'}`}
                        >
                            SIGN UP
                        </button>
                    </div>

                    {authMessage && (
                        <div className="mb-4 text-center text-sm text-green-300 bg-emerald-500/10 border border-emerald-500/20 rounded p-2">
                            {authMessage}
                        </div>
                    )}

                    <div key={authMode} className="opacity-0 animate-fade-in-up">
                        {authMode === 'login' && (
                            <Login onLoginSuccess={handleLoginSuccess} onForgot={() => setAuthMode('forgot')} />
                        )}
                        {authMode === 'signup' && (
                            <Signup onSignupSuccess={handleSignupSuccess} />
                        )}
                        {authMode === 'forgot' && (
                            <ForgotPassword onBackToLogin={() => setAuthMode('login')} />
                        )}
                    </div>
                </div>

                <div className="text-center text-xs text-gray-300 mt-6">
                    By continuing, you agree to our <span className="text-gray-100">Terms</span> and <span className="text-gray-100">Privacy Policy</span>.
                </div>
            </div>

            <style>{`
                .animate-fade-in-up { opacity: 0; animation: fadeInUp 0.6s ease-out forwards; }
                @keyframes fadeInUp { 0% { opacity: 0; transform: translateY(14px) } 100% { opacity: 1; transform: translateY(0) } }
            `}</style>
        </div>
    );
};

export default AuthGateway;
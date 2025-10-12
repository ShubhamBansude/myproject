// src/components/AuthGateway.jsx

import React, { useState } from 'react';

const Login = ({ onLoginSuccess }) => {
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
        } catch (err) {
            setError('Network error. Please try again.');
        }
    };

    return (
        <form className="space-y-4" onSubmit={handleSubmit}>
            <div>
                <label className="block text-sm text-gray-300 mb-1">Username</label>
                <input type="text" placeholder="e.g. eco_hero"
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
        </form>
    );
};


const Signup = ({ onSignupSuccess }) => {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [country, setCountry] = useState('');
    const [state, setState] = useState('');
    const [city, setCity] = useState('');
    const [showPassword, setShowPassword] = useState(false);
    const [showConfirmPassword, setShowConfirmPassword] = useState(false);
    const [error, setError] = useState(null);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError(null);

        if (!username.trim() || !password.trim() || !confirmPassword.trim() || !country.trim() || !state.trim() || !city.trim()) {
            setError('Please fill all fields.');
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
                    password: password.trim(),
                    country: country.trim(),
                    state: state.trim(),
                    city: city.trim()
                })
            });
            const data = await res.json();
            if (!res.ok) {
                setError(data?.error || 'Signup failed.');
                return;
            }
            onSignupSuccess();
        } catch (err) {
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
            <div>
                <label className="block text-sm text-gray-300 mb-1">Country</label>
                <input type="text" placeholder="e.g. United States"
                    value={country}
                    onChange={e => setCountry(e.target.value)}
                    className="w-full px-4 py-3 rounded-xl bg-white/5 border border-white/10 text-gray-100 placeholder:text-gray-400 focus:outline-none focus:border-eco-green focus:ring-2 focus:ring-eco-green/30 transition" />
            </div>
            <div>
                <label className="block text-sm text-gray-300 mb-1">State/Province</label>
                <input type="text" placeholder="e.g. California"
                    value={state}
                    onChange={e => setState(e.target.value)}
                    className="w-full px-4 py-3 rounded-xl bg-white/5 border border-white/10 text-gray-100 placeholder:text-gray-400 focus:outline-none focus:border-eco-green focus:ring-2 focus:ring-eco-green/30 transition" />
            </div>
            <div>
                <label className="block text-sm text-gray-300 mb-1">City</label>
                <input type="text" placeholder="e.g. San Francisco"
                    value={city}
                    onChange={e => setCity(e.target.value)}
                    className="w-full px-4 py-3 rounded-xl bg-white/5 border border-white/10 text-gray-100 placeholder:text-gray-400 focus:outline-none focus:border-eco-green focus:ring-2 focus:ring-eco-green/30 transition" />
            </div>
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
                    <div className="inline-flex items-center space-x-2">
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
                        {authMode === 'login' 
                            ? <Login onLoginSuccess={handleLoginSuccess} /> 
                            : <Signup onSignupSuccess={handleSignupSuccess} />
                        }
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
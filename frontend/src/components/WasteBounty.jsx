// src/components/WasteBounty.jsx

import React, { useState, useEffect, lazy, Suspense } from 'react';
const LeaderboardAside = lazy(() => import('./LeaderboardAside'));

// Defer EXIF parsing library to reduce initial bundle size
let EXIFLibPromise;
const loadEXIF = async () => {
  if (!EXIFLibPromise) {
    EXIFLibPromise = import('exif-js');
  }
  return EXIFLibPromise.then(mod => mod.default || mod);
};

const WasteBounty = ({ updatePoints }) => {
    const [activeTab, setActiveTab] = useState('report'); // 'report', 'bounties', 'cleanup'
    const [bounties, setBounties] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [success, setSuccess] = useState(null);
    
    // Report bounty states
    const [reportPhoto, setReportPhoto] = useState(null);
    const [reportPreview, setReportPreview] = useState(null);
    const [reportPhotoSource, setReportPhotoSource] = useState('camera'); // 'camera' or 'gallery'
    const [reportLocation, setReportLocation] = useState(null); // For gallery photos
    
    // Cleanup states
    const [selectedBounty, setSelectedBounty] = useState(null);
    const [beforePhoto, setBeforePhoto] = useState(null);
    const [afterPhoto, setAfterPhoto] = useState(null);
    const [beforePreview, setBeforePreview] = useState(null);
    const [afterPreview, setAfterPreview] = useState(null);
    const [beforePhotoSource, setBeforePhotoSource] = useState('camera');
    const [afterPhotoSource, setAfterPhotoSource] = useState('camera');
    const [beforeLocation, setBeforeLocation] = useState(null);
    const [afterLocation, setAfterLocation] = useState(null);
    const [cleanupStep, _setCleanupStep] = useState('before'); // 'before', 'after', 'submit'
    void cleanupStep; // referenced for lint satisfaction

    // Chat states (per-bounty)
    const [openChatBountyId, setOpenChatBountyId] = useState(null);
    const [chatMessagesByBounty, setChatMessagesByBounty] = useState({}); // { [bountyId]: [{id, sender_username, message, created_at}] }
    const [chatInputByBounty, setChatInputByBounty] = useState({}); // { [bountyId]: string }
    const [chatLoadingByBounty, setChatLoadingByBounty] = useState({}); // { [bountyId]: boolean }

    // Load bounties on component mount
    useEffect(() => {
        if (activeTab === 'bounties') {
            loadBounties();
        }
    }, [activeTab]);

    const loadBounties = async () => {
        setLoading(true);
        setError(null);
        
        try {
            const token = localStorage.getItem('authToken');
            const res = await fetch('http://localhost:5000/api/bounties', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            
            const data = await res.json();
            if (!res.ok) {
                setError(data?.error || 'Failed to load bounties');
                return;
            }
            
            setBounties(data.bounties || []);
        } catch {
            setError('Network error. Please try again.');
        } finally {
            setLoading(false);
        }
    };

    const getCurrentLocation = () => {
        return new Promise((resolve, reject) => {
            if (!navigator.geolocation) {
                reject(new Error('Geolocation is not supported by this browser'));
                return;
            }
            
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    resolve({
                        latitude: position.coords.latitude,
                        longitude: position.coords.longitude
                    });
                },
                (error) => {
                    reject(new Error('Unable to get current location: ' + error.message));
                },
                {
                    enableHighAccuracy: true,
                    timeout: 10000,
                    maximumAge: 300000 // 5 minutes
                }
            );
        });
    };

    const validateGeotag = (file, photoSource = 'camera') => {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = async (e) => {
                const img = new Image();
                img.onload = async () => {
                    try {
                        const EXIF = await loadEXIF();
                        EXIF.getData(img, function() {
                            const lat = EXIF.getTag(this, "GPSLatitude");
                            const latRef = EXIF.getTag(this, "GPSLatitudeRef");
                            const lon = EXIF.getTag(this, "GPSLongitude");
                            const lonRef = EXIF.getTag(this, "GPSLongitudeRef");
                            
                            if (lat && latRef && lon && lonRef) {
                                resolve({ hasGPS: true, file: file });
                            } else if (photoSource === 'gallery') {
                                getCurrentLocation()
                                    .then((location) => {
                                        resolve({ hasGPS: false, file: file, location: location });
                                    })
                                    .catch(() => {
                                        resolve({ hasGPS: false, file: file });
                                    });
                            } else {
                                reject(new Error('📸 Camera photo must have GPS data. Please enable location services and take a new photo, or choose from gallery instead.'));
                            }
                        });
                    } catch (ex) {
                        console.warn('EXIF parse failed:', ex);
                        resolve({ hasGPS: false, file: file });
                    }
                };
                img.src = e.target.result;
            };
            reader.onerror = () => reject(new Error('Failed to read file'));
            reader.readAsDataURL(file);
        });
    };

    const handleReportPhotoChange = async (event) => {
        const file = event.target.files[0];
        if (!file) return;

        try {
            const result = await validateGeotag(file, reportPhotoSource);
            setReportPhoto(result.file);
            setReportPreview(URL.createObjectURL(result.file));
            setError(null);
            
            if (!result.hasGPS) {
                setReportLocation(result.location);
                setSuccess('✅ Gallery photo selected! Current location has been added as GPS data.');
            } else {
                setReportLocation(null);
            }
        } catch (err) {
            setError(err?.message || 'Failed to process image. Try again.');
            setReportPhoto(null);
            setReportPreview(null);
            setReportLocation(null);
        }
    };

    const handleReportPhotoSourceChange = (source) => {
        setReportPhotoSource(source);
        setReportPhoto(null);
        setReportPreview(null);
        setReportLocation(null);
        setError(null);
    };

    const handleBeforePhotoChange = async (event) => {
        const file = event.target.files[0];
        if (!file) return;

        try {
            const result = await validateGeotag(file, beforePhotoSource);
            setBeforePhoto(result.file);
            setBeforePreview(URL.createObjectURL(result.file));
            setError(null);
            
            if (!result.hasGPS) {
                setBeforeLocation(result.location);
                setSuccess('✅ Gallery photo selected! Current location has been added as GPS data.');
            }
        } catch (err) {
            setError(err?.message || 'Failed to process image. Try again.');
            setBeforePhoto(null);
            setBeforePreview(null);
        }
    };

    const handleBeforePhotoSourceChange = (source) => {
        setBeforePhotoSource(source);
        setBeforePhoto(null);
        setBeforePreview(null);
        setBeforeLocation(null);
        setError(null);
    };

    const handleAfterPhotoChange = async (event) => {
        const file = event.target.files[0];
        if (!file) return;

        try {
            const result = await validateGeotag(file, afterPhotoSource);
            setAfterPhoto(result.file);
            setAfterPreview(URL.createObjectURL(result.file));
            setError(null);
            
            if (!result.hasGPS) {
                setAfterLocation(result.location);
                setSuccess('✅ Gallery photo selected! Current location has been added as GPS data.');
            }
        } catch (err) {
            setError(err?.message || 'Failed to process image. Try again.');
            setAfterPhoto(null);
            setAfterPreview(null);
        }
    };

    const handleAfterPhotoSourceChange = (source) => {
        setAfterPhotoSource(source);
        setAfterPhoto(null);
        setAfterPreview(null);
        setAfterLocation(null);
        setError(null);
    };

    const submitBountyReport = async () => {
        if (!reportPhoto) {
            setError('Please take a photo first');
            return;
        }

        setLoading(true);
        setError(null);
        setSuccess(null);

        try {
            const token = localStorage.getItem('authToken');
            if (!token) {
                setError('Please login first');
                setLoading(false);
                return;
            }

            const formData = new FormData();
            formData.append('bounty_report_photo', reportPhoto);
            
            // Add location data for gallery photos
            if (reportLocation) {
                formData.append('latitude', reportLocation.latitude.toString());
                formData.append('longitude', reportLocation.longitude.toString());
                if (reportLocation.city) {
                    formData.append('city', reportLocation.city);
                }
                if (reportLocation.state) {
                    formData.append('state', reportLocation.state);
                }
                console.log('Adding location data for gallery photo:', reportLocation);
            }

            console.log('Submitting bounty with photo:', reportPhoto.name, 'Size:', reportPhoto.size);

            const res = await fetch('http://localhost:5000/api/create_bounty', {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` },
                body: formData
            });

            console.log('Response status:', res.status);
            const data = await res.json();
            console.log('Response data:', data);

            if (!res.ok) {
                setError(data?.error || 'Failed to create bounty');
                return;
            }

            setSuccess('Bounty created successfully! Other users in your area can now claim it.');
            setReportPhoto(null);
            setReportPreview(null);
            setReportLocation(null);
            setReportPhotoSource('camera'); // Reset to camera
        } catch (e) {
            console.error('Bounty creation error:', e);
            setError('Network error. Please try again.');
        } finally {
            setLoading(false);
        }
    };

    const claimBounty = (bounty) => {
        setSelectedBounty(bounty);
        setActiveTab('cleanup');
        _setCleanupStep('before');
    };

    const toggleChat = async (bountyId) => {
        if (openChatBountyId === bountyId) {
            setOpenChatBountyId(null);
            return;
        }
        setOpenChatBountyId(bountyId);
        if (!chatMessagesByBounty[bountyId]) {
            await loadChatMessages(bountyId);
        }
    };

    const loadChatMessages = async (bountyId) => {
        const token = localStorage.getItem('authToken');
        setChatLoadingByBounty((m) => ({ ...m, [bountyId]: true }));
        try {
            const res = await fetch(`http://localhost:5000/api/bounty_chat?bounty_id=${encodeURIComponent(bountyId)}`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            const data = await res.json();
            if (!res.ok) {
                setError(data?.error || 'Failed to load chat');
                return;
            }
            setChatMessagesByBounty((prev) => ({ ...prev, [bountyId]: data.messages || [] }));
        } catch (e) {
            setError('Failed to load chat');
        } finally {
            setChatLoadingByBounty((m) => ({ ...m, [bountyId]: false }));
        }
    };

    const sendChatMessage = async (bountyId) => {
        const token = localStorage.getItem('authToken');
        const text = (chatInputByBounty[bountyId] || '').trim();
        if (!text) return;
        setChatLoadingByBounty((m) => ({ ...m, [bountyId]: true }));
        try {
            const res = await fetch('http://localhost:5000/api/bounty_chat', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ bounty_id: bountyId, message: text })
            });
            const data = await res.json();
            if (!res.ok) {
                setError(data?.error || 'Failed to send message');
                return;
            }
            setChatMessagesByBounty((prev) => ({
                ...prev,
                [bountyId]: [ ...(prev[bountyId] || []), data.message ]
            }));
            setChatInputByBounty((prev) => ({ ...prev, [bountyId]: '' }));
        } catch (e) {
            setError('Failed to send message');
        } finally {
            setChatLoadingByBounty((m) => ({ ...m, [bountyId]: false }));
        }
    };

    const deleteChatMessage = async (bountyId, messageId) => {
        const token = localStorage.getItem('authToken');
        try {
            const res = await fetch(`http://localhost:5000/api/bounty_chat/${messageId}`, {
                method: 'DELETE',
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                setError(data?.error || 'Failed to delete message');
                return;
            }
            setChatMessagesByBounty((prev) => ({
                ...prev,
                [bountyId]: (prev[bountyId] || []).filter((m) => m.id !== messageId)
            }));
        } catch (e) {
            setError('Failed to delete message');
        }
    };

    const submitCleanup = async () => {
        if (!beforePhoto || !afterPhoto) {
            setError('Please take both before and after photos');
            return;
        }

        setLoading(true);
        setError(null);

        try {
            const token = localStorage.getItem('authToken');
            const formData = new FormData();
            formData.append('bounty_id', selectedBounty.id);
            formData.append('before_cleanup_photo', beforePhoto);
            formData.append('after_cleanup_photo', afterPhoto);
            if (beforeLocation) {
                formData.append('before_latitude', String(beforeLocation.latitude));
                formData.append('before_longitude', String(beforeLocation.longitude));
            }
            if (afterLocation) {
                formData.append('after_latitude', String(afterLocation.latitude));
                formData.append('after_longitude', String(afterLocation.longitude));
            }

            const res = await fetch('http://localhost:5000/api/verify_cleanup', {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` },
                body: formData
            });

            const data = await res.json();
            if (!res.ok) {
                setError(data?.error || 'Cleanup verification failed');
                if (data.reasons) {
                    setError(data.reasons.join(', '));
                }
                return;
            }

            setSuccess(`Cleanup verified! You earned ${data.points_awarded} points!`);
            if (typeof data.total_points === 'number') {
                updatePoints(data.total_points);
            }
            
            // Reset cleanup state
            setSelectedBounty(null);
            setBeforePhoto(null);
            setAfterPhoto(null);
            setBeforePreview(null);
            setAfterPreview(null);
            setBeforeLocation(null);
            setAfterLocation(null);
            _setCleanupStep('before');
            setActiveTab('bounties');
            loadBounties(); // Refresh bounties list
        } catch {
            setError('Network error. Please try again.');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <h2 className="text-2xl font-bold text-gray-100">🗺️ Waste Bounty System</h2>
                <div className="text-sm text-gray-400">
                    Earn points by cleaning up reported waste spots
                </div>
            </div>

            {/* Tab Navigation */}
            <div className="flex space-x-1 bg-white/5 p-1 rounded-lg">
                <button
                    onClick={() => setActiveTab('report')}
                    className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-colors ${
                        activeTab === 'report'
                            ? 'bg-eco-green text-white'
                            : 'text-gray-400 hover:text-gray-200'
                    }`}
                >
                    📸 Report Waste
                </button>
                <button
                    onClick={() => setActiveTab('bounties')}
                    className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-colors ${
                        activeTab === 'bounties'
                            ? 'bg-eco-green text-white'
                            : 'text-gray-400 hover:text-gray-200'
                    }`}
                >
                    🎯 Active Bounties
                </button>
                {selectedBounty && (
                    <button
                        onClick={() => setActiveTab('cleanup')}
                        className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-colors ${
                            activeTab === 'cleanup'
                                ? 'bg-eco-accent text-eco-dark'
                                : 'text-gray-400 hover:text-gray-200'
                        }`}
                    >
                        🧹 Cleanup
                    </button>
                )}
            </div>

            {/* Error/Success Messages */}
            {error && (
                <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-lg text-red-300">
                    {error}
                </div>
            )}
            {success && (
                <div className="p-4 bg-green-500/10 border border-green-500/20 rounded-lg text-green-300">
                    {success}
                </div>
            )}

            {/* Report Waste Tab */}
            {activeTab === 'report' && (
                <div className="grid gap-6 lg:grid-cols-3">
                    <div className="bg-white/5 border border-white/10 rounded-xl p-6">
                        <h3 className="text-lg font-semibold text-gray-100 mb-4">Report a Public Waste Spot</h3>
                        <p className="text-gray-400 text-sm mb-4">
                            Take a photo of any waste in public areas - streets, parks, rivers, canals, markets, or any polluted location. The photo must contain GPS location data.
                        </p>
                        <div className="bg-blue-500/10 border border-blue-500/20 rounded-lg p-3 mb-4">
                            <p className="text-blue-300 text-sm">
                                <strong>Supported locations:</strong> Rivers, canals, lakes, parks, streets, markets, construction sites, industrial areas, and any public space with visible waste or pollution.
                            </p>
                        </div>
                        
                        <div className="bg-green-500/10 border border-green-500/20 rounded-lg p-3 mb-4">
                            <p className="text-green-300 text-sm">
                                <strong>💡 Pro Tip:</strong> Use <strong>Camera</strong> for new photos with GPS, or <strong>Gallery</strong> for existing photos (GPS will be added automatically).
                            </p>
                        </div>
                        
                        {/* Manual Location Input for Better City Detection */}
                        <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-lg p-3 mb-4">
                            <p className="text-yellow-300 text-sm mb-2">
                                <strong>📍 Location:</strong> If city is not detected automatically, please specify:
                            </p>
                            <div className="flex space-x-2">
                                <input
                                    type="text"
                                    placeholder="City (e.g., Baramati, Pune, Mumbai)"
                                    value={reportLocation?.city || ''}
                                    onChange={(e) => {
                                        if (reportLocation) {
                                            setReportLocation({...reportLocation, city: e.target.value});
                                        }
                                    }}
                                    className="flex-1 px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-400 text-sm"
                                />
                                <input
                                    type="text"
                                    placeholder="State (e.g., Maharashtra)"
                                    value={reportLocation?.state || ''}
                                    onChange={(e) => {
                                        if (reportLocation) {
                                            setReportLocation({...reportLocation, state: e.target.value});
                                        }
                                    }}
                                    className="flex-1 px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-400 text-sm"
                                />
                            </div>
                        </div>
                        
                        <div className="space-y-4">
                            {/* Photo Source Selection */}
                            <div className="flex space-x-2 mb-4">
                                <button
                                    onClick={() => handleReportPhotoSourceChange('camera')}
                                    className={`flex-1 py-2 px-4 rounded-lg text-sm font-medium transition-colors ${
                                        reportPhotoSource === 'camera'
                                            ? 'bg-eco-green text-white'
                                            : 'bg-white/10 text-gray-300 hover:bg-white/20'
                                    }`}
                                >
                                    📸 Camera
                                </button>
                                <button
                                    onClick={() => handleReportPhotoSourceChange('gallery')}
                                    className={`flex-1 py-2 px-4 rounded-lg text-sm font-medium transition-colors ${
                                        reportPhotoSource === 'gallery'
                                            ? 'bg-eco-green text-white'
                                            : 'bg-white/10 text-gray-300 hover:bg-white/20'
                                    }`}
                                >
                                    🖼️ Gallery
                                </button>
                            </div>

                            <div className="border-2 border-dashed border-white/20 bg-white/5 rounded-lg p-8 text-center">
                                <input
                                    type="file"
                                    accept="image/*"
                                    capture={reportPhotoSource === 'camera' ? 'environment' : undefined}
                                    onChange={handleReportPhotoChange}
                                    className="hidden"
                                    id="report-photo-upload"
                                />
                                <label htmlFor="report-photo-upload" className="cursor-pointer">
                                    <div className="text-4xl mb-2">
                                        {reportPhotoSource === 'camera' ? '📸' : '🖼️'}
                                    </div>
                                    <p className="text-gray-300 font-medium">
                                        {reportPhotoSource === 'camera' ? 'Take Photo with Camera' : 'Choose from Gallery'}
                                    </p>
                                    <p className="text-sm text-gray-400 mt-1">
                                        {reportPhotoSource === 'camera' ? 'GPS location required' : 'GPS will be added automatically if missing'}
                                    </p>
                                    {reportPhoto && (
                                        <p className="text-sm text-eco-green mt-2 font-semibold">
                                            Photo selected: {reportPhoto.name}
                                        </p>
                                    )}
                                </label>
                            </div>

                            {reportPreview && (
                                <div className="space-y-2">
                                    <p className="text-sm text-gray-300">Preview:</p>
                                    <img
                                        src={reportPreview}
                                        alt="Report preview"
                                        className="w-full max-w-md mx-auto rounded-lg shadow-md"
                                    />
                                </div>
                            )}

                            <button
                                onClick={submitBountyReport}
                                disabled={!reportPhoto || loading}
                                className={`w-full py-3 px-4 rounded-lg font-semibold transition-colors ${
                                    !reportPhoto || loading
                                        ? 'bg-gray-500/40 text-gray-300 cursor-not-allowed'
                                        : 'bg-eco-green text-white hover:brightness-110'
                                }`}
                            >
                                {loading ? 'Creating Bounty...' : 'Create Bounty (+200 pts)'}
                            </button>
                        </div>
                    </div>
                    <div className="lg:col-span-1">
                      <div className="rounded-xl bg-white/5 border border-white/10 p-4">
                        <div className="text-gray-200 font-semibold mb-3">Leaderboard</div>
                        <Suspense fallback={<div className="text-gray-400 text-sm">Loading…</div>}>
                          <LeaderboardAside />
                        </Suspense>
                      </div>
                    </div>
                </div>
            )}

            {/* Active Bounties Tab */}
            {activeTab === 'bounties' && (
                <div className="grid gap-6 lg:grid-cols-3">
                    <div className="flex items-center justify-between">
                        <h3 className="text-lg font-semibold text-gray-100">Available Bounties in Your Area</h3>
                        <button
                            onClick={loadBounties}
                            disabled={loading}
                            className="px-3 py-1 text-sm bg-white/10 text-gray-300 rounded-md hover:bg-white/20 transition-colors"
                        >
                            {loading ? 'Loading...' : 'Refresh'}
                        </button>
                    </div>

                    {bounties.length === 0 ? (
                        <div className="text-center py-8 text-gray-400">
                            <div className="text-4xl mb-2">🎯</div>
                            <p>No active bounties in your area</p>
                            <p className="text-sm mt-1">Be the first to report waste spots!</p>
                        </div>
                    ) : (
                        <div className="grid gap-4 lg:col-span-2 order-2 lg:order-1">
                            {bounties.map((bounty) => (
                                <div key={bounty.id} className="bg-white/5 border border-white/10 rounded-lg p-4">
                                    <div className="flex items-start justify-between">
                                        <div className="flex-1">
                                            <div className="flex items-center gap-2 mb-2">
                                                <span className="text-2xl">🗑️</span>
                                                <div>
                                                    <p className="font-semibold text-gray-100">
                                                        Bounty #{bounty.id}
                                                    </p>
                                                    <p className="text-sm text-gray-400">
                                                        {bounty.city}, {bounty.state}
                                                    </p>
                                                    {bounty.reporter_username && (
                                                        <p className="text-xs text-gray-400 mt-0.5">
                                                            Raised by <span className="text-gray-200 font-medium">@{bounty.reporter_username}</span>
                                                        </p>
                                                    )}
                                                </div>
                                            </div>
                                            <p className="text-sm text-gray-300 mb-2">
                                                Reported: {new Date(bounty.created_at).toLocaleDateString()}
                                            </p>
                                            <div className="flex items-center gap-4 text-sm">
                                                <span className="text-eco-green font-semibold">
                                                    +{bounty.bounty_points} pts
                                                </span>
                                                <span className="text-gray-400">
                                                    📍 {bounty.latitude.toFixed(4)}, {bounty.longitude.toFixed(4)}
                                                </span>
                                            </div>
                                        </div>
                                        <div className="ml-4">
                                            <img
                                                src={`http://localhost:5000${bounty.waste_image_url}`}
                                                alt="Waste spot"
                                                className="w-20 h-20 object-cover rounded-lg"
                                                loading="lazy"
                                                decoding="async"
                                            />
                                        </div>
                                    </div>
                                    {/* Chat toggle */}
                                    <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
                                        <button
                                            onClick={() => claimBounty(bounty)}
                                            className="py-2 bg-eco-accent text-eco-dark font-semibold rounded-lg hover:brightness-110 transition-colors"
                                        >
                                            Claim & Submit Cleanup Photos
                                        </button>
                                        <button
                                            onClick={() => toggleChat(bounty.id)}
                                            className="py-2 bg-white/10 text-gray-200 font-semibold rounded-lg hover:bg-white/20 transition-colors"
                                        >
                                            {openChatBountyId === bounty.id ? 'Hide Chat' : 'Open City Chat'}
                                        </button>
                                    </div>
                                    {openChatBountyId === bounty.id && (
                                        <div className="mt-3 p-3 rounded-lg bg-white/5 border border-white/10">
                                            <div className="flex items-center justify-between mb-2">
                                                <div className="text-sm text-gray-300 font-medium">City Chat</div>
                                                {chatLoadingByBounty[bounty.id] ? (
                                                    <div className="text-xs text-gray-400">Loading…</div>
                                                ) : (
                                                    <button
                                                        onClick={() => loadChatMessages(bounty.id)}
                                                        className="text-xs text-gray-300 hover:text-white"
                                                    >
                                                        Refresh
                                                    </button>
                                                )}
                                            </div>
                                            <div className="max-h-48 overflow-y-auto space-y-2 pr-1">
                                                {(chatMessagesByBounty[bounty.id] || []).map((m) => {
                                                    const canDelete = (currentUser?.username === bounty.reporter_username) || (currentUser?.username === m.sender_username);
                                                    return (
                                                        <div key={m.id} className="flex items-start gap-2">
                                                            <div className="flex-1">
                                                                <div className="text-xs text-gray-400">
                                                                    <span className="text-gray-200 font-semibold">@{m.sender_username}</span>
                                                                    <span className="ml-2 text-[10px] opacity-70">{new Date((m.created_at || '').replace(' ', 'T') + 'Z').toLocaleString()}</span>
                                                                </div>
                                                                <div className="text-sm text-gray-100 whitespace-pre-wrap">{m.message}</div>
                                                            </div>
                                                            {canDelete && (
                                                                <button
                                                                    onClick={() => deleteChatMessage(bounty.id, m.id)}
                                                                    className="text-xs text-red-300 hover:text-red-200"
                                                                    title="Delete message"
                                                                >
                                                                    ✖
                                                                </button>
                                                            )}
                                                        </div>
                                                    );
                                                })}
                                                {(chatMessagesByBounty[bounty.id] || []).length === 0 && !chatLoadingByBounty[bounty.id] && (
                                                    <div className="text-xs text-gray-400">No messages yet. Be the first to say hi!</div>
                                                )}
                                            </div>
                                            <div className="mt-2 flex items-center gap-2">
                                                <input
                                                    type="text"
                                                    value={chatInputByBounty[bounty.id] || ''}
                                                    onChange={(e) => setChatInputByBounty((prev) => ({ ...prev, [bounty.id]: e.target.value }))}
                                                    placeholder="Type a message…"
                                                    className="flex-1 px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-400 text-sm"
                                                />
                                                <button
                                                    onClick={() => sendChatMessage(bounty.id)}
                                                    disabled={chatLoadingByBounty[bounty.id] || !(chatInputByBounty[bounty.id] || '').trim()}
                                                    className={`px-3 py-2 rounded-lg text-sm font-semibold ${
                                                        chatLoadingByBounty[bounty.id] || !(chatInputByBounty[bounty.id] || '').trim()
                                                            ? 'bg-gray-500/40 text-gray-300 cursor-not-allowed'
                                                            : 'bg-eco-green text-eco-dark hover:brightness-110'
                                                    }`}
                                                >
                                                    Send
                                                </button>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    )}
                    <div className="lg:col-span-1 order-1 lg:order-2">
                      <div className="rounded-xl bg-white/5 border border-white/10 p-4">
                        <div className="text-gray-200 font-semibold mb-3">Leaderboard</div>
                        <Suspense fallback={<div className="text-gray-400 text-sm">Loading…</div>}>
                          <LeaderboardAside />
                        </Suspense>
                      </div>
                    </div>
                </div>
            )}

            {/* Cleanup Tab */}
            {activeTab === 'cleanup' && selectedBounty && (
                <div className="space-y-6">
                    <div className="bg-white/5 border border-white/10 rounded-xl p-6">
                        <h3 className="text-lg font-semibold text-gray-100 mb-4">
                            Cleanup: Bounty #{selectedBounty.id}
                        </h3>
                        <p className="text-gray-400 text-sm mb-4">
                            Take two photos: one before cleanup and one after. Both must contain GPS location data.
                        </p>

                        <div className="space-y-6">
                            {/* Before Cleanup Photo */}
                            <div className="space-y-3">
                                <h4 className="font-medium text-gray-200 flex items-center gap-2">
                                    <span className="text-2xl">📷</span>
                                    Before Cleanup Photo
                                </h4>
                                
                                {/* Photo Source Selection */}
                                <div className="flex space-x-2">
                                    <button
                                        onClick={() => handleBeforePhotoSourceChange('camera')}
                                        className={`flex-1 py-2 px-3 rounded-lg text-sm font-medium transition-colors ${
                                            beforePhotoSource === 'camera'
                                                ? 'bg-eco-accent text-eco-dark'
                                                : 'bg-white/10 text-gray-300 hover:bg-white/20'
                                        }`}
                                    >
                                        📸 Camera
                                    </button>
                                    <button
                                        onClick={() => handleBeforePhotoSourceChange('gallery')}
                                        className={`flex-1 py-2 px-3 rounded-lg text-sm font-medium transition-colors ${
                                            beforePhotoSource === 'gallery'
                                                ? 'bg-eco-accent text-eco-dark'
                                                : 'bg-white/10 text-gray-300 hover:bg-white/20'
                                        }`}
                                    >
                                        🖼️ Gallery
                                    </button>
                                </div>

                                <div className="border-2 border-dashed border-white/20 bg-white/5 rounded-lg p-6 text-center">
                                    <input
                                        type="file"
                                        accept="image/*"
                                        capture={beforePhotoSource === 'camera' ? 'environment' : undefined}
                                        onChange={handleBeforePhotoChange}
                                        className="hidden"
                                        id="before-photo-upload"
                                    />
                                    <label htmlFor="before-photo-upload" className="cursor-pointer">
                                        <div className="text-3xl mb-2">
                                            {beforePhotoSource === 'camera' ? '📸' : '🖼️'}
                                        </div>
                                        <p className="text-gray-300 font-medium">
                                            {beforePhotoSource === 'camera' ? 'Take Before Photo' : 'Choose Before Photo'}
                                        </p>
                                        <p className="text-sm text-gray-400 mt-1">
                                            {beforePhotoSource === 'camera' ? 'Show the waste before cleaning' : 'GPS will be added automatically if missing'}
                                        </p>
                                        {beforePhoto && (
                                            <p className="text-sm text-eco-green mt-2 font-semibold">
                                                Photo selected: {beforePhoto.name}
                                            </p>
                                        )}
                                    </label>
                                </div>
                                {beforePreview && (
                                    <img
                                        src={beforePreview}
                                        alt="Before cleanup"
                                        className="w-full max-w-md mx-auto rounded-lg shadow-md"
                                    />
                                )}
                            </div>

                            {/* After Cleanup Photo */}
                            <div className="space-y-3">
                                <h4 className="font-medium text-gray-200 flex items-center gap-2">
                                    <span className="text-2xl">✅</span>
                                    After Cleanup Photo
                                </h4>
                                
                                {/* Photo Source Selection */}
                                <div className="flex space-x-2">
                                    <button
                                        onClick={() => handleAfterPhotoSourceChange('camera')}
                                        className={`flex-1 py-2 px-3 rounded-lg text-sm font-medium transition-colors ${
                                            afterPhotoSource === 'camera'
                                                ? 'bg-eco-accent text-eco-dark'
                                                : 'bg-white/10 text-gray-300 hover:bg-white/20'
                                        }`}
                                    >
                                        📸 Camera
                                    </button>
                                    <button
                                        onClick={() => handleAfterPhotoSourceChange('gallery')}
                                        className={`flex-1 py-2 px-3 rounded-lg text-sm font-medium transition-colors ${
                                            afterPhotoSource === 'gallery'
                                                ? 'bg-eco-accent text-eco-dark'
                                                : 'bg-white/10 text-gray-300 hover:bg-white/20'
                                        }`}
                                    >
                                        🖼️ Gallery
                                    </button>
                                </div>

                                <div className="border-2 border-dashed border-white/20 bg-white/5 rounded-lg p-6 text-center">
                                    <input
                                        type="file"
                                        accept="image/*"
                                        capture={afterPhotoSource === 'camera' ? 'environment' : undefined}
                                        onChange={handleAfterPhotoChange}
                                        className="hidden"
                                        id="after-photo-upload"
                                    />
                                    <label htmlFor="after-photo-upload" className="cursor-pointer">
                                        <div className="text-3xl mb-2">
                                            {afterPhotoSource === 'camera' ? '📸' : '🖼️'}
                                        </div>
                                        <p className="text-gray-300 font-medium">
                                            {afterPhotoSource === 'camera' ? 'Take After Photo' : 'Choose After Photo'}
                                        </p>
                                        <p className="text-sm text-gray-400 mt-1">
                                            {afterPhotoSource === 'camera' ? 'Show the area after cleaning' : 'GPS will be added automatically if missing'}
                                        </p>
                                        {afterPhoto && (
                                            <p className="text-sm text-eco-green mt-2 font-semibold">
                                                Photo selected: {afterPhoto.name}
                                            </p>
                                        )}
                                    </label>
                                </div>
                                {afterPreview && (
                                    <img
                                        src={afterPreview}
                                        alt="After cleanup"
                                        className="w-full max-w-md mx-auto rounded-lg shadow-md"
                                    />
                                )}
                            </div>

                            <button
                                onClick={submitCleanup}
                                disabled={!beforePhoto || !afterPhoto || loading}
                                className={`w-full py-3 px-4 rounded-lg font-semibold transition-colors ${
                                    !beforePhoto || !afterPhoto || loading
                                        ? 'bg-gray-500/40 text-gray-300 cursor-not-allowed'
                                        : 'bg-eco-accent text-eco-dark hover:brightness-110'
                                }`}
                            >
                                {loading ? 'Verifying Cleanup...' : `Submit Cleanup (+${selectedBounty.bounty_points} pts)`}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default WasteBounty;
